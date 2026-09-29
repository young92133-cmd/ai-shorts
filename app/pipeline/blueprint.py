"""기존 장면별 Script를 자동 영상 제작 설계도로 변환한다.

2A에서는 이미 생성된 대본을 연결한다. 직접 쓴 텍스트의 AI 장면 분할은 2B,
TTS 실측 시간 반영은 2C가 담당한다. 기존 timeline.json의 렌더 계약은 바꾸지 않는다.
"""
from __future__ import annotations

from pathlib import Path

from .models import BlueprintScene, Script, VideoBlueprint
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
            index=index, start=start, end=end, duration=duration,
            narration=narration, subtitle=narration,
            visual_type="image" if scene.image_prompt.strip() else "card",
            image_prompt=scene.image_prompt.strip(),
            motion="zoom_in" if index % 2 == 0 else "zoom_out",
            emphasis_text=scene.on_screen_text.strip(),
            transition="cut" if index == 0 else "fade",
        ))
        start = end
    return VideoBlueprint(topic=script.topic, width=width, height=height, fps=fps,
                          estimated_duration=start, scenes=scenes)


def save(job_dir: Path, blueprint: VideoBlueprint) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)
    target = job_dir / FILE
    temp = job_dir / (FILE + ".tmp")
    temp.write_text(blueprint.model_dump_json(indent=2), encoding="utf-8")
    temp.replace(target)
    return target


def load(job_dir: Path) -> VideoBlueprint:
    return VideoBlueprint.model_validate_json((job_dir / FILE).read_text(encoding="utf-8"))
