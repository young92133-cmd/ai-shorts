"""스튜디오 웹 경로 (/studio, /api/studio/...). app/main.py 가 이 router 를 붙인다.

혼자 쓰는 로컬 프로그램이라 작업 목록은 메모리에만 둔다. 오래 걸리는 제작은 별도 스레드에서 돌려 화면이 멈추지 않게 한다.
"""
from __future__ import annotations

import asyncio
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from ..carousel import characters as charmod
from ..carousel.schema import CAROUSEL_FORMATS
from ..carousel.templates import list_templates
from ..factory import core
from ..factory.core import FactoryError
from . import project as studio

router = APIRouter()
PAGE = Path(__file__).resolve().parent / "studio.html"
FILE_RE = re.compile(r"^(card_\d{2}\.png|[A-Za-z0-9_-]+\.zip)$")
TASKS: dict[str, dict[str, Any]] = {}


class CreateBody(BaseModel):
    topic: str
    format: str = "card_news"
    pages: int = 8
    template: str = ""
    character: str = ""
    image_search: bool = True
    instructions: str = ""


def _err(e: Exception) -> HTTPException:
    if isinstance(e, FactoryError):
        return HTTPException(404 if e.code == "not_found" else 400, e.message)
    return HTTPException(500, f"{type(e).__name__}: {e}")


async def _in_thread(coro_fn, *args, **kwargs):
    """Pillow 렌더·Claude 호출이 서버 이벤트 루프를 막지 않게 별도 스레드의 새 루프에서 실행."""
    return await asyncio.to_thread(lambda: asyncio.run(coro_fn(*args, **kwargs)))


@router.get("/studio", response_class=HTMLResponse)
async def page():
    return HTMLResponse(PAGE.read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache"})   # 화면을 고치면 바로 반영


@router.get("/api/studio/choices")
async def choices():
    return {"formats": list(CAROUSEL_FORMATS), "templates": list_templates(),
            "characters": [{"id": c.id, "name": c.name} for c in charmod.list_characters()],
            "pages": list(range(6, 11))}


@router.get("/api/studio/projects")
async def projects():
    return studio.list_projects()


@router.post("/api/studio/projects")
async def create(body: CreateBody):
    if body.format not in CAROUSEL_FORMATS:
        raise HTTPException(400, "형식을 다시 골라 주세요.")
    if not body.topic.strip():
        raise HTTPException(400, "주제를 입력해 주세요.")
    if not 6 <= body.pages <= 10:
        raise HTTPException(400, "장수는 6~10 입니다.")
    if any(t["status"] == "running" for t in TASKS.values()):
        raise HTTPException(409, "이미 만들고 있는 작업이 있습니다. 끝난 뒤 다시 눌러 주세요.")
    tid = uuid.uuid4().hex[:8]
    task: dict[str, Any] = {"id": tid, "status": "running", "log": [], "result": None, "topic": body.topic.strip()}
    TASKS[tid] = task

    def log(msg: str) -> None:
        task["log"] = (task["log"] + [str(msg)])[-30:]

    async def run():
        try:
            out = await _in_thread(studio.create, body.topic, fmt=body.format, pages=body.pages,
                                   template=body.template, character=body.character,
                                   image_search=body.image_search, instructions=body.instructions, log=log)
            task.update(status="done" if out.get("status") == "render_complete" else "error", result=out)
        except Exception as e:  # noqa: BLE001 - 화면에 이유를 보여 준다
            task.update(status="error", result={"message": e.message if isinstance(e, FactoryError) else str(e)})

    asyncio.create_task(run())
    return task


@router.get("/api/studio/tasks/{tid}")
async def task_status(tid: str):
    if tid not in TASKS:
        raise HTTPException(404)
    return TASKS[tid]


@router.get("/api/studio/projects/{pid}")
async def get_project(pid: str):
    try:
        return studio.load(pid)
    except Exception as e:  # noqa: BLE001
        raise _err(e)


class PageEdit(BaseModel):
    fields: dict[str, Any] = {}


@router.post("/api/studio/projects/{pid}/pages/{n}")
async def edit_page(pid: str, n: int, body: PageEdit):
    try:
        return await _in_thread(studio.update_page, pid, n, body.fields)
    except Exception as e:  # noqa: BLE001
        raise _err(e)


@router.post("/api/studio/projects/{pid}/pages/{n}/vary")
async def vary(pid: str, n: int):
    try:
        return await _in_thread(studio.vary_scene, pid, n)
    except Exception as e:  # noqa: BLE001
        raise _err(e)


class PageMove(BaseModel):
    to: int


class PageAdd(BaseModel):
    after: int
    kind: str = "card"     # card | comic


@router.post("/api/studio/projects/{pid}/pages/{n}/move")
async def move(pid: str, n: int, body: PageMove):
    try:
        return await _in_thread(studio.move_page, pid, n, body.to)
    except Exception as e:  # noqa: BLE001
        raise _err(e)


@router.post("/api/studio/projects/{pid}/pages/{n}/delete")
async def delete(pid: str, n: int):
    try:
        return await _in_thread(studio.delete_page, pid, n)
    except Exception as e:  # noqa: BLE001
        raise _err(e)


@router.post("/api/studio/projects/{pid}/pages-add")
async def add(pid: str, body: PageAdd):
    if body.kind not in ("card", "comic"):
        raise HTTPException(400, "kind 는 card | comic 입니다.")
    try:
        return await _in_thread(studio.add_page, pid, body.after, body.kind)
    except Exception as e:  # noqa: BLE001
        raise _err(e)


@router.post("/api/studio/projects/{pid}/undo")
async def undo(pid: str):
    try:
        return await _in_thread(studio.undo, pid)
    except Exception as e:  # noqa: BLE001
        raise _err(e)


@router.post("/api/studio/projects/{pid}/redo")
async def redo(pid: str):
    try:
        return await _in_thread(studio.redo, pid)
    except Exception as e:  # noqa: BLE001
        raise _err(e)


@router.post("/api/studio/projects/{pid}/pages/{n}/image")
async def upload_image(pid: str, n: int, file: UploadFile = File(...), confirm_rights: bool = Form(False)):
    """카드 n 에 PC 이미지를 넣는다(교체). 임시 파일로 받은 뒤 프로젝트 uploads/studio/ 로 복사한다."""
    data = await file.read(studio.MAX_UPLOAD + 1)     # 한도는 엔진(project.MAX_UPLOAD) 하나
    if len(data) > studio.MAX_UPLOAD:
        raise HTTPException(400, "이미지는 20MB 이하만 넣을 수 있습니다.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "upload"
        src.write_bytes(data)
        try:
            return await _in_thread(studio.set_image, pid, n, src, file.filename or "image.png", confirm_rights=confirm_rights)
        except Exception as e:  # noqa: BLE001
            raise _err(e)


@router.post("/api/studio/projects/{pid}/pages/{n}/image-clear")
async def clear_image(pid: str, n: int):
    try:
        return await _in_thread(studio.clear_image, pid, n)
    except Exception as e:  # noqa: BLE001
        raise _err(e)


@router.post("/api/studio/projects/{pid}/export")
async def export(pid: str):
    try:
        path = studio.export_zip(pid)
    except Exception as e:  # noqa: BLE001
        raise _err(e)
    return {"file": f"{path.parent.name}/{path.name}", "path": str(path)}


@router.get("/api/studio/files/{pid}/{fmt}/{name}")
async def files(pid: str, fmt: str, name: str):
    if fmt not in CAROUSEL_FORMATS or not FILE_RE.match(name) or not core.PID_RE.match(pid):
        raise HTTPException(404)
    p = core.output_root() / pid / fmt / name
    if not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, filename=name if name.endswith(".zip") else None)
