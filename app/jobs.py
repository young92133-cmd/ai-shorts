"""잡 큐: 한 번에 하나씩 순차 실행, SSE 로 진행상황 전달, 상태는 output/<id>/job.json 에 저장."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import shutil
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import load_config, load_presets, merge_options, save_preset
from .pipeline.assets import move_uploads
from .pipeline.models import Script
from .pipeline.run import rerender, run_pipeline
from .pipeline.styles import delete_style, load_styles, nfc, save_style


@dataclass
class Job:
    id: str
    mode: str
    input: str
    preset: str
    options: dict[str, Any]
    status: str = "queued"  # queued | running | awaiting_review | done | error
    stage: str = "queued"
    pct: int = 0
    message: str = "대기 중"
    created: str = field(default_factory=lambda: dt.datetime.now().isoformat(timespec="seconds"))
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    logs: list[str] = field(default_factory=list)
    script: dict[str, Any] | None = None
    review_choices: dict[str, Any] = field(default_factory=dict)
    _review_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id, "mode": self.mode, "input": self.input, "preset": self.preset, "options": self.options,
            "status": self.status, "stage": self.stage, "pct": self.pct, "message": self.message,
            "created": self.created, "error": self.error, "logs": self.logs[-40:], "script": self.script,
            "result": {k: v for k, v in self.result.items() if k in ("video", "thumb", "meta", "duration", "topic", "docs", "trend", "segments", "source", "visuals", "reference", "source_candidates", "comment_candidates", "selected_comments", "suggested_comment_ids", "final_sources", "timeline", "exports", "rendered_at")},
        }


TTS_PROVIDERS = ("edge", "openai", "elevenlabs", "typecast")
SCENE_FILE = re.compile(r"^scene_(\d{2})_(.+)$")


class JobManager:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.presets = load_presets(self.cfg)
        self.styles = load_styles(self.cfg)
        self.jobs: dict[str, Job] = {}
        self.queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()   # (job_id, "run" | "rerender")
        self.output = Path(self.cfg["paths"]["output"])
        self.output.mkdir(parents=True, exist_ok=True)
        self._worker: asyncio.Task | None = None
        self._load_from_disk()

    # ---------- 영속화 ----------
    def _job_dir(self, job_id: str) -> Path:
        return self.output / job_id

    def _save(self, job: Job) -> None:
        d = self._job_dir(job.id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "job.json").write_text(json.dumps(job.public(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_from_disk(self) -> None:
        for p in sorted(self.output.glob("*/job.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                job = Job(id=data["id"], mode=data["mode"], input=data["input"], preset=data["preset"],
                          options=data.get("options", {}), status=data["status"], stage=data.get("stage", ""),
                          pct=data.get("pct", 0), message=data.get("message", ""), created=data.get("created", ""),
                          result=data.get("result", {}), error=data.get("error", ""), logs=data.get("logs", []),
                          script=data.get("script"), review_choices=data.get("review_choices", {}))
                if job.status in ("queued", "running", "awaiting_review"):
                    job.status, job.message = "error", "서버 재시작으로 중단됨"
                self.jobs[job.id] = job
            except Exception:
                continue

    # ---------- 공개 API ----------
    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._loop())

    def list(self) -> list[dict[str, Any]]:
        return [j.public() for j in sorted(self.jobs.values(), key=lambda j: j.created, reverse=True)]

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def create(self, mode: str, input_text: str, preset: str, options: dict[str, Any]) -> Job:
        if preset not in self.presets:
            raise ValueError(f"프리셋 없음: {preset}")
        job_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
        job = Job(id=job_id, mode=mode, input=input_text, preset=preset, options=options)
        self.jobs[job_id] = job
        self._save(job)
        self.queue.put_nowait((job_id, "run"))
        return job

    def job_dir(self, job_id: str) -> Path:
        return self._job_dir(job_id)

    def request_rerender(self, job_id: str) -> Job:
        """⑦ 에서 고친 자막·댓글로 영상만 다시 만든다. 완료된 잡만 가능."""
        job = self.jobs[job_id]
        if job.status != "done":
            raise ValueError("완성된 영상만 다시 만들 수 있습니다.")
        job.status, job.stage, job.pct, job.message = "queued", "render", 0, "다시 만들기 대기 중"
        self._emit(job)
        self.queue.put_nowait((job_id, "rerender"))
        return job

    def touch_result(self, job_id: str, **updates: Any) -> None:
        """내보내기 결과 등 result 일부를 갱신하고 저장한다."""
        job = self.jobs[job_id]
        job.result.update(updates)
        self._save(job)

    def update_preset(self, preset_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        data = save_preset(self.cfg, preset_id, updates)
        self.presets = load_presets(self.cfg)
        return data

    # ---------- 스타일 ----------
    def list_styles(self) -> list[dict[str, Any]]:
        return list(self.styles.values())

    def upsert_style(self, style_id: str | None, data: dict[str, Any]) -> dict[str, Any]:
        saved = save_style(self.cfg, style_id, data)
        self.styles = load_styles(self.cfg)
        return saved

    def remove_style(self, style_id: str) -> None:
        delete_style(self.cfg, style_id)
        self.styles = load_styles(self.cfg)

    def approve(self, job_id: str, script_data: dict[str, Any] | None,
                source_indexes: list[int] | None = None, comment_ids: list[str] | None = None,
                tts_provider: str = "", voice: str = "", scene_map: list[int] | None = None) -> None:
        job = self.jobs[job_id]
        if job.status != "awaiting_review":
            raise ValueError("대본 검토 대기 상태가 아닙니다.")
        if tts_provider and tts_provider not in TTS_PROVIDERS:
            raise ValueError("지원하지 않는 음성 종류입니다.")
        if voice and not re.fullmatch(r"[A-Za-z0-9 ._:-]{1,100}", voice):
            raise ValueError("목소리 이름을 확인해 주세요.")
        n_orig = len((job.script or {}).get("scenes") or [])
        if scene_map is not None and (len(set(scene_map)) != len(scene_map)
                                      or any(not isinstance(i, int) or not 0 <= i < n_orig for i in scene_map)):
            raise ValueError("장면 순서 정보가 올바르지 않습니다.")
        if script_data:
            new_script = Script.model_validate(script_data).model_dump()
            if scene_map is not None and len(scene_map) != len(new_script["scenes"]):
                raise ValueError("장면 순서 정보와 대본 장면 수가 다릅니다.")
            job.script = new_script
        if scene_map is not None:
            self._remap_scene_files(job_id, scene_map)
        if tts_provider:
            job.review_choices["tts_provider"] = tts_provider
        if voice:
            job.review_choices["voice"] = voice
        sources = job.result.get("source_candidates", [])
        comments = job.result.get("comment_candidates", [])
        if source_indexes is not None:
            if any(not isinstance(i, int) or i < 0 or i >= len(sources) for i in source_indexes):
                raise ValueError("영상 후보 선택이 올바르지 않습니다.")
            job.review_choices["source_indexes"] = list(dict.fromkeys(source_indexes))
        if comment_ids is not None:
            valid = {c["id"] for c in comments}
            if len(comment_ids) > 2 or any(c not in valid for c in comment_ids):
                raise ValueError("댓글은 후보 중 최대 2개까지 선택해 주세요.")
            job.review_choices["comment_ids"] = list(dict.fromkeys(comment_ids))
        job._review_event.set()

    def _remap_scene_files(self, job_id: str, scene_map: list[int]) -> None:
        """검토 중 장면을 지우면 뒤 장면 번호가 당겨진다. scene_NN_ 고정 파일도 새 번호로 옮긴다.

        scene_map[새 번호] = 원래 번호. 지워진 장면의 파일은 _removed_ 로 바꿔 배치에서 빠지게 한다.
        """
        up = self._job_dir(job_id) / "uploads"
        if not up.is_dir():
            return
        new_of = {orig: new for new, orig in enumerate(scene_map)}
        staged: list[tuple[Path, str]] = []
        for p in list(up.iterdir()):
            m = SCENE_FILE.match(p.name)
            if not p.is_file() or not m:
                continue
            orig, rest = int(m.group(1)), m.group(2)
            if orig not in new_of:
                p.replace(up / f"_removed_{p.name}")
            elif new_of[orig] != orig:
                tmp = up / f"_remap_{p.name}"
                p.replace(tmp)                       # 이름이 겹치지 않게 두 단계로 옮긴다
                staged.append((tmp, f"scene_{new_of[orig]:02d}_{rest}"))
        for tmp, name in staged:
            tmp.replace(up / name)

    def delete(self, job_id: str) -> None:
        job = self.jobs.pop(job_id, None)
        if job and job.status not in ("running", "awaiting_review"):
            shutil.rmtree(self._job_dir(job_id), ignore_errors=True)

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.jobs[job_id]._subscribers.append(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        job = self.jobs.get(job_id)
        if job and q in job._subscribers:
            job._subscribers.remove(q)

    # ---------- 내부 ----------
    def _emit(self, job: Job) -> None:
        payload = job.public()
        for q in list(job._subscribers):
            q.put_nowait(payload)

    def _progress(self, job: Job):
        def fn(stage: str, pct: int, msg: str) -> None:
            job.stage, job.message = stage, msg
            if pct:
                job.pct = pct
            job.logs.append(f"[{stage}] {msg}")
            self._emit(job)
        return fn

    def _review(self, job: Job):
        async def fn(script: Script, preview: dict[str, Any]) -> tuple[Script, dict[str, Any]]:
            job.script = script.model_dump()
            job.result.update(preview)
            job.status, job.message = "awaiting_review", "대본을 확인하고 '렌더링 시작'을 눌러주세요"
            self._save(job)
            self._emit(job)
            job._review_event.clear()
            await job._review_event.wait()
            job.status, job.message = "running", "대본 확정"
            self._emit(job)
            return Script.model_validate(job.script), job.review_choices
        return fn

    async def _rerender(self, job: Job) -> None:
        job.status, job.stage, job.pct, job.message = "running", "render", 5, "다시 만들기 시작"
        self._emit(job)
        try:
            run_cfg = merge_options(self.cfg, self.presets.get(job.preset, {}), job.options)
            res = await rerender(self._job_dir(job.id), run_cfg, progress=self._progress(job))
            job.result.update(res, rendered_at=dt.datetime.now().isoformat(timespec="seconds"))
            job.message = "다시 만들기 완료"
        except Exception as e:  # noqa: BLE001 - 실패해도 기존 final.mp4 는 그대로 남는다
            job.message = f"다시 만들기 실패 (기존 영상은 그대로): {type(e).__name__}: {e}"
            job.logs.append(traceback.format_exc()[-1500:])
        job.status, job.stage, job.pct = "done", "done", 100
        self._save(job)
        self._emit(job)

    async def _loop(self) -> None:
        while True:
            job_id, action = await self.queue.get()
            job = self.jobs.get(job_id)
            if not job:
                continue
            if action == "rerender":
                await self._rerender(job)
                continue
            job.status, job.message = "running", "시작"
            self._emit(job)
            try:
                # 잡 생성 전에 올려둔 첨부 파일을 잡 폴더로 옮긴다
                if token := job.options.get("upload_token"):
                    staging = self.output / "_uploads" / re.sub(r"[^a-zA-Z0-9_-]", "", str(token))
                    moved = move_uploads(staging, self._job_dir(job.id))
                    if moved:
                        job.logs.append(f"[images] 첨부 {moved}개 준비됨")

                run_cfg = merge_options(self.cfg, self.presets[job.preset], job.options)
                result = await run_pipeline(
                    self._job_dir(job.id), job.mode, job.input, run_cfg,
                    progress=self._progress(job),
                    review=self._review(job) if job.options.get("review") else None,
                    clip_mode=bool(job.options.get("clip_mode")),
                    instructions=str(job.options.get("instructions") or ""),
                    style=self.styles.get(nfc(job.options.get("style_id") or "")),
                    visual_mode=str(job.options.get("visual_mode") or ""),
                    reference_name=str(job.options.get("reference_name") or ""),
                )
                job.result = result
                result["rendered_at"] = dt.datetime.now().isoformat(timespec="seconds")
                if result.get("script"):
                    job.script = result["script"]
                job.status, job.stage, job.pct, job.message = "done", "done", 100, "완료"
            except Exception as e:  # noqa: BLE001
                job.status, job.stage = "error", "error"
                job.error = f"{type(e).__name__}: {e}"
                job.message = job.error
                job.logs.append(traceback.format_exc()[-1500:])
            self._save(job)
            self._emit(job)
