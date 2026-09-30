"""2C 실기기 검증: 실제 Edge TTS 길이로 장면·자막·영상 시간이 맞는지 MP4 까지 확인한다.

무료 경로만 쓴다: Edge TTS(인터넷 필요) + 내부 생성 카드 + ffmpeg. CapCut·유료 API·LLM 호출 없음.
  A  직접 대본 약 20~30초 (장면 분할은 실제 코드의 문장 경계 대체 경로)
  B  경제 쇼츠 약 50~60초 (직접 대본)
  A2 주제 경로 (리서치·AI 대본만 고정 데이터, TTS·렌더는 실제)
실행: .venv\\Scripts\\python.exe scripts/verify_tts_timeline.py
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import load_config, load_presets, merge_options  # noqa: E402
from app.pipeline import blueprint, run, script_split, timeline  # noqa: E402
from app.pipeline.media import probe_duration, probe_video, require_ffmpeg  # noqa: E402
from app.pipeline.models import Scene, Script  # noqa: E402

SCRIPT_A = ("엘리베이터 케이블이 끊어지면 정말 바로 떨어질까요? "
            "사실 엘리베이터는 여러 가닥의 케이블이 무게를 나눠서 들고 있습니다. "
            "한 가닥이 끊어져도 나머지 케이블이 버티도록 여유 있게 설계합니다. "
            "속도가 갑자기 빨라지면 조속기가 감지해서 비상 브레이크를 겁니다. "
            "그래서 영화처럼 한 번에 추락하는 일은 거의 일어나지 않습니다.")

SCRIPT_B = ("월급은 그대로인데 왜 장바구니는 점점 가벼워질까요? "
            "이 현상을 경제학에서는 실질 소득 감소라고 부릅니다. "
            "예를 들어 월급이 300만 원이고 물가가 1년에 3퍼센트 오른다고 가정해 보겠습니다. "
            "숫자로는 같은 300만 원이지만, 1년 뒤 살 수 있는 물건은 약 3퍼센트 줄어듭니다. "
            "이 상태가 3년 이어지면 구매력은 대략 9퍼센트 가까이 줄어듭니다. "
            "그래서 연봉 협상에서는 인상률을 물가 상승률과 비교해 봐야 합니다. "
            "인상률이 물가보다 낮다면, 월급이 올라도 실제로는 깎인 것과 비슷합니다. "
            "저축도 마찬가지입니다. 이자율이 물가보다 낮으면 돈의 가치가 조금씩 줄어듭니다. "
            "결국 중요한 건 숫자가 아니라, 그 돈으로 무엇을 살 수 있느냐입니다. "
            "이 영상의 숫자는 이해를 돕기 위한 가정입니다.")

TOPIC_SCRIPT = Script(
    topic="콘크리트가 강한 이유", titles=["콘크리트는 왜 단단할까"], description="검증용 고정 대본", hashtags=["건축"],
    sources=[], scenes=[
        Scene(narration="콘크리트는 누르는 힘에는 강하지만 당기는 힘에는 약합니다.", image_prompt="concrete", on_screen_text="누르는 힘에 강함"),
        Scene(narration="그래서 안에 철근을 넣어 당기는 힘을 대신 버티게 합니다.", image_prompt="rebar", on_screen_text="철근이 인장력 담당"),
        Scene(narration="두 재료가 온도에 따라 늘어나는 정도가 비슷해서 서로 잘 붙어 있습니다.", image_prompt="bond", on_screen_text="열팽창 계수 비슷"),
        Scene(narration="이 조합 덕분에 높은 건물과 긴 다리를 만들 수 있습니다.", image_prompt="bridge", on_screen_text="철근콘크리트"),
    ])


def _cfg(target: int) -> dict:
    cfg = load_config()
    cfg = merge_options(cfg, load_presets(cfg)["engineering"], {})
    cfg["images"]["provider"] = "none"            # 내부 대체 카드만 사용 (무료)
    cfg["tts"].update(provider="edge", voice="ko-KR-InJoonNeural")
    cfg["video"].update(target_seconds=target)
    return cfg


def _silence_tail(video: Path, total: float) -> float:
    """영상 끝부분의 연속 무음 길이 (끝까지 이어지는 무음이 없으면 0)."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "silencedetect=n=-40dB:d=0.3",
                        "-vn", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p.stderr)]
    if starts and len(starts) > len(ends):      # 끝까지 무음으로 끝남
        return round(total - starts[-1], 2)
    if starts and ends and abs(ends[-1] - total) < 0.1:
        return round(total - starts[-1], 2)
    return 0.0


async def _scene_gaps(video: Path, bp) -> list[float]:
    """장면 경계마다 말이 멈춰 있는 시간 (음성 끝 → 다음 음성 시작 사이 실제 무음)."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "silencedetect=n=-40dB:d=0.1",
                        "-vn", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    spans = list(zip([float(x) for x in re.findall(r"silence_start: ([\d.]+)", p.stderr)],
                     [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p.stderr)]))
    out = []
    for s in bp.scenes[1:]:
        hit = [e - st for st, e in spans if st - 0.5 <= s.timeline_start <= e + 0.5]
        out.append(round(max(hit), 2) if hit else 0.0)
    return out


def _frames(video: Path, bp, out: Path) -> list[Path]:
    """장면 경계 직후(+0.3초)와 직전(-0.2초) 프레임을 뽑아 사람이 볼 수 있게 한다."""
    out.mkdir(exist_ok=True)
    shots = []
    for s in bp.scenes:
        for label, t in (("start", s.timeline_start + 0.3), ("end", max(s.timeline_start, s.timeline_end - 0.2))):
            p = out / f"scene{s.index + 1:02d}_{label}.jpg"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                            "-frames:v", "1", "-vf", "scale=360:-2", str(p)])
            shots.append(p)
    return shots


async def verify(name: str, job_dir: Path, result: dict) -> dict:
    bp = blueprint.load(job_dir)
    tl = timeline.load(job_dir)
    video = Path(result["video"])
    info = await probe_video(video)
    width, height = info["streams"][0]["width"], info["streams"][0]["height"]
    final_len = float(info["format"]["duration"])
    narration_len = await probe_duration(job_dir / "narration.mp3")
    problems: list[str] = []

    print(f"\n=== {name}: {len(bp.scenes)}장면 ===")
    print(f"{'장면':>4} {'역할':<8} {'예상':>7} {'실제음성':>8} {'파일실측':>8} {'시작':>7} {'음성끝':>7} {'종료':>7}")
    for s in bp.scenes:
        mp3 = job_dir / "audio" / f"scene_{s.index:02d}.mp3"
        file_len = await probe_duration(mp3) if mp3.is_file() else -1
        if abs(file_len - s.actual_tts_duration) > 0.01:
            problems.append(f"장면 {s.index + 1} 음성 파일 길이 불일치")
        if s.timeline_end < s.speech_end:
            problems.append(f"장면 {s.index + 1} 음성이 잘림")
        print(f"{s.index + 1:>4} {s.scene_type[:8]:<8} {s.estimated_duration:>6.2f}s {s.actual_tts_duration:>7.2f}s "
              f"{file_len:>7.2f}s {s.timeline_start:>6.2f}s {s.speech_end:>6.2f}s {s.timeline_end:>6.2f}s")
    try:
        blueprint.check_timeline(bp, tl)
    except ValueError as e:
        problems.append(str(e))

    # 자막 줄이 자기 장면 음성 구간 안에 있고 다음 장면으로 넘어가지 않는지
    lines = tl["subtitles"]["lines"]
    starts = [s.timeline_start for s in bp.scenes]
    bad_lines = 0
    for ln in lines:
        idx = max(i for i, st in enumerate(starts) if st <= ln["start"] + 1e-6)
        sc = bp.scenes[idx]
        if ln["end"] > sc.timeline_end + 1e-6 or ln["end"] > sc.speech_end + 0.16 or ln["end"] <= ln["start"]:
            bad_lines += 1
    if bad_lines:
        problems.append(f"장면 밖으로 나간 자막 {bad_lines}줄")

    expected_narr = (sum(s.actual_tts_duration for s in bp.scenes)
                     + (bp.scene_gap or 0.25) * (len(bp.scenes) - 1) + (bp.tail or 0.0))
    if abs(narration_len - expected_narr) > 0.15:
        problems.append(f"나레이션 길이 {narration_len:.2f}s ≠ 장면 합 {expected_narr:.2f}s")
    if abs(final_len - bp.actual_duration) > 0.15:
        problems.append(f"영상 {final_len:.2f}s 와 설계도 {bp.actual_duration:.2f}s 차이가 큼")
    if final_len + 0.05 < bp.scenes[-1].speech_end:
        problems.append("마지막 음성이 영상보다 길어 잘림")
    tail = _silence_tail(video, final_len)
    if tail > 0.8:
        problems.append(f"끝 무음 {tail:.2f}s")
    if (width, height) != (1080, 1920):
        problems.append(f"해상도 {width}x{height}")
    shots = _frames(video, bp, job_dir / "check_frames")

    gaps = await _scene_gaps(video, bp)
    if gaps and max(gaps) > 1.0:
        problems.append(f"장면 사이 무음이 김 (최대 {max(gaps):.2f}s)")
    print(f"자막 {len(lines)}줄 (장면 밖 {bad_lines}줄) · 나레이션 {narration_len:.2f}s (장면 합+여백+여운 {expected_narr:.2f}s)")
    print(f"장면 전환 무음(초): {', '.join(f'{g:.2f}' for g in gaps) or '-'}")
    print(f"설계도 영상 길이 {bp.actual_duration:.2f}s · 실제 MP4 {final_len:.2f}s · {width}x{height} · 끝 무음 {tail:.2f}s")
    print(f"MP4: {video}")
    print(f"확인용 프레임 {len(shots)}장: {job_dir / 'check_frames'}")
    print("결과:", "통과" if not problems else "문제 → " + " / ".join(problems))
    return {"name": name, "mp4": str(video), "duration": round(final_len, 2), "blueprint_duration": bp.actual_duration,
            "size": f"{width}x{height}", "scenes": len(bp.scenes), "subtitle_lines": len(lines),
            "tail_silence": tail, "problems": problems}


async def main() -> None:
    require_ffmpeg()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = Path(load_config()["paths"]["output"])
    report = []

    async def auto_ok(script, preview):
        return script, {}

    # A·B: 직접 대본. AI 분할 대신 실제 코드의 문장 경계 대체 경로를 쓴다 (LLM 호출 없음)
    for name, text, target in (("A_short", SCRIPT_A, 25), ("B_econ", SCRIPT_B, 55)):
        job_dir = out_root / f"tts_timeline_{name}_{stamp}"
        with patch.object(script_split, "ask_structured", new=AsyncMock(side_effect=RuntimeError("검증: AI 없이 분할"))):
            result = await run.run_pipeline(job_dir, "script", text, _cfg(target), review=auto_ok)
        report.append(await verify(name, job_dir, result))

    # A2: 주제 경로. 리서치·AI 대본만 고정, TTS·자막·렌더는 실제
    job_dir = out_root / f"tts_timeline_A2_topic_{stamp}"
    with patch.object(run.research, "research_topic", new=AsyncMock(return_value=[])), \
         patch.object(run.scriptmod, "make_plan", new=AsyncMock(side_effect=RuntimeError("검증: 구성 생략"))), \
         patch.object(run.scriptmod, "write_script", new=AsyncMock(return_value=TOPIC_SCRIPT)):
        result = await run.run_pipeline(job_dir, "topic", "콘크리트가 강한 이유", _cfg(25), review=auto_ok)
    report.append(await verify("A2_topic", job_dir, result))

    (out_root / f"tts_timeline_report_{stamp}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [r["name"] for r in report if r["problems"]]
    print("\n전체:", "모두 통과" if not failed else f"문제 있음 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
