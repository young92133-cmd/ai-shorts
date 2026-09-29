"""무료·권리 안전한 자동 제작 실기기 확인.

고정 대본만 사용하므로 Claude/GPT 호출·유료 이미지·타인 영상·CapCut은 없다.
기존 잡 파이프라인의 Edge TTS, 카드, ASS 자막, FFmpeg MP4 렌더를 실제 실행한다.
실행: .venv\\Scripts\\python.exe scripts/demo_blueprint_mvp.py
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
from app.pipeline import run  # noqa: E402
from app.pipeline.media import probe_video  # noqa: E402
from app.pipeline.models import Scene, Script  # noqa: E402


SCRIPT = Script(
    topic="바람을 버티는 건물의 비밀",
    scenes=[
        Scene(narration="건물은 왜 강한 바람에도 쉽게 무너지지 않을까요?",
              image_prompt="abstract blue wind on a building, no text", on_screen_text="바람의 힘"),
        Scene(narration="핵심은 기둥 하나가 아니라 힘을 나누는 전체 구조에 있습니다.",
              image_prompt="abstract columns and beams, no text", on_screen_text="힘의 분산"),
        Scene(narration="기둥을 굵게 만드는 것보다 하중이 흐르는 길을 설계하는 일이 중요합니다.",
              image_prompt="abstract structural load paths, no text", on_screen_text="하중의 길"),
        Scene(narration="좋은 설계는 눈에 보이는 모양보다 보이지 않는 연결에서 시작됩니다.",
              image_prompt="abstract connected structure, no text", on_screen_text="연결의 설계"),
    ],
    titles=["바람에도 버티는 건물의 비밀"],
    description="건물의 하중 전달을 설명하는 내부 제작 데모입니다.",
    hashtags=["건축", "구조"], sources=[],
)


async def main() -> None:
    cfg = load_config()
    cfg = merge_options(cfg, load_presets(cfg)["engineering"], {})
    cfg["images"]["provider"] = "none"
    cfg["tts"].update(provider="edge", voice="ko-KR-SunHiNeural", rate="+5%")
    cfg["video"].update(width=1080, height=1920, fps=24, transition=0.3, target_seconds=25)
    job_dir = Path(cfg["paths"]["output"]) / ("mvp_blueprint_demo_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    with (patch.object(run.research, "research_topic", new=AsyncMock(return_value=[])),
          patch.object(run.scriptmod, "write_script", new=AsyncMock(return_value=SCRIPT))):
        result = await run.run_pipeline(job_dir, "topic", SCRIPT.topic, cfg,
                                        style={"name": "내부 생성 데모"}, visual_mode="images")
    info = await probe_video(Path(result["video"]))
    print(f"DEMO_MP4={result['video']}")
    print(f"BLUEPRINT={job_dir / 'blueprint.json'}")
    print(f"SOURCE_REGISTRY={job_dir / 'sources.json'}")
    print(f"VIDEO_WIDTH={info['streams'][0]['width']} HEIGHT={info['streams'][0]['height']} DURATION={float(info['format']['duration']):.2f}")


if __name__ == "__main__":
    asyncio.run(main())
