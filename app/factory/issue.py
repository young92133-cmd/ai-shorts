"""`issue` 명령: 사진 편집형 이슈 쇼츠 (기획서 → AI 사진[Flow]·실제 사진[캡처] → 편집).

    issue new --plan-file plan.json                 # 기획서 검증 후 프로젝트 생성 (issue_prompts.md 함께)
    issue update [id] --plan-file plan.json
    issue status [id]                               # 사진별 준비 상태
    issue prompts [id] [--photo P03]                # Flow 에 넣을 AI 사진 문장 / 캡처할 실제 사진 목록
    issue photo [id] --photo P03 --file 이미지        # Flow 에서 받은 이미지·브라우저 캡처 넣기
    issue photo [id] --photo P05 --youtube URL --at 12.5   # 유튜브 영상 그 시각 프레임
    issue photo [id] --photo P06 --image-url URL    # 기사 대표 사진 주소
    issue photo [id] --from 다운로드폴더 [--since-minutes 30]  # 'P01…' 이름 파일 한꺼번에
    issue assemble [id] [--no-sfx]                  # 나레이션·자막·사진 띠 편집 → final.mp4
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..config import load_config
from ..pipeline import issueshorts as iss
from . import core


def _output() -> Path:
    return Path(load_config()["paths"]["output"])


def _job(project_id: str | None) -> Path:
    out = _output()
    if project_id:
        d = out / project_id
        if not (d / iss.PLAN_FILE).is_file():
            raise core.FactoryError("not_found", f"이슈 쇼츠 프로젝트가 아닙니다: {project_id}")
        return d
    found = sorted(p.parent for p in out.glob(f"*/{iss.PLAN_FILE}"))
    if not found:
        raise core.FactoryError("not_found", "이슈 쇼츠 프로젝트가 없습니다. 먼저 issue new --plan-file 로 만드세요.")
    return found[-1]


def _read_plan(path: str) -> tuple[iss.IssuePlan, list[str]]:
    p = Path(path)
    if not p.is_file():
        raise core.FactoryError("invalid", f"기획서 파일이 없습니다: {path}")
    try:
        plan = iss.IssuePlan.model_validate_json(p.read_text(encoding="utf-8-sig"))
    except ValidationError as e:
        raise core.FactoryError("invalid", "issue_plan 형식 오류", details=[f"{'.'.join(map(str, x['loc']))}: {x['msg']}"
                                                                     for x in e.errors()][:20]) from e
    errors, warnings = iss.check_plan(plan)
    if errors:
        raise core.FactoryError("invalid", "기획서 검수 실패 — 고친 뒤 다시 실행하세요", errors=errors, warnings=warnings)
    return plan, warnings


def _summary(job: Path) -> dict[str, Any]:
    plan = iss.load_plan(job)
    state = iss.read_state(job)
    return {"status": "ok", "project_id": job.name, "project_dir": str(job), "topic": plan.topic,
            "prompts_file": str(job / iss.PROMPTS_FILE), "flow_url": state.get("flow_url", ""),
            "stage": state.get("stage", "plan"), "estimated_seconds": iss.estimate_seconds(plan),
            **iss.photo_status(job, plan), "ai_provider_used": "none"}


def new(plan_file: str) -> dict[str, Any]:
    plan, warnings = _read_plan(plan_file)
    job = _output() / f"{core._new_id()}_issue"
    iss.save_plan(job, plan)
    iss.mark(job, stage="plan")
    return {**_summary(job), "warnings": warnings}


def update(project_id: str | None, plan_file: str) -> dict[str, Any]:
    job = _job(project_id)
    plan, warnings = _read_plan(plan_file)
    iss.save_plan(job, plan)
    return {**_summary(job), "warnings": warnings}


def prompts(project_id: str | None, photo: str | None) -> dict[str, Any]:
    job = _job(project_id)
    plan = iss.load_plan(job)
    items = [p for p in plan.photos if not photo or p.id == photo]
    if photo and not items:
        raise core.FactoryError("invalid", f"없는 사진 id: {photo}")
    out = []
    for p in items:
        d: dict[str, Any] = {"photo": p.id, "kind": p.kind, "desc": p.desc,
                             "ready": iss.photo_path(job, p.id) is not None}
        if p.kind == "ai":
            d["flow_prompt"] = iss.flow_prompt(plan, p)
        else:
            d["source"] = p.source.model_dump() if p.source else None
            d["hide_note"] = p.hide_note
        out.append(d)
    return {"status": "ok", "project_id": job.name, "photos": out}


def note(project_id: str | None, flow_url: str) -> dict[str, Any]:
    job = _job(project_id)
    iss.mark(job, flow_url=flow_url)
    return _summary(job)


async def photo(project_id: str | None, pid: str | None, file: str | None, youtube: str | None,
                at: float | None, image_url: str | None, from_dir: str | None,
                since_minutes: float | None) -> dict[str, Any]:
    job = _job(project_id)
    try:
        if from_dir:
            since = time.time() - since_minutes * 60 if since_minutes else None
            res = iss.add_from_dir(job, Path(from_dir), since)
        else:
            if not pid:
                raise core.FactoryError("invalid", "--photo P01 처럼 사진 id 가 필요합니다")
            if file:
                res = iss.add_file(job, pid, Path(file))
            elif image_url:
                res = iss.add_image_url(job, pid, image_url)
            else:
                res = await iss.add_youtube(job, pid, youtube, at)
    except iss.IssueError as e:
        raise core.FactoryError("invalid", str(e)) from e
    except OSError as e:
        raise core.FactoryError("invalid", f"사진을 받지 못했습니다: {e}") from e
    return {"status": "ok", "project_id": job.name, **res, **iss.photo_status(job)}


async def assemble(project_id: str | None, sfx: bool, log=print) -> dict[str, Any]:
    job = _job(project_id)
    status = iss.photo_status(job)
    if not status["ready"]:
        raise core.FactoryError("not_ready", f"아직 없는 사진: AI {status['missing_ai']} · 실제 {status['missing_real']}",
                                **status)
    from ..config import merge_options
    cfg = merge_options(load_config(), {}, {})
    try:
        res = await iss.assemble(job, cfg, sfx=sfx, log=log)
    except Exception as e:  # noqa: BLE001
        iss.mark(job, stage="assemble_failed", error=str(e)[:300])
        return {"status": "failed", "project_id": job.name, "failed_at": "assemble", "message": str(e)[:500],
                "next_action": "issue assemble"}
    return {"status": "ok", "project_id": job.name, **res, "ai_provider_used": "none"}


def add_parser(sub):
    p = sub.add_parser("issue", help="사진 편집형 이슈 쇼츠 (AI 사진=Flow, 실제 사진=캡처 → 편집)")
    c = p.add_subparsers(dest="issue_cmd", required=True)
    n = c.add_parser("new", help="기획서(issue_plan.json) 검증 후 프로젝트 생성")
    n.add_argument("--plan-file", required=True)
    u = c.add_parser("update", help="기획서 고치기")
    u.add_argument("project_id", nargs="?")
    u.add_argument("--plan-file", required=True)
    s = c.add_parser("status", help="사진별 준비 상태")
    s.add_argument("project_id", nargs="?")
    pr = c.add_parser("prompts", help="Flow 사진 문장 / 캡처 목록")
    pr.add_argument("project_id", nargs="?")
    pr.add_argument("--photo")
    no = c.add_parser("note", help="Flow 프로젝트 주소 기억")
    no.add_argument("project_id", nargs="?")
    no.add_argument("--flow-url", required=True)
    ph = c.add_parser("photo", help="사진 넣기 (파일·유튜브 프레임·이미지 주소·다운로드 폴더)")
    ph.add_argument("project_id", nargs="?")
    ph.add_argument("--photo", dest="pid")
    src = ph.add_mutually_exclusive_group(required=True)
    src.add_argument("--file")
    src.add_argument("--youtube", nargs="?", const="", help="유튜브 주소(생략하면 기획서 source.url)")
    src.add_argument("--image-url")
    src.add_argument("--from", dest="from_dir")
    ph.add_argument("--at", type=float, help="유튜브 프레임 시각(초)")
    ph.add_argument("--since-minutes", type=float)
    a = c.add_parser("assemble", help="사진 + 나레이션 + 자막 → final.mp4")
    a.add_argument("project_id", nargs="?")
    a.add_argument("--no-sfx", action="store_true")
    return p


async def dispatch(a, log=print) -> dict[str, Any]:
    cmd = a.issue_cmd
    if cmd == "new":
        return new(a.plan_file)
    if cmd == "update":
        return update(a.project_id, a.plan_file)
    if cmd == "status":
        return _summary(_job(a.project_id))
    if cmd == "prompts":
        return prompts(a.project_id, a.photo)
    if cmd == "note":
        return note(a.project_id, a.flow_url)
    if cmd == "photo":
        if a.youtube is not None:   # --youtube 만 주면 기획서의 source.url 을 쓴다
            return await photo(a.project_id, a.pid, None, a.youtube or None, a.at, None, None, None)
        return await photo(a.project_id, a.pid, a.file, None, None, a.image_url, a.from_dir, a.since_minutes)
    if cmd == "assemble":
        return await assemble(a.project_id, not a.no_sfx, log=log)
    raise core.FactoryError("invalid", "지원하지 않는 issue 명령")
