"""Factory lifecycle for Benchmark plans; reuses V1 state/inspection/rendering."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path

from ..benchmarks import adapters, engine
from ..benchmarks.models import BenchmarkPlan, BenchmarkProfile, Material
from ..benchmarks.profiles import load_profile, profile_names
from ..pipeline import blueprint, timeline, visuals
from ..pipeline.assets import kind_of
from ..pipeline.media import has_audio, probe_video, require_ffmpeg
from ..pipeline.models import PlannedScript
from ..pipeline.render import make_thumbnail
from ..pipeline.sources import SourceRegistry
from . import core, state as st


def profiles() -> dict:
    return {"status": "ok", "profiles": [load_profile(name).model_dump() for name in profile_names()]}


def _fingerprint(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _config(request: dict) -> dict:
    provider = request.get("llm") or "claude"
    engine.subscription_config({"provider": provider})
    cfg = core._run_cfg({**request, "llm": "claude", "tts": None, "allow_openai": False})
    cfg["llm"] = engine.subscription_config(cfg["llm"])
    return cfg


async def make(*, video: list[str], benchmark: str, seconds: int | None = None, review: bool = False,
               hint: str = "", instructions: str = "", llm: str | None = None, model: str | None = None,
               subtitles: bool | None = None, asset_rights: dict | None = None,
               benchmark_plan: str | None = None, benchmark_observations: str | None = None,
               mute_source: bool = False, log=print) -> dict:
    if not video or len(video) > 4:
        raise core.FactoryError("invalid", "Benchmark에는 --video 로 로컬 영상 1~4개를 지정하세요.")
    if benchmark_plan and benchmark_observations:
        raise core.FactoryError("invalid", "benchmark-plan / benchmark-observations 중 하나만 지정하세요.")
    if seconds is not None and (isinstance(seconds, bool) or not isinstance(seconds, int) or not 10 <= seconds <= 180):
        raise core.FactoryError("invalid", "목표 길이는 10~180초 사이 정수여야 합니다.")
    rights = asset_rights or {}
    if not (rights.get("rights_confirmed") and str(rights.get("license_note", "")).strip()
            and rights.get("license") in {"my_channel", "licensed_upload", "ai_generated"}
            and rights.get("commercial_allowed") and rights.get("adaptation_allowed")
            and rights.get("third_party_rights_checked")):
        raise core.FactoryError("rights", "영상 사용 권한과 근거를 --confirm-rights --note 로 확인하세요. "
                                "권리는 my_channel / licensed_upload / ai_generated 중 하나여야 합니다.")
    try:
        profile = load_profile(benchmark)
        if mute_source:
            profile.render.preserve_source_audio = False
        if profile.render_adapter not in adapters.BUILDERS:
            raise ValueError(f"benchmark adapter not implemented: {profile.render_adapter}")
        originals = []
        for value in video:
            if "://" in value or value.startswith(("\\\\", "//")):
                raise ValueError("Benchmark 입력은 로컬 파일만 지원합니다. 다운로드는 하지 않습니다.")
            src = Path(value).resolve()
            if not src.is_file() or kind_of(src) != "video" or src.stat().st_size > 200 * 1024 * 1024:
                raise ValueError("Benchmark 영상은 200MB 이하의 읽을 수 있는 로컬 영상이어야 합니다.")
            originals.append(src)
        supplied_plan = (BenchmarkPlan.model_validate_json(Path(benchmark_plan).read_text(encoding="utf-8-sig"))
                         if benchmark_plan else None)
        material = (Material.model_validate_json(Path(benchmark_observations).read_text(encoding="utf-8-sig"))
                    if benchmark_observations else None)
        request = {"mode": "benchmark", "input": hint, "benchmark": benchmark, "seconds": seconds,
                   "review": review, "instructions": instructions, "llm": llm, "model": model,
                   "subtitles": subtitles, "preset": "daily", "allow_openai": False,
                   "analysis_method": "supplied_plan" if supplied_plan else "supplied_observations" if material else "sampled_frames"}
        cfg = _config(request)
        require_ffmpeg()
        metadata = {}
        for i, src in enumerate(originals, 1):
            info = await probe_video(src)
            duration = float(info.get("format", {}).get("duration", 0))
            stream = (info.get("streams") or [{}])[0]
            if not math.isfinite(duration) or duration <= 0 or not stream.get("width") or not stream.get("height"):
                raise ValueError(f"읽을 수 있는 영상 스트림이나 길이가 없습니다: {src.name}")
            metadata[f"video_{i}"] = {"path": str(src), "duration": duration, "has_audio": await has_audio(src),
                                      "sha256": _fingerprint(src)}
        if material:
            engine.validate_material(material, metadata)
        if supplied_plan:
            engine.validate_plan(supplied_plan, profile, metadata)
            # Validate adapter constraints before creating a project as well.
            adapters.build(supplied_plan, profile, metadata, Path.cwd(), seconds=seconds)
    except (ValueError, OSError) as exc:
        raise core.FactoryError("invalid", str(exc)) from exc
    job = core.output_root() / core._new_id()
    state = st.save(job, st.new(job.name, request))
    progress = core._progress(job, state, log)
    try:
        sources = {}
        registry = SourceRegistry(job)
        for sid, src in metadata.items():
            destination = job / "uploads" / f"{sid}{Path(src['path']).suffix.lower()}"
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(src["path"], destination)
            item = registry.add(kind="video", origin="upload", path=str(destination), title=sid,
                                rights=rights, used_for="benchmark_evidence")
            if not item.usable_in_video:
                raise ValueError("입력 영상의 사용 권한이 확인되지 않았습니다.")
            sources[sid] = {**src, "path": timeline.rel(destination, job), "sha256": _fingerprint(destination)}
        engine.save_json(job / engine.SOURCES_FILE, sources)
        engine.save_json(job / engine.PROFILE_FILE, profile.model_dump())
        source_paths = {sid: {**s, "path": str(timeline.resolve(s["path"], job))} for sid, s in sources.items()}
        progress("research", 5, "시청 이유를 정하기 위한 입력 관찰 준비")
        if supplied_plan:
            plan = supplied_plan
        else:
            with core._ai_session(job, state, cfg):
                if material is None:
                    material = await engine.observe_video(profile, source_paths, cfg["llm"], job,
                                                          hint=hint, log=log)
                engine.save_json(job / engine.MATERIAL_FILE, material.model_dump())
                progress("research", 100, "관찰 수집 완료")
                plan = await engine.analyze(profile, material, cfg["llm"], source_paths, job, instructions=instructions)
        progress("research", 100, "시청 이유와 claim/evidence 검증 완료")
        engine.save_json(job / engine.PLAN_FILE, plan.model_dump())
        script, bp, tl = adapters.build(plan, profile, source_paths, job, seconds=seconds,
                                        subtitles=subtitles is not False)
        engine.save_json(job / "script.json", script.model_dump())
        blueprint.save(job, bp)
        timeline.save(job, tl)
        engine.save_json(job / visuals.MANIFEST, [s.visual_decision.model_dump() for s in bp.scenes])
        state["topic"] = plan.claim
        core.runmod._write_meta(job, [plan.hook], plan.reasoning_summary, [], [])
        progress("script", 100, "Benchmark 대본·근거 장면 저장 (TTS 없음)")
        if review:
            st.advance(job, state, "waiting_for_script_approval", topic=plan.claim)
            return core._summary(job, state, **core._script_view(job), benchmark=plan.model_dump(),
                                 benchmark_path=str(job / engine.PLAN_FILE), analysis_method=request["analysis_method"])
        return await render(job, state, log=log, sync_script=True)
    except Exception as exc:
        return core._fail(job, state, exc)


def _sources(job: Path) -> dict:
    sources = json.loads((job / engine.SOURCES_FILE).read_text(encoding="utf-8"))
    registry = SourceRegistry(job)
    if not registry.path.is_file():
        raise ValueError("Benchmark source rights registry is missing")
    for source in sources.values():
        path = timeline.resolve(source["path"], job).resolve()
        if not path.is_relative_to((job / "uploads").resolve()) or _fingerprint(path) != source["sha256"]:
            raise ValueError("입력 파일이 변경됐습니다. 시청 이유와 근거를 새로 분석해야 합니다.")
        item = registry.by_path(path)
        if not item or not item.usable_in_video:
            raise ValueError("입력 영상의 사용 권한이 확인되지 않았습니다.")
        source["path"] = str(path)
    return sources


async def render(job: Path, state: dict, *, log=print, sync_script: bool = False) -> dict:
    """Resume and rerender never re-analyze or invoke any AI/TTS."""
    try:
        require_ffmpeg()
        sources = _sources(job)
        profile = BenchmarkProfile.model_validate_json((job / engine.PROFILE_FILE).read_text(encoding="utf-8"))
        plan = BenchmarkPlan.model_validate_json((job / engine.PLAN_FILE).read_text(encoding="utf-8"))
        material = (Material.model_validate_json((job / engine.MATERIAL_FILE).read_text(encoding="utf-8"))
                    if (job / engine.MATERIAL_FILE).is_file() else None)
        engine.validate_plan(plan, profile, sources, material)
        tl = timeline.load(job)
        mappings = tl.get("benchmark", {}).get("scene_evidence", [])
        if len(mappings) != len(tl["scenes"]) or tl.get("narration") or tl.get("mode") != "broll":
            raise ValueError("invalid Benchmark timeline")
        evidence = {e.id: e for e in plan.evidence}
        proof_stages = {s.key for s in profile.stages if s.caption == "reaction_captions"}
        payoff_stages = {s.key for s in profile.stages if s.caption in {"payoff", "payoff_or_question"}}
        payoff_start = min((s["start"] for s, m in zip(tl["scenes"], mappings) if m["stage"] in payoff_stages), default=timeline.total_duration(tl))
        coverage = {e.id: [] for e in plan.evidence}
        offset = 0.0
        for scene, mapping in zip(tl["scenes"], mappings):
            clip = evidence[mapping["evidence_id"]].clip
            visual = scene["visual"]
            if (not math.isfinite(scene["duration"]) or scene["duration"] <= 0 or abs(scene["start"] - offset) > 0.002
                    or mapping["source_id"] != clip.source_id
                    or visual["kind"] != "video" or str(timeline.resolve(visual["path"], job).resolve()) != sources[clip.source_id]["path"]
                    or visual["src_start"] < clip.start - 0.001
                    or visual["src_start"] + scene["duration"] > clip.end + 0.001
                    or abs(visual.get("src_end", -1) - (visual["src_start"] + scene["duration"])) > 0.001):
                raise ValueError("timeline visual must stay within its selected evidence clip")
            offset += scene["duration"]
            if mapping["stage"] in proof_stages and offset <= payoff_start + 0.002:
                coverage[mapping["evidence_id"]].append((visual["src_start"], visual["src_end"]))
        for eid, ranges in coverage.items():
            clip = evidence[eid].clip
            cursor = clip.start
            for start, end in sorted(ranges):
                if start > cursor + 0.002:
                    break
                cursor = max(cursor, end)
            if cursor < clip.end - 0.002:
                raise ValueError("all selected evidence must be shown completely before the payoff")
        if sync_script:
            script = PlannedScript.model_validate_json((job / "script.json").read_text(encoding="utf-8"))
            bp = blueprint.load(job)
            if len(script.scenes) != len(tl["scenes"]) or len(tl["subtitles"]["lines"]) != len(script.scenes):
                raise ValueError("Benchmark caption scene count changed")
            for scene, line, text, bp_scene in zip(tl["scenes"], tl["subtitles"]["lines"], script.scenes, bp.scenes):
                scene["title"] = text.on_screen_text
                line.update(text=text.narration, words=[], static=True)
                bp_scene.narration = bp_scene.subtitle = text.narration
                bp_scene.emphasis_text = text.on_screen_text
            timeline.save(job, tl)
            blueprint.save(job, bp)
        for scene in tl["scenes"]:
            adapters.validate_caption_layout(profile, scene["title"], [])
        adapters.validate_caption_layout(profile, "", [line["text"] for line in tl["subtitles"]["lines"]])
        registry = SourceRegistry(job)
        registry.guard_timeline(tl)
        st.advance(job, state, "blueprint_complete")
        st.advance(job, state, "visuals_complete")
        st.advance(job, state, "rendering")
        log("기존 b-roll·자막 렌더로 제작 중 (AI 재분석·TTS 없음)")
        temporary = job / "final_benchmark_new.mp4"
        cfg = core._cfg()
        await timeline.render_timeline(tl, job, temporary, Path(cfg["paths"]["assets"]) / "fonts")
        info = await probe_video(temporary)
        stream = (info.get("streams") or [{}])[0]
        duration = float(info.get("format", {}).get("duration", 0))
        if (not temporary.is_file() or not temporary.stat().st_size or not math.isfinite(duration)
                or stream.get("width") != tl["width"] or stream.get("height") != tl["height"]
                or abs(duration - timeline.total_duration(tl)) > 0.2):
            raise ValueError("Benchmark 영상의 해상도 또는 길이가 계획과 다릅니다.")
        temporary.replace(job / "final.mp4")
        await make_thumbnail(job / "final.mp4", job / "thumb.jpg", at=0.5)
        result = {"video": str(job / "final.mp4"), "topic": plan.claim, "duration": duration,
                  "plan_method": "benchmark", "benchmark": str(job / engine.PLAN_FILE)}
        return {**await core._finish(job, state, result), "benchmark": plan.model_dump(),
                "analysis_method": state["request"]["analysis_method"], "tts": "none"}
    except Exception as exc:
        return core._fail(job, state, exc)


async def resume(project_id: str | None, *, log=print, rerender: bool = False) -> dict:
    job = core.project_dir(project_id)
    state = st.load(job)
    if not rerender:
        if st.next_action(state, job) != "resume":
            raise core.FactoryError("not_ready", "이어서 만들 Benchmark 계획이 없습니다.")
        st.advance(job, state, "script_approved", error="", failed_at="")
    return await render(job, state, log=log, sync_script=not rerender)
