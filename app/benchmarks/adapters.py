"""Translate plans into V1 render contracts; the common engine stays independent."""
from __future__ import annotations

from pathlib import Path

from ..pipeline.models import BlueprintScene, PlannedScene, PlannedScript, VideoBlueprint, VisualDecision
from ..pipeline.timeline import build_timeline
from ..pipeline.subtitles import wrap_title
from .engine import validate_plan
from .models import BenchmarkPlan, BenchmarkProfile


def validate_caption_layout(profile: BenchmarkProfile, title: str, captions: list[str]) -> None:
    """Do not silently truncate the hook's promise or an evidence explanation."""
    per_line = max(4, int((profile.render.width - 120) / int(profile.render.caption_size * 1.15)))
    if title.strip() and wrap_title(title, per_line, max_lines=2)[-1].endswith("…"):
        raise ValueError("Benchmark hook/title is too long for two lines; shorten it before rendering")
    if any(wrap_title(text, 16, max_lines=3)[-1].endswith("…") for text in captions if text.strip()):
        raise ValueError("Benchmark caption is too long for three lines; shorten it before rendering")


def visual_clip(plan: BenchmarkPlan, profile: BenchmarkProfile, sources: dict[str, dict],
                job_dir: Path, *, seconds: float | None = None, subtitles: bool = True) -> tuple[PlannedScript, VideoBlueprint, dict]:
    """Fill configurable stages with bounded evidence; repeated portions are marked.

    No stretching, unrelated b-roll, highlight scoring or TTS. The first evidence
    plays across the first-evidence stage and interpretation if it is longer.
    All selected proof windows must play completely before the payoff.
    """
    plan = validate_plan(plan, profile, sources)
    if not profile.stages or profile.render.narration:
        raise ValueError("visual_clip needs content stages and narration=false")
    allowed = {"reason_to_watch", "reaction_captions", "payoff_or_question", "payoff", "viewer_question", "claim"}
    if any(s.caption not in allowed for s in profile.stages):
        raise ValueError("unsupported caption selector for visual_clip")
    target = float(seconds if seconds is not None else profile.length.target)
    if not 10 <= target <= 180:
        raise ValueError("benchmark target duration must be between 10 and 180 seconds")
    if any(e.clip.end - e.clip.start < 0.5 for e in plan.evidence):
        raise ValueError("visual evidence clips must be at least 0.5 seconds for rendering")
    # Evidence stages are selected by their caption role, not fixed second offsets.
    proof_stages = [s for s in profile.stages if s.caption == "reaction_captions"]
    if not proof_stages:
        raise ValueError("visual_clip needs at least one reaction_captions evidence stage")
    weights = sum(s.seconds for s in profile.stages)
    proof_budget = target * sum(s.seconds for s in proof_stages) / weights
    if sum(e.clip.end - e.clip.start for e in plan.evidence) > proof_budget + 0.001:
        raise ValueError("complete evidence does not fit the evidence stages; select tighter proof windows")
    scenes, blueprint_scenes, render_scenes, lines, mappings = [], [], [], [], []
    proof_index, proof_offset = 0, 0.0
    offset = 0.0
    shown: dict[str, list[tuple[float, float]]] = {}
    for stage in profile.stages:
        remaining = target * stage.seconds / weights
        stage_duration, stage_elapsed = remaining, 0.0
        cursor = stage.evidence_start % len(plan.evidence)
        while remaining > 0.0005:
            pending_proof = stage.caption == "reaction_captions" and proof_index < len(plan.evidence)
            index = proof_index if pending_proof else cursor
            evidence = plan.evidence[index]
            clip = evidence.clip
            src_start = clip.start + (proof_offset if pending_proof else 0)
            duration = min(remaining, clip.end - src_start)
            if stage.caption == "payoff_or_question" and plan.ending_question and stage_elapsed < stage_duration / 2:
                duration = min(duration, stage_duration / 2 - stage_elapsed)
            if stage.caption == "reaction_captions":
                caption = plan.reaction_captions[index]
            elif stage.caption == "payoff_or_question":
                caption = plan.ending_question if plan.ending_question and stage_elapsed >= stage_duration / 2 - 0.0005 else plan.payoff
            else:
                caption = getattr(plan, stage.caption)
            replay = any(lo <= src_start and hi >= src_start + duration - 0.001 for lo, hi in shown.get(evidence.id, []))
            shown.setdefault(evidence.id, []).append((src_start, src_start + duration))
            if replay and stage.caption == "reaction_captions":
                caption = "다시 보기 · " + caption
            start, end = round(offset, 3), round(offset + duration, 3)
            scene_index = len(scenes)
            source = sources[clip.source_id]
            path = Path(source["path"])
            caption = " ".join(caption.split())
            note = f"Caption only; no TTS. Evidence {evidence.id}: {evidence.supports_claim}"
            scenes.append(PlannedScene(narration=caption, image_prompt="", on_screen_text=plan.hook,
                                      scene_type=stage.key, subtitle=caption, visual_type="video",
                                      visual_description=evidence.content, content_kind="claim", notes=note,
                                      motion="static", transition="cut"))
            decision = VisualDecision(scene_id=f"scene_{scene_index + 1:02d}", requested_visual_type="video",
                                      resolved_visual_type="upload_video", asset_path=str(path), asset_source="user_upload",
                                      rights_status="allowed", rights_reason="Source registry checked before rendering",
                                      selection_reason=evidence.supports_claim)
            blueprint_scenes.append(BlueprintScene(index=scene_index, scene_id=decision.scene_id, scene_type=stage.key,
                                    start=start, end=end, duration=end - start, estimated_duration=end - start,
                                    narration=caption, subtitle=caption, visual_type="video", visual_description=evidence.content,
                                    source_id=clip.source_id, emphasis_text=plan.hook, motion="static", transition="cut",
                                    notes=note, timeline_start=start, timeline_end=end, visual_decision=decision))
            render_scenes.append({"duration": end - start, "title": plan.hook, "credit": profile.render.branding,
                                  "visual": {"kind": "video", "path": path, "src_start": src_start,
                                             "src_end": min(clip.end, src_start + duration),
                                             "has_audio": bool(source.get("has_audio")) and profile.render.preserve_source_audio}})
            lines.append({"start": start, "end": end, "text": caption, "words": [], "static": True})
            mappings.append({"evidence_id": evidence.id, "source_id": clip.source_id, "replay": replay,
                             "stage": stage.key, "src_start": src_start, "src_end": src_start + duration})
            if pending_proof:
                proof_offset += duration
                if clip.start + proof_offset >= clip.end - 0.0005:
                    proof_index, proof_offset = proof_index + 1, 0.0
            offset += duration
            remaining -= duration
            stage_elapsed += duration
            cursor = (cursor + 1) % len(plan.evidence)
    if proof_index < len(plan.evidence):
        raise ValueError("selected evidence was not fully shown")
    settings = profile.render
    validate_caption_layout(profile, plan.hook, [s.narration for s in scenes])
    script = PlannedScript(topic=plan.claim, scenes=scenes, titles=[plan.hook], description=plan.reasoning_summary,
                           hashtags=[], sources=[])
    bp = VideoBlueprint(timing="evidence_aligned", topic=plan.claim, width=settings.width, height=settings.height,
                        fps=settings.fps, estimated_duration=round(offset, 3), actual_duration=round(offset, 3),
                        scene_gap=0, tail=0, scenes=blueprint_scenes)
    tl = build_timeline(job_dir, width=settings.width, height=settings.height, fps=settings.fps,
                        mode="broll", narration=None, bgm=None, bgm_volume=0,
                        source_volume=settings.source_volume if settings.preserve_source_audio else 0, transition=0,
                        scenes=render_scenes, lines=lines, subtitles_enabled=subtitles,
                        subtitle_style={"font": settings.font, "size": settings.caption_size,
                                        "highlight": settings.accent, "outline": settings.outline})
    tl["benchmark"] = {"profile_name": profile.profile_name, "narration": False,
                       "blur_background": settings.blur_background, "audio_fade_seconds": 0,
                       "frame_layout": settings.frame_layout,
                       "scene_evidence": mappings}
    return script, bp, tl


# Future fact/timeline content adds one adapter entry; generic analysis stays unchanged.
BUILDERS = {"visual_clip": visual_clip}


def build(plan: BenchmarkPlan, profile: BenchmarkProfile, sources: dict[str, dict], job_dir: Path, **options):
    if profile.render_adapter not in BUILDERS:
        raise ValueError(f"benchmark render adapter not implemented: {profile.render_adapter}")
    return BUILDERS[profile.render_adapter](plan, profile, sources, job_dir, **options)
