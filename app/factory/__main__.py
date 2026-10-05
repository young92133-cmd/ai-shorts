"""콘텐츠팩토리 명령줄. 결과는 stdout 에 JSON 한 덩어리, 진행 로그는 stderr 로 나온다.

    python -m app.factory make --topic "고양이가 상자를 좋아하는 이유" --seconds 45
    python -m app.factory make --url "https://..." --seconds 50 --review   # 대본까지만 만들고 멈춤
    python -m app.factory resume  [project_id]                            # 멈춘 대본으로 이어서 MP4까지
    python -m app.factory status  [project_id]
    python -m app.factory inspect [project_id] --part script|scenes|visuals|files|all
    python -m app.factory edit-scene [project_id] --scene 3 --narration "..." --emphasis "..."
    python -m app.factory set-visual [project_id] --scene 3 --card number_card
    python -m app.factory rerender [project_id]
    python -m app.factory styles | trends | export [project_id] --pack

종료 코드: 0 성공 / 1 제작 실패 / 2 요청 오류(없는 프로젝트, 잘못된 값, 아직 할 수 없는 단계)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from . import core, batch, benchmark


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m app.factory", description="AI 쇼츠 콘텐츠팩토리")
    sub = ap.add_subparsers(dest="cmd", required=True)

    mk = sub.add_parser("make", help="쇼츠 한 편 만들기 (기본: MP4 까지 자동)")
    src = mk.add_mutually_exclusive_group(required=True)
    src.add_argument("--topic", help="주제")
    src.add_argument("--url", help="유튜브·기사 링크 (여러 개면 공백으로 구분)")
    src.add_argument("--auto", action="store_true", help="요즘 화제 소재를 AI 가 골라서")
    src.add_argument("--script", dest="script_text", help="완성 대본 직접 입력 (보조 기능)")
    src.add_argument("--script-file", help="완성 대본 텍스트 파일")
    src.add_argument("--reference-video", help="참고 영상 파일 (분석 전용, 200MB 이하)")
    mk.add_argument("--hint", default="", help="참고 영상의 주제 힌트 (사실 근거로 취급하지 않음)")
    mk.add_argument("--seconds", type=int, help="목표 길이(초)")
    mk.add_argument("--preset", default="daily", help="분야 기본값 (styles 명령으로 목록 확인)")
    mk.add_argument("--style", help="참고 스타일 id 또는 이름")
    mk.add_argument("--review", "--stop-at-script", action="store_true", help="대본까지만 만들고 승인 대기")
    mk.add_argument("--instructions", default="", help="추가 요청 (말투, 강조할 점 등)")
    mk.add_argument("--llm", choices=("claude", "openai", "auto"))
    mk.add_argument("--allow-openai", action="store_true", default=None, help="이번 제작에서 유료 OpenAI API 사용을 명시적으로 허용")
    mk.add_argument("--format", dest="content_format", choices=tuple(core.FORMATS), help="information | story | issue")
    mk.add_argument("--model")
    mk.add_argument("--tts", help="edge | openai | elevenlabs | typecast")
    mk.add_argument("--voice")
    mk.add_argument("--no-subtitles", action="store_true")
    mk.add_argument("--asset", action="append", default=[], help="장면 화면 후보 파일 (여러 번 가능)")
    mk.add_argument("--license", default="my_channel", help="첨부 파일 권리: my_channel | ai_generated | pexels | pixabay | kogl_type0 | kogl_type1")
    mk.add_argument("--note", default="", help="권리 근거 (예: 내가 직접 찍은 사진)")
    mk.add_argument("--confirm-rights", action="store_true", help="첨부 파일을 영상에 써도 된다는 것을 확인함")
    mk.add_argument("--benchmark", default="auto", help="콘텐츠 구조: auto(기본, 8개 중 자동 선택) | off(기존 구성) | profile id 강제 지정")

    for name, help_ in (("resume", "멈춘 대본으로 이어서 MP4 까지"), ("status", "진행 상태"),
                        ("rerender", "저장된 재료로 영상만 다시 렌더")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("project_id", nargs="?", help="생략하면 가장 최근 프로젝트")

    ins = sub.add_parser("inspect", help="대본·장면·화면·파일 보기")
    ins.add_argument("project_id", nargs="?")
    ins.add_argument("--part", default="all", choices=("all", "script", "scenes", "visuals", "benchmark", "files"))

    ed = sub.add_parser("edit-scene", help="렌더 전 장면 문장/강조문구 수정")
    ed.add_argument("project_id", nargs="?")
    ed.add_argument("--scene", type=int, required=True, help="장면 번호 (1부터)")
    ed.add_argument("--narration")
    ed.add_argument("--emphasis")

    sv = sub.add_parser("set-visual", help="장면 화면 바꾸기")
    sv.add_argument("project_id", nargs="?")
    sv.add_argument("--scene", type=int, required=True, help="장면 번호 (1부터)")
    sv.add_argument("--card", choices=core.CARD_CHOICES)
    sv.add_argument("--file", help="권리가 확인된 이미지 파일")
    sv.add_argument("--license", default="my_channel")
    sv.add_argument("--note", default="")
    sv.add_argument("--confirm-rights", action="store_true")

    sub.add_parser("styles", help="프리셋·스타일 목록")
    tr = sub.add_parser("trends", help="요즘 화제 키워드")
    tr.add_argument("--limit", type=int, default=10)

    bt = sub.add_parser("batch", help="여러 편을 한 편씩 순차 제작")
    inputs = bt.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--topic", dest="topics", action="append", help="주제 (여러 번 지정 가능)")
    inputs.add_argument("--select", nargs="+", type=int, help="trends 후보 번호 (예: --select 2 4)")
    bt.add_argument("--candidates", dest="candidates_id", help="trends가 반환한 후보 id, 생략하면 최근 목록")
    bt.add_argument("--count", type=int, default=1, help="주제마다 만들 편수 (전체 최대 10편)")
    bt.add_argument("--seconds", type=int)
    bt.add_argument("--preset", default="daily")
    bt.add_argument("--style")
    bt.add_argument("--format", dest="content_format", choices=tuple(core.FORMATS))
    bt.add_argument("--review", action="store_true")
    bt.add_argument("--instructions", default="")
    bt.add_argument("--llm", choices=("claude", "openai", "auto"))
    bt.add_argument("--allow-openai", action="store_true", default=None)
    bt.add_argument("--model")
    bt.add_argument("--benchmark", default="auto", help="콘텐츠 구조: auto(기본, 8개 중 자동 선택) | off(기존 구성) | profile id 강제 지정")
    for name in ("batch-status", "batch-resume"):
        bs = sub.add_parser(name, help="순차 제작 상태 조회" if name == "batch-status" else "순차 제작의 검토 대본 이어서 완성")
        bs.add_argument("batch_id", nargs="?")

    ex = sub.add_parser("export", help="완성 파일 목록 / 편집용 내보내기")
    ex.add_argument("project_id", nargs="?")
    ex.add_argument("--pack", action="store_true", help="편집 재료 zip")
    ex.add_argument("--capcut", action="store_true", help="CapCut 프로젝트로 내보내기")

    bm = sub.add_parser("benchmark", help="V2: 관찰 메모에서 claim/evidence 쌍 선택 (오프라인)")
    bm_sub = bm.add_subparsers(dest="benchmark_cmd", required=True)
    bm_sub.add_parser("profiles", help="구조적 benchmark profile 목록")
    bm_sub.add_parser("sources", help="분석된 source와 production profile 연결 목록")
    bp = bm_sub.add_parser("plan", help="권리 확인된 로컬 영상·관찰 JSON에서 제작 계획 저장")
    bp.add_argument("--input", dest="input_file", required=True, help="관찰 메모 JSON 파일")
    bp.add_argument("--profile", dest="profile_id", default="kpop_observation_clip")
    bp.add_argument("--seconds", type=int, help="profile의 허용 길이, 기본 profile 설정")
    bp.add_argument("--observation-type", help="profile에 정의된 variation 이름")
    bp.add_argument("--confirm-rights", action="store_true")
    bp.add_argument("--note", default="", help="입력 영상 모두에 대한 사용 권한 근거")
    bp.add_argument("--license", dest="license_", default="my_channel", choices=("my_channel", "licensed_upload", "ai_generated"))
    bp.add_argument("--mute-source", action="store_true", help="원본 소리를 제거 (TTS 없음)")
    for command in ("inspect", "render"):
        bc = bm_sub.add_parser(command, help="저장 계획 조회" if command == "inspect" else "기존 렌더로 제작/재렌더")
        bc.add_argument("project_id", help="benchmark plan이 반환한 작업 id")
    return ap


async def _dispatch(a: argparse.Namespace) -> dict[str, Any]:
    if a.cmd == "benchmark":
        if a.benchmark_cmd == "profiles":
            return benchmark.profiles()
        if a.benchmark_cmd == "sources":
            from ..pipeline.benchmark_registry import inventory
            return {"status": "ok", **inventory(), "ai_provider_used": "none"}
        if a.benchmark_cmd == "plan":
            return await benchmark.plan(a.input_file, profile_id=a.profile_id, seconds=a.seconds,
                                        observation_type=a.observation_type, confirm_rights=a.confirm_rights,
                                        note=a.note, license_=a.license_, preserve_audio=not a.mute_source, log=_log)
        if a.benchmark_cmd == "inspect":
            return benchmark.inspect(a.project_id)
        return await benchmark.render(a.project_id, log=_log)
    if a.cmd == "make":
        script_text = a.script_text
        if a.script_file:
            with open(a.script_file, encoding="utf-8") as f:
                script_text = f.read()
        return await core.make(
            topic=a.topic, url=a.url, auto=a.auto, script_text=script_text, preset=a.preset, style=a.style,
            seconds=a.seconds, review=a.review, instructions=a.instructions, llm=a.llm, model=a.model, tts=a.tts,
            voice=a.voice, subtitles=False if a.no_subtitles else None, assets=a.asset,
            asset_rights=core._own_rights(a.license, a.note, a.confirm_rights), reference_video=a.reference_video,
            hint=a.hint, content_format=a.content_format, allow_openai=a.allow_openai,
            benchmark=a.benchmark, log=_log)
    if a.cmd == "batch":
        return await batch.make(topics=a.topics, select=a.select, candidates_id=a.candidates_id, count=a.count,
                                seconds=a.seconds, preset=a.preset, style=a.style, content_format=a.content_format,
                                review=a.review, instructions=a.instructions, llm=a.llm, model=a.model,
                                allow_openai=a.allow_openai, benchmark=a.benchmark, log=_log)
    if a.cmd == "batch-status":
        return batch.status(a.batch_id)
    if a.cmd == "batch-resume":
        return await batch.resume(a.batch_id, log=_log)
    if a.cmd == "resume":
        return await core.resume(a.project_id, log=_log)
    if a.cmd == "status":
        return core.status(a.project_id)
    if a.cmd == "inspect":
        return core.inspect(a.project_id, a.part)
    if a.cmd == "edit-scene":
        return core.edit_scene(a.project_id, a.scene, narration=a.narration, emphasis=a.emphasis)
    if a.cmd == "set-visual":
        return await core.set_visual(a.project_id, a.scene, card=a.card, file=a.file, license_=a.license,
                                     note=a.note, confirm_rights=a.confirm_rights, log=_log)
    if a.cmd == "rerender":
        return await core.rerender(a.project_id, log=_log)
    if a.cmd == "styles":
        return core.styles()
    if a.cmd == "trends":
        return await core.trends(a.limit, log=_log)
    if a.cmd == "export":
        return await core.export(a.project_id, pack=a.pack, capcut_draft=a.capcut, log=_log)
    raise core.FactoryError("invalid", f"알 수 없는 명령: {a.cmd}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):   # Windows 콘솔에서도 한글 JSON 이 깨지지 않게
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    try:
        out = asyncio.run(_dispatch(args))
        code = 1 if out.get("status") in ("failed", "partial_failure") or out.get("rerender") == "failed" else 0
    except core.FactoryError as e:
        out, code = e.as_dict(), 2
    except Exception as e:  # noqa: BLE001 - 예상 못 한 오류도 JSON 으로 알린다
        out, code = {"status": "error", "error": "unexpected", "message": f"{type(e).__name__}: {core.llmmod.safe_error(e)}"}, 1
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return code


if __name__ == "__main__":
    sys.exit(main())
