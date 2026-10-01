r"""V1 실사용 검증. 실제 Claude 구독/Edge TTS/FFmpeg를 사용하며 유료 API는 차단한다.

사용자 요청이 있을 때만 실행한다:
  .venv\Scripts\python.exe scripts/verify_factory_v1.py --cases A B C D E --youtube-url URL
이미 만든 프로젝트 검사:
  ... --verify PROJECT_ID
영상/보고서는 Git 제외 output/에 보존한다. 한 편씩 실행하며 실패한 기존 결과도 지우지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402
from app.factory import core, batch, state as st  # noqa: E402
from app.pipeline import blueprint, timeline  # noqa: E402
from app.pipeline.media import require_ffmpeg, probe_video, probe_duration  # noqa: E402
from app.pipeline.sources import SourceRegistry  # noqa: E402
from app.pipeline.llm import safe_error  # noqa: E402


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def verify(project_id: str) -> dict:
    job_dir = core.project_dir(project_id)
    saved = st.load(job_dir)
    video = job_dir / "final.mp4"
    issues = []
    if not video.is_file() or not video.stat().st_size:
        return {"project_id": project_id, "passed": False, "issues": ["final.mp4 없음"], "state": saved.get("status")}
    info = await probe_video(video)
    stream = info["streams"][0]
    duration = float(info["format"]["duration"])
    if (stream["width"], stream["height"]) != (1080, 1920):
        issues.append("해상도가 1080x1920이 아님")
    if saved.get("status") != "render_complete":
        issues.append("project_state가 완료 상태가 아님")
    narration = job_dir / "narration.mp3"
    if not narration.is_file() or await probe_duration(narration) <= 0:
        issues.append("TTS 파일 없음/길이 오류")
    ass = job_dir / "subs.ass"
    if not ass.is_file() or "Dialogue:" not in ass.read_text(encoding="utf-8"):
        issues.append("자막 파일 없음/내용 없음")
    bp = blueprint.load(job_dir)
    tl = timeline.load(job_dir)
    try:
        blueprint.check_timeline(bp, tl)
    except ValueError as exc:
        issues.append(str(exc))
    rights_ok = True
    try:
        SourceRegistry(job_dir).guard_timeline(tl)
    except ValueError as exc:
        rights_ok = False
        issues.append(str(exc))
    calls = saved.get("ai_calls", [])
    used = [call["provider"] for call in calls if call.get("status") == "success"]
    expected_provider = used[-1] if used else "none"
    recorded_provider = saved.get("ai_provider_used") or "none"
    if recorded_provider != expected_provider or set(saved.get("ai_providers_used", [])) != set(used):
        issues.append("AI 공급자 기록과 실제 성공 호출 이력이 다름")
    if abs(duration - bp.actual_duration) > 0.2:
        issues.append("설계도와 실제 영상 길이가 다름")
    # 전체 스트림을 실제로 디코딩해 깨진 프레임/오디오가 없는지 확인한다.
    decoded = await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if decoded.returncode or decoded.stderr.strip():
        issues.append("전체 디코딩 오류: " + safe_error(decoded.stderr))
    # 장면 중앙과 전환 직후를 뽑아 눈으로도 확인할 수 있게 한다.
    frames = job_dir / "v1_check_frames"
    frames.mkdir(exist_ok=True)
    shots = []
    for scene in bp.scenes:
        for label, t in (("middle", (scene.timeline_start + scene.speech_end) / 2),
                         ("transition", min(scene.timeline_start + 0.5, scene.speech_end))):
            shot = frames / f"scene_{scene.index + 1:02d}_{label}.jpg"
            result = await asyncio.to_thread(subprocess.run,
                ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-ss", str(t), "-i", str(video),
                 "-frames:v", "1", "-vf", "scale=270:480", str(shot)], capture_output=True, timeout=30)
            if result.returncode or not shot.is_file():
                issues.append(f"{scene.index + 1}장면 프레임 추출 실패")
            elif label == "middle":
                shots.append(shot)
    sheet_path = job_dir / "v1_scene_sheet.jpg"
    if shots:
        sheet = Image.new("RGB", (270 * len(shots), 480), "black")
        for i, shot in enumerate(shots):
            with Image.open(shot) as image:
                sheet.paste(image, (270 * i, 0))
        sheet.save(sheet_path, quality=90)
    return {"project_id": project_id, "passed": not issues, "issues": issues,
            "final_video": str(video), "duration": round(duration, 2), "resolution": "1080x1920",
            "scenes": len(bp.scenes), "subtitle_lines": len(tl["subtitles"]["lines"]),
            "ai_provider_used": saved.get("ai_provider_used"), "ai_calls": saved.get("ai_calls", []),
            "scene_sheet": str(sheet_path), "rights_guard": rights_ok}


async def main(args) -> int:
    require_ffmpeg()
    if args.verify:
        result = await verify(args.verify)
        (core.project_dir(args.verify) / "v1_verification.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 1
    report_path = core.output_root() / ("v1_report_" + core._new_id() + ".json")
    report = {"started": st.now(), "paid_api_allowed": False, "cases": []}
    common = {"seconds": 45, "llm": "claude", "allow_openai": False, "log": log}
    for case in args.cases:
        log(f"=== V1 실제 제작 {case} ===")
        entry = {"case": case}
        try:
            if case == "A":
                result = await core.make(topic="하늘이 파랗고 노을이 붉은 이유", content_format="information", review=True, **common)
                if result.get("status") == "waiting_for_script_approval":
                    pid = result["project_id"]
                    core.status(pid)
                    core.inspect(pid, "script")
                    before = _hash(core.project_dir(pid) / "script.json")
                    result = await core.resume(pid, log=log)
                    entry["review_resume_script_preserved"] = before == _hash(core.project_dir(pid) / "script.json")
            elif case == "B":
                result = await core.make(topic="비 오는 버스 정류장에서 모르는 사람에게 우산을 빌려준 작은 친절의 창작 사연",
                                         content_format="story", **common)
            elif case == "C":
                result = await core.make(topic="USB-C 모양이 같아도 충전 속도와 데이터 속도가 다른 이유",
                                         content_format="information", **common)
            elif case == "D":
                if not args.youtube_url:
                    raise RuntimeError("D 검증에는 --youtube-url이 필요합니다.")
                result = await core.make(url=args.youtube_url, content_format="information", **common)
            elif case == "E":
                found = await core.trends(limit=5, log=log)
                entry["trend_candidates"] = found["candidates"]
                entry["candidates_id"] = found["candidates_id"]
                selected = await batch.make(select=[2 if len(found["candidates"]) >= 2 else 1],
                                            candidates_id=found["candidates_id"], content_format="issue", **common)
                entry["batch_id"] = selected["batch_id"]
                result = selected["items"][0]["result"]
            elif case == "F":
                result = await core.make(auto=True, content_format="issue", **common)
            elif case == "G":
                if not args.article_url:
                    raise RuntimeError("G 검증에는 --article-url이 필요합니다.")
                result = await core.make(url=args.article_url, content_format="information", **common)
            elif case == "H":
                if not args.reference_video:
                    raise RuntimeError("H 검증에는 --reference-video가 필요합니다.")
                result = await core.make(reference_video=args.reference_video, content_format="information", **common)
            else:
                raise ValueError(case)
            entry["result"] = result
            if result.get("status") == "render_complete":
                entry["verification"] = await verify(result["project_id"])
        except Exception as exc:
            entry["error"] = safe_error(exc)
        report["cases"].append(entry)
        report["updated"] = st.now()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(entry, ensure_ascii=False, indent=2), flush=True)
    print(f"REPORT: {report_path}")
    return 0 if all(c.get("verification", {}).get("passed") for c in report["cases"]) else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="사용자 승인 후 V1 실제 제작 검증")
    parser.add_argument("--cases", nargs="+", choices=list("ABCDEFGH"), default=list("ABCDE"))
    parser.add_argument("--youtube-url")
    parser.add_argument("--article-url")
    parser.add_argument("--reference-video")
    parser.add_argument("--verify", help="이미 완성된 Factory 프로젝트 id")
    sys.exit(asyncio.run(main(parser.parse_args())))
