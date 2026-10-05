"""Offline typed evidence adapters. References are annotations, never fetched media."""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import cards, timeline
from .benchmark_models import BenchmarkPlan, StructuredCandidate
from .sources import SourceRegistry


def clips(candidate):
    return (candidate.evidence_clips if not isinstance(candidate, StructuredCandidate)
            else [e.clip for e in candidate.evidence if e.clip])


def common_view(plan):
    c = plan.selection
    structured = isinstance(c, StructuredCandidate)
    return dict(profile_name=plan.profile_id, content_type=plan.profile_snapshot.content_type,
                reason_to_watch=c.reason_to_watch,
                viewer_question=c.viewer_question if structured else c.ending_question,
                hook=c.hook, claim=c.claim,
                evidence_type=c.evidence_type if structured else "clip",
                evidence=[e.model_dump() for e in c.evidence] if structured else
                         [dict(evidence_type="clip", **e.model_dump()) for e in c.evidence_clips],
                payoff=c.payoff if structured else c.ending_question,
                ending_question=c.ending_question, confidence=plan.confidence,
                reasoning_summary=plan.reasoning_summary)


def select(data, profile, durations, *, seconds=None, observation_type=None, preserve_audio=True):
    target = profile.default_seconds if seconds is None else seconds
    if isinstance(target, bool) or not isinstance(target, int) or not profile.min_seconds <= target <= profile.max_seconds:
        raise ValueError(f"benchmark length must be {profile.min_seconds}~{profile.max_seconds} seconds")
    if observation_type and observation_type not in profile.observation_types:
        raise ValueError("observation_type is not supported by this profile")
    sources = {s.id: s for s in data.sources}
    for sid, duration in durations.items():
        if sid not in sources or not math.isfinite(duration) or duration <= 0:
            raise ValueError("invalid source duration")
    accepted, rejected = [], []
    for c in data.observations:
        try:
            if not isinstance(c, StructuredCandidate):
                raise ValueError("structured profile requires viewer_question, typed evidence and payoff")
            rule = profile.observation_types.get(c.observation_type)
            if not rule or observation_type and c.observation_type != observation_type:
                raise ValueError("unsupported/requested observation_type")
            if len(c.evidence) < rule.min_evidence:
                raise ValueError("insufficient evidence")
            if c.evidence_type != "multiple_examples" and c.evidence_type not in profile.evidence_types:
                raise ValueError("invalid evidence type for profile")
            if {e.role for e in c.evidence} != set(profile.evidence_roles):
                raise ValueError("profile requires exactly its evidence roles")
            for e in c.evidence:
                label = f"{e.rank}위 · " if e.rank else f"{e.condition_value} · " if e.condition_value else ""
                if len(label + e.caption) > 60:
                    raise ValueError("condition/rank caption exceeds subtitle limit")
                if e.evidence_type not in profile.evidence_types:
                    raise ValueError("invalid evidence type for profile")
                source = sources.get(e.source_id)
                if source is None:
                    raise ValueError("unknown evidence source")
                if profile.adapter == "evidence_cards" and (e.clip or not source.reference):
                    raise ValueError("card evidence requires an annotation reference, not media")
                if profile.adapter == "evidence_sequence" and not e.clip:
                    raise ValueError("sequence evidence requires local timed clips")
                if e.clip and (not source.path or e.source_id not in durations or e.clip.end > durations[e.source_id]):
                    raise ValueError("evidence exceeds/misses source duration")
            evidence_clips = clips(c)
            for i, clip in enumerate(evidence_clips):
                for prev in evidence_clips[:i]:
                    # Canonical paths prevent duplicate file aliases being independent proof.
                    if (Path(sources[clip.source_id].path).resolve() == Path(sources[prev.source_id].path).resolve()
                            and max(clip.start, prev.start) < min(clip.end, prev.end)):
                        raise ValueError("overlapping evidence cannot count as independent")
            if rule.distinct_perspectives and len({e.clip.perspective for e in c.evidence if e.clip}) < 2:
                raise ValueError("distinct perspectives required")
            if profile.content_type == "physics_comparison":
                if not c.experiment or c.experiment.variable != c.observation_type:
                    raise ValueError("experiment requires the selected variable and fixed controls")
                if c.experiment.variable in c.experiment.controls:
                    raise ValueError("changed variable cannot also be fixed")
                values = [e.condition_value for e in c.evidence]
                if not all(values) or len(set(values)) != len(values):
                    raise ValueError("experiment conditions must be explicit and distinct")
            if profile.content_type == "ranked_moments":
                ranks = [e.rank for e in c.evidence]
                if ranks != list(range(len(ranks), 0, -1)):
                    raise ValueError("ranks must count down consecutively to 1")
            scale = target / profile.default_seconds
            for beat in profile.content_structure:
                group = [e for e in c.evidence if e.role == beat.role]
                if sum(e.clip.end - e.clip.start for e in group if e.clip) > (beat.end - beat.start) * scale + .001:
                    raise ValueError("complete evidence does not fit its structure beat")
            confidence = min(c.confidence, *(e.confidence for e in c.evidence),
                             *(clip.confidence for clip in evidence_clips))
            if confidence < profile.minimum_confidence:
                raise ValueError("annotation confidence below profile threshold")
            accepted.append((confidence, c))
        except ValueError as error:
            rejected.append(dict(id=c.id, reason=str(error)))
    if not accepted:
        raise ValueError("no supported claim/evidence pair: " + json.dumps(rejected, ensure_ascii=False))
    confidence, winner = max(accepted, key=lambda pair: pair[0])
    rejected += [dict(id=c.id, reason="qualified but lower priority") for _, c in accepted if c.id != winner.id]
    return BenchmarkPlan(profile_id=profile.id, profile_snapshot=profile, topic=data.topic, selection=winner,
                         confidence=confidence, reasoning_summary=f"Offline annotated evidence; User reasoning: {winner.reasoning_summary}",
                         rejected_candidates=rejected, target_seconds=target, preserve_audio=preserve_audio)


def build(job: Path, plan, sources):
    c, profile = plan.selection, plan.profile_snapshot
    registry = SourceRegistry(job)
    scenes, lines = [], []
    scale = plan.target_seconds / profile.default_seconds
    card_dir = job / "cards"
    card_dir.mkdir(exist_ok=True)

    def append_card(text, duration, role, evidence_id=None):
        path = cards.render_card("statement_card", card_dir / f"{len(scenes):02d}.png", emphasis=text,
                                 seed=plan.profile_id, variant=len(scenes))
        registry.add(kind="image", origin="generated", path=str(path), used_for="benchmark_card")
        scenes.append(dict(duration=duration, title="", credit="", role=role, evidence_id=evidence_id,
                           visual=dict(kind="image", path=str(path))))

    for beat in profile.content_structure:
        start, end = round(beat.start * scale, 3), round(beat.end * scale, 3)
        group = [e for e in c.evidence if e.role == beat.role]
        if not group:
            text = c.hook if beat.role == "hook" else c.ending_question if beat.role == "ending_question" else c.payoff
            append_card(text, end - start, beat.role)
            continue
        cursor = start
        for i, e in enumerate(group):
            if e.clip:
                duration = e.clip.end - e.clip.start
                src = sources[e.source_id]
                scenes.append(dict(duration=duration, title="", credit="", role=beat.role, evidence_id=e.id,
                                   visual=dict(kind="video", path=src["path"], src_start=e.clip.start,
                                               has_audio=src["has_audio"] and plan.preserve_audio)))
                label = f"{e.rank}위 · " if e.rank else f"{e.condition_value} · " if e.condition_value else ""
                lines.append(dict(start=cursor, end=cursor + duration, text=label + e.caption, words=[]))
            else:
                # One factual caption per card; no source article/quote asset copied.
                duration = (end - start) / len(group)
                append_card(e.caption, duration, beat.role, e.id)
                lines.append(dict(start=cursor, end=cursor + duration, text=e.caption, words=[]))
            cursor += duration
        if end - cursor > .001:
            # A result recap fills remaining time without invented video frames.
            append_card(c.payoff if beat.role == profile.evidence_roles[-1] else group[-1].caption,
                        end - cursor, beat.role)
    tl = timeline.build_timeline(job, width=1080, height=1920, fps=30, mode="observation", narration=None,
                                 bgm=None, bgm_volume=0, source_volume=1 if plan.preserve_audio else 0,
                                 transition=0, scenes=scenes, lines=lines,
                                 subtitle_style=dict(font="Malgun Gothic", size=54, highlight="#FFBD70", outline="#172034"),
                                 titles_enabled=False)
    for rendered, scene in zip(tl["scenes"], scenes):
        rendered.update(role=scene["role"], evidence_id=scene.get("evidence_id"))
    tl["benchmark"] = common_view(plan)
    return tl
