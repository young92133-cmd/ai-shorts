"""기존 장면별 Script를 자동 영상 제작 설계도로 변환한다.

2A의 기존 대본 및 2B의 완성 대본 분할 결과를 연결한다.
from_script 의 시간은 글자 수 기반 예상치이고, 2C 의 align_to_audio 가 실제 TTS 길이로 확정한다.
확정된 설계도가 렌더 장면 길이의 기준이 된다. 기존 timeline.json의 렌더 계약은 바꾸지 않는다.
"""
from __future__ import annotations

from pathlib import Path

from .models import BlueprintScene, SceneAudio, Script, VideoBlueprint
from .script import CHARS_PER_SEC

FILE = "blueprint.json"


def from_script(script: Script, *, gap: float = 0.25, width: int = 1080,
                height: int = 1920, fps: int = 30) -> VideoBlueprint:
    if not script.scenes:
        raise ValueError("장면이 없는 대본은 영상 제작 설계도를 만들 수 없습니다.")
    if gap < 0 or width <= 0 or height <= 0 or fps <= 0:
        raise ValueError("영상 크기, 프레임 수, 장면 간격을 확인해 주세요.")
    scenes: list[BlueprintScene] = []
    start = 0.0
    for index, scene in enumerate(script.scenes):
        narration = scene.narration.strip()
        if not narration:
            raise ValueError(f"{index + 1}번 장면의 내레이션이 비어 있습니다.")
        # TTS 실측 전 미리보기 수치. 2C에서 실제 오디오 길이로 확정한다.
        speech = max(1.0, len(narration) / CHARS_PER_SEC)
        duration = round(speech + (0.5 if index == len(script.scenes) - 1 else gap), 3)
        end = round(start + duration, 3)
        scenes.append(BlueprintScene(
            index=index, scene_id=f"scene_{index + 1:02d}", scene_type=getattr(scene, "scene_type", ""),
            start=start, end=end, duration=duration, estimated_duration=duration,
            narration=narration, subtitle=getattr(scene, "subtitle", "").strip() or narration,
            visual_type=getattr(scene, "visual_type", "") or ("image" if scene.image_prompt.strip() else "card"),
            visual_description=getattr(scene, "visual_description", "").strip() or scene.image_prompt.strip(),
            image_prompt=scene.image_prompt.strip(),
            source_requirement=getattr(scene, "source_requirement", ""), notes=getattr(scene, "notes", ""),
            motion=getattr(scene, "motion", "") or ("zoom_in" if index % 2 == 0 else "zoom_out"),
            emphasis_text=scene.on_screen_text.strip(),
            transition=getattr(scene, "transition", "") or ("cut" if index == 0 else "fade"),
        ))
        start = end
    return VideoBlueprint(topic=script.topic, width=width, height=height, fps=fps,
                          estimated_duration=start, scenes=scenes)


TAIL = 0.5   # 마지막 장면 뒤 여운. 기존 렌더와 같은 값.


def align_to_audio(bp: VideoBlueprint, scene_audio: list[SceneAudio], *, gap: float,
                   tail: float = TAIL) -> VideoBlueprint:
    """장면별 실제 TTS 길이로 설계도 시간을 확정한다 (2C).

    장면 i 는 자기 음성 시작(offset)에 시작하고, 다음 장면 음성이 시작할 때 끝난다.
    그래서 장면 사이에는 gap 만큼의 짧은 여백만 있고, 마지막 장면만 tail 여운이 붙는다.
    예상치(estimated_duration)는 비교용으로 남긴다. 가짜 길이를 만들지 않는다.
    """
    if len(scene_audio) != len(bp.scenes):
        raise ValueError(f"음성 장면 수({len(scene_audio)})와 설계도 장면 수({len(bp.scenes)})가 다릅니다.")
    out = bp.model_copy(deep=True)
    for i, (scene, audio) in enumerate(zip(out.scenes, scene_audio)):
        if audio.duration is None or audio.duration <= 0:
            raise ValueError(f"{i + 1}번 장면 음성 길이가 올바르지 않습니다.")
        start = round(audio.offset, 3)
        speech_end = round(audio.offset + audio.duration, 3)
        if i + 1 < len(scene_audio):
            end = round(scene_audio[i + 1].offset, 3)
        else:
            end = round(speech_end + tail, 3)
        if end < speech_end:
            raise ValueError(f"{i + 1}번 장면이 음성보다 먼저 끝나도록 계산됐습니다.")
        scene.actual_tts_duration = round(audio.duration, 3)
        scene.timeline_start, scene.speech_end, scene.timeline_end = start, speech_end, end
        scene.start, scene.end, scene.duration = start, end, round(end - start, 3)
    out.timing = "tts_aligned"
    out.scene_gap, out.tail = gap, tail
    out.actual_duration = out.scenes[-1].timeline_end
    return out


def scene_durations(bp: VideoBlueprint) -> list[float]:
    """렌더에 쓸 장면별 화면 길이. 실제 음성으로 확정된 설계도에서만 꺼낸다."""
    if bp.timing != "tts_aligned":
        raise ValueError("실제 음성 길이로 확정되지 않은 설계도로는 영상을 만들 수 없습니다.")
    return [round(s.timeline_end - s.timeline_start, 3) for s in bp.scenes]


def check_timeline(bp: VideoBlueprint, tl: dict, tol: float = 0.02) -> None:
    """timeline.json 장면 시작·길이가 설계도와 같은지 렌더 전에 확인한다."""
    tl_scenes = tl.get("scenes") or []
    if len(tl_scenes) != len(bp.scenes):
        raise ValueError(f"타임라인 장면 수({len(tl_scenes)})가 설계도({len(bp.scenes)})와 다릅니다.")
    for i, (s, t) in enumerate(zip(bp.scenes, tl_scenes)):
        if abs(float(t["start"]) - s.timeline_start) > tol or abs(float(t["duration"]) - s.duration) > tol:
            raise ValueError(
                f"{i + 1}번 장면 시간이 어긋났습니다 (설계도 {s.timeline_start:.2f}+{s.duration:.2f}초, "
                f"타임라인 {float(t['start']):.2f}+{float(t['duration']):.2f}초). 렌더를 중단합니다.")


def save(job_dir: Path, blueprint: VideoBlueprint) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)
    target = job_dir / FILE
    temp = job_dir / (FILE + ".tmp")
    temp.write_text(blueprint.model_dump_json(indent=2), encoding="utf-8")
    temp.replace(target)
    return target


def load(job_dir: Path) -> VideoBlueprint:
    return VideoBlueprint.model_validate_json((job_dir / FILE).read_text(encoding="utf-8"))
