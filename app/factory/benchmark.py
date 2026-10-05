"""Benchmark CLI orchestration, isolated from V1 make/resume/latest projects.

Local files only. No research, downloads, LLM, image API or TTS calls.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path

from ..pipeline import benchmark as engine, timeline
from ..pipeline.assets import VIDEO_EXT
from ..pipeline.benchmark_models import BenchmarkInput
from ..pipeline.benchmark_structured import clips, common_view
from ..pipeline.media import has_audio, probe_video, require_ffmpeg
from ..pipeline.sources import SourceRegistry
from . import core

STATE_FILE = "benchmark_state.json"


def _write(path: Path, data: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _fingerprint(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def project_dir(project_id: str) -> Path:
    if not core.PID_RE.fullmatch(project_id):
        raise core.FactoryError("invalid", "올바른 benchmark 작업 id가 필요합니다.")
    job = core.output_root() / "benchmarks" / project_id
    if not (job / STATE_FILE).is_file():
        raise core.FactoryError("not_found", "benchmark 작업을 찾을 수 없습니다.")
    return job


def profiles() -> dict:
    return {"status": "ok", "profiles": engine.profiles(), "ai_provider_used": "none"}


def inspect(project_id: str) -> dict:
    job = project_dir(project_id)
    state = json.loads((job / STATE_FILE).read_text(encoding="utf-8"))
    try:
        loaded = engine.load_plan(job)
        saved_plan = {"plan": loaded.model_dump(), "benchmark": common_view(loaded)}
    except (ValueError, OSError) as error:
        saved_plan = {"plan": None, "plan_validation_error": str(error)}
    return {**state, **saved_plan, "project_dir": str(job), "plan_path": str(job / engine.PLAN_FILE),
            "next_action": ("benchmark plan" if saved_plan["plan"] is None else
                            "benchmark render" if state["status"] != "render_complete" else "done")}


async def plan(input_file: str, *, profile_id: str = "kpop_observation_clip",
               seconds: int | None = None, observation_type: str | None = None,
               confirm_rights: bool = False, note: str = "", license_: str = "my_channel",
               preserve_audio: bool = True, log=print) -> dict:
    if not confirm_rights or not note.strip():
        raise core.FactoryError("rights", "사용 권한을 확인하고 --confirm-rights와 --note 근거를 지정하세요.")
    # Stage 1 supports local originals or AI assets. External stock licences
    # require URLs/credits that this small command does not yet collect.
    if license_ not in {"my_channel", "licensed_upload", "ai_generated"}:
        raise core.FactoryError("rights", "로컬 입력 권리는 my_channel / licensed_upload / ai_generated를 사용하세요.")
    try:
        profile = engine.load_profile(profile_id)
        input_path = Path(input_file).resolve()
        data = BenchmarkInput.model_validate_json(input_path.read_text(encoding="utf-8-sig"))
        resolved = {}
        for src in data.sources:
            if src.reference:
                continue
            if "://" in src.path or src.path.startswith(("\\\\", "//")):
                raise ValueError("local supplied video files only; URLs/network paths are not supported")
            path = Path(src.path)
            if not path.is_absolute():
                path = input_path.parent / path
            path = path.resolve()
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXT:
                raise ValueError(f"local video file not found or unsupported: {src.id}")
            src.path = str(path)
            resolved[src.id] = path
        require_ffmpeg()
        metadata = {}
        for source_id, path in resolved.items():
            info = await probe_video(path)
            if not info.get("streams"):
                raise ValueError(f"no video stream: {source_id}")
            duration = float(info.get("format", {}).get("duration", 0))
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError(f"invalid source duration: {source_id}")
            metadata[source_id] = {"duration": duration, "has_audio": await has_audio(path)}
        selected = engine.select_pair(data, profile, {k: v["duration"] for k, v in metadata.items()},
                                      seconds=seconds, observation_type=observation_type,
                                      preserve_audio=preserve_audio)
    except (ValueError, OSError) as error:
        raise core.FactoryError("invalid", str(error)) from error

    project_id = "benchmark_" + core._new_id()
    job = core.output_root() / "benchmarks" / project_id
    job.mkdir(parents=True, exist_ok=False)
    registry = SourceRegistry(job)
    rights = core._own_rights(license_, note, confirm_rights)
    sources = {src.id: {"reference": src.reference} for src in data.sources if src.reference}
    for source_id in dict.fromkeys(c.source_id for c in clips(selected.selection)):
        original = resolved[source_id]
        destination = job / "uploads" / (source_id + original.suffix.lower())
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(original, destination)
        item = registry.add(kind="video", origin="upload", path=str(destination),
                            title=source_id, rights=rights, used_for="benchmark_evidence")
        if not item.usable_in_video:
            raise core.FactoryError("rights", "소스 사용 권한 검사에 실패했습니다.")
        sources[source_id] = {**metadata[source_id], "path": timeline.rel(destination, job),
                              "sha256": _fingerprint(destination)}
    registry.save()  # text-only plans still have an explicit, initially empty rights ledger
    engine.save_plan(job, selected)
    state = {"schema_version": 1, "engine": "benchmark", "project_id": project_id,
             "status": "benchmark_ready", "sources": sources, "ai_provider_used": "none",
             "ai_calls": [], "tts": "none", "outputs": {}}
    _write(job / STATE_FILE, state)
    log("claim/evidence 쌍을 검증하고 저장했습니다. AI·TTS 호출 없음.")
    return inspect(project_id)


async def render(project_id: str, log=print) -> dict:
    job = project_dir(project_id)
    state = json.loads((job / STATE_FILE).read_text(encoding="utf-8"))
    previous_outputs = dict(state.get("outputs", {}))
    failed_at = "validation"
    try:
        plan_ = engine.load_plan(job)
        source_meta = state["sources"]
        # Revalidate saved claim/evidence and media at every render. A caller
        # editing JSON cannot silently evade timecode or rights checks.
        allowed_root = (job / "uploads").resolve()
        registry = SourceRegistry(job)
        if not registry.path.is_file():
            raise ValueError("source rights registry is missing")
        sources = {}
        require_ffmpeg()
        for sid, src in source_meta.items():
            if src.get("reference"):
                sources[sid] = src
                continue
            path = timeline.resolve(src["path"], job).resolve()
            if not path.is_relative_to(allowed_root):
                raise ValueError("saved source must stay in benchmark uploads")
            if _fingerprint(path) != src["sha256"]:
                raise ValueError("source changed since claim/evidence selection; create a new plan")
            item = registry.by_path(path)
            if not item or not item.usable_in_video:
                raise ValueError("source rights are no longer confirmed")
            info = await probe_video(path)
            if not info.get("streams"):
                raise ValueError("source no longer contains video")
            sources[sid] = {**src, "path": str(path),
                            "duration": float(info["format"]["duration"]), "has_audio": await has_audio(path)}
        data = BenchmarkInput(topic=plan_.topic,
                              sources=[{"id": sid, **({"reference": src["reference"]} if src.get("reference") else
                                                       {"path": src["path"]})} for sid, src in sources.items()],
                              observations=[plan_.selection])
        engine.select_pair(data, plan_.profile_snapshot, {k: v["duration"] for k, v in sources.items() if "duration" in v},
                           seconds=plan_.target_seconds, preserve_audio=plan_.preserve_audio)
        tl = engine.build_timeline(job, plan_, sources)
        registry = SourceRegistry(job)  # adapters may register newly generated cards
        overlay = engine.make_brand_overlay(job, plan_.selection.hook)
        registry.add(kind="image", origin="generated", path=str(overlay), used_for="benchmark_brand")
        tl["comments"] = [{**timeline.image_comment(str(overlay), 0, plan_.target_seconds),
                            "x": 0.5, "y": 0.5, "width": 1.0}]
        registry.guard_timeline(tl)
        timeline.save(job, tl)
        failed_at = "render"
        state.update(status="rendering", error="")
        _write(job / STATE_FILE, state)
        log("기존 B-roll·ASS 렌더 사용: 1080x1920, TTS 없음.")
        temporary = job / "final.benchmark.tmp.mp4"
        await timeline.render_timeline(tl, job, temporary)
        info = await probe_video(temporary)
        stream = (info.get("streams") or [{}])[0]
        duration = float(info.get("format", {}).get("duration", 0))
        if (not temporary.is_file() or temporary.stat().st_size == 0
                or stream.get("width") != 1080 or stream.get("height") != 1920
                or abs(duration - plan_.target_seconds) > 0.2):
            raise ValueError("benchmark output resolution/duration validation failed")
        temporary.replace(job / "final.mp4")
        outputs = {"final_video": str(job / "final.mp4"), "plan": str(job / engine.PLAN_FILE),
                   "timeline": str(job / timeline.FILE), "sources": str(registry.path),
                   "subtitles": str(job / "subs.ass")}
        state.update(status="render_complete", outputs=outputs, duration=round(duration, 3),
                     resolution="1080x1920", error="", failed_at="")
    except Exception as error:  # preserve plan + any previously completed video
        state.update(status="failed", error=f"{type(error).__name__}: {error}",
                     failed_at=failed_at, outputs=previous_outputs)
    _write(job / STATE_FILE, state)
    return inspect(project_id)
