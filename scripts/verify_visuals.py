"""2D 실기기 검증: 장면별 화면 자동 선택이 들어간 실제 MP4 3편을 만들고 점검한다.

  A 정보/상식형   주제 → 실제 AI 조사·대본(Claude 구독) → 장면 설계 → TTS → 화면 자동 선택 → MP4
  B 사연/스토리형 완성 대본(수동 보조 경로) + 직접 그려 권리를 확인한 그림 1장 업로드
  C 제품/기술형   주제 → 실제 AI 조사·대본 → … → MP4

무료 경로: Edge TTS, 내부 카드, ffmpeg. AI 이미지 생성은 꺼져 있다(config 기본값). CapCut 미사용.
A·C 는 Claude 구독 한도를 쓴다. 실행: .venv\\Scripts\\python.exe scripts/verify_visuals.py [A B C]
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import load_config, load_presets, merge_options  # noqa: E402
from app.pipeline import blueprint, run  # noqa: E402
from app.pipeline.cards import _font  # noqa: E402
from app.pipeline.media import require_ffmpeg  # noqa: E402
from app.pipeline.script_split import EMPHASIS_MAX  # noqa: E402
from app.pipeline.sources import SourceRegistry  # noqa: E402
from app.pipeline.subtitles import wrap_title  # noqa: E402
from scripts.verify_tts_timeline import verify as verify_timing  # noqa: E402

STORY = ("퇴근길 버스에서 지갑을 잃어버린 걸 알았을 때, 정말 눈앞이 캄캄했습니다. "
         "신분증에 카드까지 전부 그 안에 있었거든요. "
         "그날 밤 늦게 모르는 번호로 전화가 한 통 왔습니다. "
         "버스 기사님이 좌석 밑에서 지갑을 발견하고 명함을 보고 연락하신 거였어요. "
         "다음 날 찾아가 감사 인사를 드리자, 기사님은 손사래를 치며 웃으셨습니다. "
         "누구라도 그렇게 했을 거라면서요. "
         "그 뒤로 저도 길에서 떨어진 물건을 보면 그냥 지나치지 않게 됐습니다. "
         "작은 친절이 이렇게 돌고 돈다는 걸 그날 처음 배웠습니다.")

OWN_RIGHTS = {"license": "my_channel", "rights_confirmed": True, "commercial_allowed": True,
              "adaptation_allowed": True, "third_party_rights_checked": True,
              "license_note": "검증용으로 이 프로그램에서 직접 그린 그림 (제3자 요소 없음)"}


def _draw_bus_wallet(path: Path) -> None:
    """B 의 지갑 이야기에 맞춘 (장면 번호를 지정하지 않고 올린다) 단순 일러스트. 일부러 가로 비율로 만든다."""
    img = Image.new("RGB", (1600, 900), (236, 228, 214))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([420, 250, 1180, 700], radius=60, fill=(120, 72, 40), outline=(70, 40, 20), width=12)
    d.rounded_rectangle([470, 300, 900, 560], radius=24, fill=(250, 250, 250), outline=(60, 60, 60), width=6)
    d.rectangle([500, 340, 620, 480], fill=(180, 200, 230))
    d.text((650, 350), "ID CARD", font=_font(56), fill=(40, 40, 40))
    for k, color in enumerate(((220, 60, 60), (60, 120, 220))):
        d.rounded_rectangle([760 + k * 60, 470 + k * 40, 1120 + k * 60, 640 + k * 40], radius=20, fill=color)
    img.save(path, quality=92)


def _cfg(preset: str, target: int) -> dict:
    cfg = load_config()
    cfg = merge_options(cfg, load_presets(cfg)[preset], {})
    cfg["images"]["provider"] = "none"
    cfg["tts"].update(provider="edge", voice="ko-KR-InJoonNeural")
    cfg["video"]["target_seconds"] = target
    return cfg


async def _auto_ok(script, preview):
    return script, {}


def _mid_frames(video: Path, bp, out: Path) -> Path:
    """장면 가운데 프레임을 한 장씩 모아 사람이 한눈에 보는 시트로."""
    out.mkdir(exist_ok=True)
    shots = []
    for s in bp.scenes:
        t = (s.timeline_start + s.speech_end) / 2
        p = out / f"mid{s.index + 1:02d}.jpg"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=270:-2", str(p)])
        shots.append(p)
    sheet = Image.new("RGB", (270 * len(shots), 480), "black")
    for k, p in enumerate(shots):
        sheet.paste(Image.open(p).resize((270, 480)), (270 * k, 0))
    target = out.parent / "scene_sheet.jpg"
    sheet.save(target, quality=85)
    return target


def check_visuals(name: str, job_dir: Path) -> dict:
    bp = blueprint.load(job_dir)
    reg = SourceRegistry(job_dir)
    problems = []
    kinds = []
    print(f"\n--- {name}: 장면별 화면 ---")
    for s in bp.scenes:
        d = s.visual_decision
        kinds.append(d.resolved_visual_type)
        item = reg.by_path(d.asset_path) if d.asset_path else None
        usable = bool(item and item.usable_in_video)
        if d.rights_status != "allowed" or not usable:
            problems.append(f"장면 {s.index + 1} 권리 문제")
        if len(s.emphasis_text) > EMPHASIS_MAX:
            problems.append(f"장면 {s.index + 1} 강조문구 {len(s.emphasis_text)}자")
        if len(wrap_title(s.emphasis_text, 11)) > 2:
            problems.append(f"장면 {s.index + 1} 키워드 2줄 초과")
        print(f"{s.index + 1}. [{s.content_kind:<10}] {d.resolved_visual_type:<18} 강조='{s.emphasis_text}'"
              f"{' (대체)' if d.fallback_used else ''}\n   이유: {d.selection_reason}")
    longest, run_len = 1, 1
    for a, b in zip(kinds, kinds[1:]):
        run_len = run_len + 1 if a == b else 1
        longest = max(longest, run_len)
    if longest >= 3:
        problems.append(f"같은 화면 {longest}번 연속")
    print(f"화면 종류: {sorted(set(kinds))} · 최대 연속 {longest}")
    return {"kinds": kinds, "types": sorted(set(kinds)), "max_repeat": longest, "problems": problems}


async def make(name: str, stamp: str) -> dict:
    out = Path(load_config()["paths"]["output"])
    job_dir = out / f"visuals_{name}_{stamp}"
    if name == "A":
        result = await run.run_pipeline(job_dir, "topic", "고양이가 좁은 상자를 좋아하는 이유",
                                        _cfg("daily", 30), review=_auto_ok)
    elif name == "B":
        (job_dir / "uploads").mkdir(parents=True, exist_ok=True)
        _draw_bus_wallet(job_dir / "uploads" / "wallet.jpg")
        result = await run.run_pipeline(job_dir, "script", STORY, _cfg("daily", 40), review=_auto_ok,
                                        upload_rights={"wallet.jpg": OWN_RIGHTS})
    else:
        result = await run.run_pipeline(job_dir, "topic", "노이즈캔슬링 이어폰이 주변 소음을 없애는 원리",
                                        _cfg("engineering", 45), review=_auto_ok)
    timing = await verify_timing(name, job_dir, result)
    vis = check_visuals(name, job_dir)
    sheet = _mid_frames(Path(result["video"]), blueprint.load(job_dir), job_dir / "mid_frames")
    print(f"장면 시트: {sheet}")
    return {**timing, **vis, "problems": timing["problems"] + vis["problems"], "sheet": str(sheet),
            "plan_method": result.get("plan_method") or result.get("split_method"), "topic": result.get("topic")}


async def main() -> None:
    require_ffmpeg()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    names = sys.argv[1:] or ["A", "B", "C"]
    report = [await make(n, stamp) for n in names]
    out = Path(load_config()["paths"]["output"]) / f"visuals_report_{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [r["name"] for r in report if r["problems"]]
    print("\n전체:", "모두 통과" if not failed else f"문제 있음 {failed}", f"· 보고서 {out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
