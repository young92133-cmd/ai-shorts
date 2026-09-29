"""2B 실기기 검증: 완성 대본→장면 계획→TTS→내부 카드→자막→MP4.

AI 응답만 고정 목 데이터로 대체해 무료·재현 가능하게 확인한다.
실행: .venv\\Scripts\\python.exe scripts/demo_script_split_mvp.py
"""
from __future__ import annotations

import asyncio
import datetime as dt
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import load_config, load_presets, merge_options  # noqa: E402
from app.pipeline import run, script_split  # noqa: E402
from app.pipeline.media import probe_video  # noqa: E402
from app.pipeline.script_split import SplitPlan, SplitScene  # noqa: E402
from scripts.demo_blueprint_mvp import SCRIPT  # noqa: E402


async def main() -> None:
    text = SCRIPT.full_narration()
    assert len(script_split.sentences(text)) == 4
    plan = SplitPlan(scenes=[SplitScene(
        sentence_ids=[i + 1], scene_type="Hook" if i == 0 else "결론" if i == 3 else "핵심 정보",
        visual_type="text_card", visual_description=f"내부 생성 구조 설명 카드 {i + 1}",
        emphasis_text=sc.on_screen_text, motion="zoom_in", transition="cut" if i == 0 else "fade",
        source_requirement="internal_generated", notes="무료 내부 생성 데모")
        for i, sc in enumerate(SCRIPT.scenes)])
    cfg = load_config()
    cfg = merge_options(cfg, load_presets(cfg)["engineering"], {})
    cfg["images"]["provider"] = "none"
    cfg["tts"].update(provider="edge", voice="ko-KR-SunHiNeural", rate="+5%")
    cfg["video"].update(width=1080, height=1920, fps=24, transition=0.3, target_seconds=25)
    job_dir = Path(cfg["paths"]["output"]) / ("mvp_script_split_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))

    async def review(script, preview):
        assert len(preview["blueprint"]["scenes"]) == 4
        return script, {}

    with patch.object(script_split, "ask_structured", new=AsyncMock(return_value=plan)):
        result = await run.run_pipeline(job_dir, "script", text, cfg, review=review)
    info = await probe_video(Path(result["video"]))
    print(f"DEMO_MP4={result['video']}")
    print(f"BLUEPRINT={job_dir / 'blueprint.json'}")
    print(f"SOURCE_REGISTRY={job_dir / 'sources.json'}")
    print(f"VIDEO_WIDTH={info['streams'][0]['width']} HEIGHT={info['streams'][0]['height']} DURATION={float(info['format']['duration']):.2f}")


if __name__ == "__main__":
    asyncio.run(main())
