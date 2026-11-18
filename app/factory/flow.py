"""`flow` 명령: Google Flow 공학 쇼츠 (기획서 → Flow 생성[브라우저] → 클립 받기 → 편집).

    flow new --plan-file plan.json          # 기획서 검증 후 프로젝트 생성 (flow_prompts.md 함께)
    flow update [id] --plan-file plan.json  # 기획서 고치기
    flow status [id]                        # 장면별 클립 유무, 다음 장면
    flow prompts [id] --scene 3             # 그 장면의 CLEAN/INFO/영상 프롬프트 (브라우저 자동화가 씀)
    flow note [id] --flow-url URL           # Flow 프로젝트 주소 기억
    flow import [id] --scene 3 --file 영상.mp4
    flow import [id] --from 다운로드폴더 [--since-minutes 30]
    flow assemble [id] [--clip-volume 0.12] [--no-subtitles]
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..config import load_config
from ..pipeline import flowshorts as fs
from . import core


def _output() -> Path:
    return Path(load_config()["paths"]["output"])


def _job(project_id: str | None) -> Path:
    out = _output()
    if project_id:
        d = out / project_id
        if not (d / fs.PLAN_FILE).is_file():
            raise core.FactoryError("not_found", f"Flow 프로젝트가 아닙니다: {project_id}")
        return d
    found = sorted(p.parent for p in out.glob(f"*/{fs.PLAN_FILE}"))
    if not found:
        raise core.FactoryError("not_found", "Flow 프로젝트가 없습니다. 먼저 flow new --plan-file 로 만드세요.")
    return found[-1]


def _read_plan(path: str) -> fs.FlowPlan:
    p = Path(path)
    if not p.is_file():
        raise core.FactoryError("invalid", f"기획서 파일이 없습니다: {path}")
    try:
        plan = fs.FlowPlan.model_validate_json(p.read_text(encoding="utf-8-sig"))
    except ValidationError as e:
        raise core.FactoryError("invalid", "flow_plan 형식 오류", details=[f"{'.'.join(map(str, x['loc']))}: {x['msg']}"
                                                                    for x in e.errors()][:20]) from e
    errors, warnings = fs.check_plan(plan)
    if errors:
        raise core.FactoryError("invalid", "기획서 검수 실패 — 고친 뒤 다시 실행하세요", errors=errors, warnings=warnings)
    plan._warnings = warnings  # type: ignore[attr-defined]
    return plan


def _summary(job: Path) -> dict[str, Any]:
    plan = fs.load_plan(job)
    state = fs._read_state(job)
    return {"status": "ok", "project_id": job.name, "project_dir": str(job), "topic": plan.topic,
            "prompts_file": str(job / fs.PROMPTS_FILE), "flow_url": state.get("flow_url", ""),
            "stage": state.get("stage", "plan"), **fs.clip_status(job, plan), "ai_provider_used": "none"}


def new(plan_file: str) -> dict[str, Any]:
    plan = _read_plan(plan_file)
    job = _output() / f"{core._new_id()}_flow"
    fs.save_plan(job, plan)
    fs.mark(job, stage="plan")
    return {**_summary(job), "warnings": plan._warnings}  # type: ignore[attr-defined]


def update(project_id: str | None, plan_file: str) -> dict[str, Any]:
    job = _job(project_id)
    plan = _read_plan(plan_file)
    fs.save_plan(job, plan)
    return {**_summary(job), "warnings": plan._warnings}  # type: ignore[attr-defined]


def prompts(project_id: str | None, scene: int) -> dict[str, Any]:
    job = _job(project_id)
    plan = fs.load_plan(job)
    sc = next((s for s in plan.scenes if s.index == scene), None)
    if sc is None:
        raise core.FactoryError("invalid", f"없는 장면 번호입니다: {scene} (1~{len(plan.scenes)})")
    return {"status": "ok", "project_id": job.name, "scene": scene, "narration": sc.narration,
            "shots": [{"shot": s.shot, "role": s.role, "clean_prompt": s.clean_prompt,
                       "info_prompt": s.info_prompt or None} for s in sc.shots],
            "video_prompt": sc.video_prompt, "clip_exists": fs.clip_path(job, scene).is_file()}


def note(project_id: str | None, flow_url: str) -> dict[str, Any]:
    job = _job(project_id)
    fs.mark(job, flow_url=flow_url)
    return _summary(job)


def import_(project_id: str | None, scene: int | None, file: str | None, from_dir: str | None,
            since_minutes: float | None) -> dict[str, Any]:
    job = _job(project_id)
    if file and scene is None:
        raise core.FactoryError("invalid", "--file 에는 --scene 번호가 필요합니다")
    since = time.time() - since_minutes * 60 if since_minutes else None
    try:
        res = fs.import_clips(job, scene=scene, file=Path(file) if file else None,
                              from_dir=Path(from_dir) if from_dir else None, since=since)
    except fs.FlowError as e:
        raise core.FactoryError("invalid", str(e)) from e
    return {"status": "ok", "project_id": job.name, **res}


async def assemble(project_id: str | None, clip_volume: float, subtitles: bool, log=print) -> dict[str, Any]:
    job = _job(project_id)
    if not 0 <= clip_volume <= 1:
        raise core.FactoryError("invalid", "--clip-volume 은 0~1 입니다")
    status = fs.clip_status(job)
    if not status["ready"]:
        raise core.FactoryError("not_ready", f"아직 영상이 없는 장면: {status['missing']}", **status)
    from ..config import merge_options
    cfg = merge_options(load_config(), {}, {})   # tts.voice 등 기본값 채우기 (프리셋 없음)
    try:
        res = await fs.assemble(job, cfg, clip_volume=clip_volume, subtitles=subtitles, log=log)
    except Exception as e:  # noqa: BLE001
        fs.mark(job, stage="assemble_failed", error=str(e)[:300])
        return {"status": "failed", "project_id": job.name, "failed_at": "assemble", "message": str(e)[:500],
                "next_action": "flow assemble"}
    return {"status": "ok", "project_id": job.name, **res, "ai_provider_used": "none"}


def add_parser(sub):
    p = sub.add_parser("flow", help="Google Flow 공학 쇼츠 (기획서 → Flow 생성 → 클립 → 편집)")
    c = p.add_subparsers(dest="flow_cmd", required=True)
    n = c.add_parser("new", help="기획서(flow_plan.json) 검증 후 프로젝트 생성")
    n.add_argument("--plan-file", required=True)
    u = c.add_parser("update", help="기획서 고치기")
    u.add_argument("project_id", nargs="?")
    u.add_argument("--plan-file", required=True)
    s = c.add_parser("status", help="장면별 클립 유무")
    s.add_argument("project_id", nargs="?")
    pr = c.add_parser("prompts", help="장면 프롬프트")
    pr.add_argument("project_id", nargs="?")
    pr.add_argument("--scene", type=int, required=True)
    no = c.add_parser("note", help="Flow 프로젝트 주소 기억")
    no.add_argument("project_id", nargs="?")
    no.add_argument("--flow-url", required=True)
    im = c.add_parser("import", help="내려받은 Flow 영상을 장면 자리에")
    im.add_argument("project_id", nargs="?")
    im.add_argument("--scene", type=int)
    src = im.add_mutually_exclusive_group(required=True)
    src.add_argument("--file")
    src.add_argument("--from", dest="from_dir")
    im.add_argument("--since-minutes", type=float)
    a = c.add_parser("assemble", help="클립 + 내레이션 + 자막 → final.mp4")
    a.add_argument("project_id", nargs="?")
    a.add_argument("--clip-volume", type=float, default=0.12)
    a.add_argument("--no-subtitles", action="store_true")
    return p


async def dispatch(a, log=print) -> dict[str, Any]:
    cmd = a.flow_cmd
    if cmd == "new":
        return new(a.plan_file)
    if cmd == "update":
        return update(a.project_id, a.plan_file)
    if cmd == "status":
        return _summary(_job(a.project_id))
    if cmd == "prompts":
        return prompts(a.project_id, a.scene)
    if cmd == "note":
        return note(a.project_id, a.flow_url)
    if cmd == "import":
        return import_(a.project_id, a.scene, a.file, a.from_dir, a.since_minutes)
    if cmd == "assemble":
        return await assemble(a.project_id, a.clip_volume, not a.no_subtitles, log=log)
    raise core.FactoryError("invalid", "지원하지 않는 flow 명령")
