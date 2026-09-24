"""FastAPI 웹 서버. 실행: uvicorn app.main:app --reload"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import set_key
from pydantic import BaseModel

from .config import USER_ENV, env
from .jobs import JobManager
from .pipeline.assets import kind_of
from .pipeline.llm import find_claude_cli
from .pipeline.styles import analyze_references, style_to_dict

BASE = Path(__file__).resolve().parent
manager: JobManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    global manager
    manager = JobManager()
    manager.start()
    yield


app = FastAPI(title="AI Shorts", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


class CreateJob(BaseModel):
    mode: str  # topic | url | auto | upload
    input: str = ""
    preset: str
    options: dict[str, Any] = {}


class Approve(BaseModel):
    script: dict[str, Any] | None = None
    source_indexes: list[int] | None = None
    comment_ids: list[str] | None = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "presets": list(manager.presets.values()),
        "cfg": manager.cfg,
        "keys": {
            "anthropic": bool(env("ANTHROPIC_API_KEY")),
            "claude_cli": find_claude_cli() or "",
            "gemini": bool(env("GEMINI_API_KEY")),
            "hf": bool(env("HF_TOKEN")), "fal": bool(env("FAL_KEY")), "openai": bool(env("OPENAI_API_KEY")),
            "elevenlabs": bool(env("ELEVENLABS_API_KEY")), "typecast": bool(env("TYPECAST_API_KEY")),
            "naver": bool(env("NAVER_CLIENT_ID")),
            "youtube": bool(env("YOUTUBE_API_KEY")),
        },
    })


@app.get("/api/presets")
async def presets():
    return list(manager.presets.values())


@app.put("/api/presets/{preset_id}")
async def update_preset(preset_id: str, body: dict[str, Any]):
    try:
        return manager.update_preset(preset_id, body)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))


# ---------- 스타일 지침 ----------

class StyleBody(BaseModel):
    name: str = ""
    hook_pattern: str = ""
    structure: str = ""
    emotional_arc: str = ""
    tone: str = ""
    sentence_style: str = ""
    pacing: str = ""
    cta: str = ""
    notes: str = ""
    source_urls: list[str] = []


class AnalyzeBody(BaseModel):
    urls: list[str]
    hint: str = ""
    save: bool = True
    llm_provider: str = ""
    llm_model: str = ""


class OpenAIKeyBody(BaseModel):
    api_key: str


class YouTubeKeyBody(BaseModel):
    api_key: str


@app.post("/api/settings/gemini-key")
async def save_gemini_key(body: YouTubeKeyBody):
    key = body.api_key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,200}", key):
        raise HTTPException(400, "Gemini API 키를 확인해 주세요.")
    USER_ENV.parent.mkdir(parents=True, exist_ok=True)
    USER_ENV.touch(exist_ok=True)
    set_key(str(USER_ENV), "GEMINI_API_KEY", key)
    import os
    os.environ["GEMINI_API_KEY"] = key
    return {"ok": True}


@app.post("/api/settings/youtube-key")
async def save_youtube_key(body: YouTubeKeyBody):
    key = body.api_key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", key):
        raise HTTPException(400, "YouTube Data API 키를 확인해 주세요.")
    USER_ENV.parent.mkdir(parents=True, exist_ok=True)
    USER_ENV.touch(exist_ok=True)
    set_key(str(USER_ENV), "YOUTUBE_API_KEY", key)
    import os
    os.environ["YOUTUBE_API_KEY"] = key
    return {"ok": True}


@app.post("/api/settings/openai-key")
async def save_openai_key(body: OpenAIKeyBody):
    key = body.api_key.strip()
    if not key or "\n" in key or "\r" in key or len(key) > 500:
        raise HTTPException(400, "OpenAI API 키를 확인해 주세요.")
    USER_ENV.parent.mkdir(parents=True, exist_ok=True)
    USER_ENV.touch(exist_ok=True)
    set_key(str(USER_ENV), "OPENAI_API_KEY", key)
    import os

    os.environ["OPENAI_API_KEY"] = key
    return {"ok": True}


@app.get("/api/styles")
async def list_styles():
    return manager.list_styles()


@app.post("/api/styles")
async def create_style(body: StyleBody):
    if not body.name.strip():
        raise HTTPException(400, "스타일 이름을 입력하세요.")
    return manager.upsert_style(None, body.model_dump())


@app.put("/api/styles/{style_id}")
async def update_style(style_id: str, body: StyleBody):
    return manager.upsert_style(style_id, body.model_dump())


@app.delete("/api/styles/{style_id}")
async def delete_style_api(style_id: str):
    manager.remove_style(style_id)
    return {"ok": True}


@app.post("/api/styles/analyze")
async def analyze_style(body: AnalyzeBody):
    """참고 영상 URL 들을 분석해 스타일 지침 초안을 만든다. 시간이 걸리므로 UI 에서 로딩 표시 필요."""
    urls = [u.strip() for u in body.urls if u.strip()]
    if not urls:
        raise HTTPException(400, "참고 영상 URL을 1개 이상 넣어주세요.")
    if len(urls) > 5:
        raise HTTPException(400, "참고 영상은 최대 5개까지 분석할 수 있습니다.")
    for url in urls:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        valid = ((host in ("youtube.com", "www.youtube.com", "m.youtube.com")
                  and ((parsed.path == "/watch" and parse_qs(parsed.query).get("v"))
                       or (parsed.path.startswith(("/shorts/", "/live/")) and bool(parsed.path.split("/")[2]))))
                 or (host in ("youtu.be", "www.youtu.be") and parsed.path.strip("/")))
        if parsed.scheme not in ("http", "https") or not valid:
            raise HTTPException(400, f"유튜브 영상 주소를 확인해 주세요: {url}")

    llm = dict(manager.cfg["llm"])
    if body.llm_provider:
        if body.llm_provider not in ("claude", "openai", "anthropic"):
            raise HTTPException(400, "지원하지 않는 대본 AI입니다.")
        llm["provider"] = body.llm_provider
    if body.llm_model:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", body.llm_model):
            raise HTTPException(400, "AI 모델 이름을 확인해 주세요.")
        llm["model"] = body.llm_model
    elif llm["provider"] == "openai":
        llm["model"] = llm.get("openai_model", "gpt-5-mini")
    if llm["provider"] == "openai" and not env("OPENAI_API_KEY"):
        raise HTTPException(400, "GPT를 사용하려면 화면의 GPT 연결에서 OpenAI API 키를 먼저 등록해 주세요.")
    if llm["provider"] == "claude" and not find_claude_cli():
        raise HTTPException(400, "Claude Code 로그인 도구를 찾지 못했습니다.")
    workdir = manager.output / "_styles" / str(abs(hash(tuple(urls))) % 10**8)
    try:
        res = await analyze_references(llm, urls, workdir, body.hint)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"분석 실패: {e}")
    data = style_to_dict(res.profile, urls)
    if body.save:
        data = manager.upsert_style(None, data)
    return {"style": data, "findings": res.findings}


# ---------- 파일 첨부 ----------
# 잡을 만들기 전에 올릴 수 있도록 토큰별 임시 폴더에 보관했다가, 잡 생성 시 옮긴다.

@app.post("/api/uploads")
async def upload_files(token: str = Form(""), files: list[UploadFile] = File(...)):
    token = re.sub(r"[^a-zA-Z0-9_-]", "", token) or uuid.uuid4().hex[:12]
    staging = manager.output / "_uploads" / token
    staging.mkdir(parents=True, exist_ok=True)

    saved, skipped = [], []
    for f in files:
        data = await f.read()
        if len(data) > 200 * 1024 * 1024:
            skipped.append(f"{f.filename} (200MB 초과)")
            continue
        name = Path(f.filename or "file").name.replace("\\", "_")
        if kind_of(Path(name)) is None:
            skipped.append(f"{name} (지원하지 않는 형식)")
            continue
        out = staging / name
        n = 2
        while out.exists():
            out = staging / f"{Path(name).stem}_{n}{Path(name).suffix}"
            n += 1
        out.write_bytes(data)
        saved.append({"name": out.name, "kind": kind_of(out), "size": len(data)})

    return {"token": token, "saved": saved, "skipped": skipped,
            "total": len(list(staging.iterdir()))}


@app.get("/api/uploads/{token}")
async def list_uploads(token: str):
    staging = manager.output / "_uploads" / re.sub(r"[^a-zA-Z0-9_-]", "", token)
    if not staging.exists():
        return {"token": token, "files": []}
    return {"token": token, "files": [
        {"name": p.name, "kind": kind_of(p), "size": p.stat().st_size}
        for p in sorted(staging.iterdir()) if p.is_file() and kind_of(p)]}


@app.delete("/api/uploads/{token}")
async def clear_uploads(token: str, name: str = ""):
    staging = manager.output / "_uploads" / re.sub(r"[^a-zA-Z0-9_-]", "", token)
    if not staging.exists():
        return {"ok": True}
    if name:
        target = staging / Path(name).name
        target.unlink(missing_ok=True)
    else:
        shutil.rmtree(staging, ignore_errors=True)
    return {"ok": True}


@app.get("/api/jobs")
async def list_jobs():
    return manager.list()


@app.post("/api/jobs")
async def create_job(body: CreateJob):
    if body.mode not in ("topic", "url", "auto", "upload"):
        raise HTTPException(400, "mode 는 topic | url | auto | upload")
    if body.mode not in ("auto", "upload") and not body.input.strip():
        raise HTTPException(400, "입력이 비어 있습니다.")
    if body.mode == "upload":
        token = re.sub(r"[^a-zA-Z0-9_-]", "", str(body.options.get("upload_token") or ""))
        name = str(body.options.get("reference_name") or "")
        if not token or not name or Path(name).name != name or kind_of(Path(name)) != "video":
            raise HTTPException(400, "참고 영상 파일을 하나 선택해 주세요.")
        if not (manager.output / "_uploads" / token / name).is_file():
            raise HTTPException(400, "선택한 영상 파일이 업로드 목록에 없습니다.")
        body.options["visual_mode"] = "broll"
    provider = body.options.get("llm_provider") or manager.cfg["llm"]["provider"]
    if provider == "openai" and not env("OPENAI_API_KEY"):
        raise HTTPException(400, "OPENAI_API_KEY 가 .env 에 없습니다.")
    if provider == "anthropic" and not env("ANTHROPIC_API_KEY"):
        raise HTTPException(400, "ANTHROPIC_API_KEY 가 .env 에 없습니다.")
    if provider == "claude" and not find_claude_cli():
        raise HTTPException(400, "claude.exe 를 찾을 수 없습니다. README 의 Claude 로그인 안내를 확인하세요.")
    try:
        job = manager.create(body.mode, body.input.strip(), body.preset, body.options)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return job.public()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(404)
    return job.public()


@app.post("/api/jobs/{job_id}/approve")
async def approve(job_id: str, body: Approve):
    if not manager.get(job_id):
        raise HTTPException(404)
    try:
        manager.approve(job_id, body.script, body.source_indexes, body.comment_ids)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/jobs/{job_id}/scene-visual")
async def scene_visual(job_id: str, scene: int = Form(...), file: UploadFile = File(...)):
    """대본 검토 중에 특정 장면에 쓸 파일을 올린다 (Flow 에서 만든 이미지 등).

    scene_NN_ 파일명 규칙으로 저장하면 assets.plan_assets 가 그 장면에 고정 배치한다.
    """
    job = manager.get(job_id)
    if not job:
        raise HTTPException(404)
    if job.status != "awaiting_review":
        raise HTTPException(400, "대본 검토 중에만 올릴 수 있습니다.")
    if scene < 0 or scene > 99:
        raise HTTPException(400, "장면 번호가 올바르지 않습니다.")

    name = Path(file.filename or "file").name.replace("\\", "_")
    if kind_of(Path(name)) is None:
        raise HTTPException(400, f"지원하지 않는 형식입니다: {name}")

    up = manager.output / job_id / "uploads"
    up.mkdir(parents=True, exist_ok=True)
    for old in up.glob(f"scene_{scene:02d}_*"):   # 같은 장면에 다시 올리면 교체
        old.unlink(missing_ok=True)
    out = up / f"scene_{scene:02d}_{name}"
    out.write_bytes(await file.read())
    return {"ok": True, "scene": scene, "name": out.name}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    manager.delete(job_id)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/events")
async def events(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(404)
    q = manager.subscribe(job_id)

    async def gen():
        try:
            yield f"data: {json.dumps(job.public(), ensure_ascii=False)}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    if payload["status"] in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            manager.unsubscribe(job_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/files/{job_id}/{name}")
async def files(job_id: str, name: str):
    p = manager.output / job_id / name
    if not p.exists() or ".." in name:
        raise HTTPException(404)
    return FileResponse(p)
