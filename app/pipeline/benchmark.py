"""Offline claim-first benchmark selection and existing timeline/render adaptation."""
from __future__ import annotations

import json
import math
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

from . import cards, timeline
from .benchmark_models import BenchmarkInput, BenchmarkPlan, BenchmarkProfile

PROFILE_ROOT = Path(__file__).resolve().parents[2] / "benchmarks"
PLAN_FILE = "benchmark_plan.json"


def load_profile(profile_id: str, root: Path | None = None) -> BenchmarkProfile:
    from .benchmark_models import Identifier
    from pydantic import TypeAdapter
    TypeAdapter(Identifier).validate_python(profile_id)
    base = root or PROFILE_ROOT
    path = base / "profiles" / f"{profile_id}.yaml"
    if not path.is_file():
        path = base / f"{profile_id}.yaml"  # preserve Stage 1 and external profile directories
    if not path.is_file():
        raise ValueError(f"unknown benchmark profile: {profile_id}")
    profile = BenchmarkProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if profile.id != profile_id:
        raise ValueError("profile ID must match filename")
    return profile


def profiles(root: Path | None = None) -> list[dict]:
    base = root or PROFILE_ROOT
    paths = list(base.glob("*.yaml")) + list((base / "profiles").glob("*.yaml"))
    names = [p.stem for p in paths]
    if len(names) != len(set(names)):
        raise ValueError("duplicate production profile IDs")
    return [load_profile(name, root).model_dump() for name in sorted(names, key=lambda n: (n != "kpop_observation_clip", n))]


def select_pair(data: BenchmarkInput, profile: BenchmarkProfile, durations: dict[str, float],
                *, seconds: int | None = None, observation_type: str | None = None,
                preserve_audio: bool = True) -> BenchmarkPlan:
    """Filter complete claim/evidence pairs before ranking; never rank raw highlights.

    Confidence is the weakest declared annotation confidence. No semantic AI check
    or popularity prediction is implied. Invalid candidates remain in the audit.
    """
    if profile.adapter != "legacy_clip":
        from .benchmark_structured import select
        return select(data, profile, durations, seconds=seconds, observation_type=observation_type,
                      preserve_audio=preserve_audio)
    target = profile.default_seconds if seconds is None else seconds
    if isinstance(target, bool) or not isinstance(target, int) or not 20 <= target <= 35:
        raise ValueError("benchmark length must be an integer between 20 and 35 seconds")
    if observation_type and observation_type not in profile.observation_types:
        raise ValueError("observation_type is not supported by this profile")
    source_ids = {src.id for src in data.sources}
    for sid, duration in durations.items():
        if sid not in source_ids or not math.isfinite(duration) or duration <= 0:
            raise ValueError("durations must describe finite positive local source lengths")
    qualified, rejected = [], []
    for candidate in data.observations:
        from .benchmark_models import ObservationCandidate
        if not isinstance(candidate, ObservationCandidate):
            rejected.append({"id": candidate.id, "reason": "legacy clip profile requires evidence_clips"})
            continue
        errors = []
        rule = profile.observation_types.get(candidate.observation_type)
        if observation_type and candidate.observation_type != observation_type:
            errors.append("different requested observation_type")
        if not rule:
            errors.append("unsupported observation_type")
        elif len(candidate.evidence_clips) < rule.min_evidence:
            errors.append("insufficient independent evidence clips")
        elif rule.distinct_perspectives and len({c.perspective for c in candidate.evidence_clips}) < 2:
            errors.append("distinct perspectives are required")
        for i, clip in enumerate(candidate.evidence_clips):
            if clip.source_id not in source_ids or clip.source_id not in durations:
                errors.append(f"unknown source: {clip.source_id}")
            elif clip.end > durations[clip.source_id]:
                errors.append(f"evidence exceeds source duration: {clip.source_id}")
            for earlier in candidate.evidence_clips[:i]:
                if (clip.source_id == earlier.source_id
                        and max(clip.start, earlier.start) < min(clip.end, earlier.end)):
                    errors.append("overlapping evidence cannot count as independent clips")
        confidence = min(candidate.confidence, *(c.confidence for c in candidate.evidence_clips))
        if confidence < profile.minimum_confidence:
            errors.append("annotation confidence below profile threshold")
        # Evidence must play in full across the two evidence beats. Never cut
        # away the part that might prove the claim just to fill a template.
        scale = target / profile.default_seconds
        first_beat, interpretation = profile.content_structure[1:3]
        first_budget = (first_beat.end - first_beat.start) * scale
        interpretation_budget = (interpretation.end - interpretation.start) * scale
        lengths = [c.end - c.start for c in candidate.evidence_clips]
        if sum(lengths) - min(lengths[0], first_budget) > interpretation_budget + 0.0001:
            errors.append("complete evidence does not fit evidence beats; choose tighter proof windows")
        if errors:
            rejected.append({"id": candidate.id, "reason": "; ".join(dict.fromkeys(errors))})
        else:
            qualified.append((confidence, candidate))
    if not qualified:
        raise ValueError("no supported claim/evidence pair: " + json.dumps(rejected, ensure_ascii=False))
    confidence, winner = max(qualified, key=lambda pair: pair[0])  # stable input-order tie break
    rejected += [{"id": c.id, "reason": "qualified but lower priority (confidence/input order)"}
                 for _, c in qualified if c.id != winner.id]
    return BenchmarkPlan(
        profile_id=profile.id, profile_snapshot=profile, topic=data.topic, selection=winner,
        confidence=confidence, reasoning_summary=(
            f"Claim-first pair selected from {len(data.observations)} annotated candidates; "
            f"{len(winner.evidence_clips)} independent clip(s), weakest declared confidence {confidence:.2f}. "
            f"User reasoning: {winner.reasoning_summary}"),
        rejected_candidates=rejected, target_seconds=target, preserve_audio=preserve_audio,
    )


def save_plan(job_dir: Path, plan: BenchmarkPlan) -> None:
    tmp = job_dir / (PLAN_FILE + ".tmp")
    tmp.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(job_dir / PLAN_FILE)


def load_plan(job_dir: Path) -> BenchmarkPlan:
    return BenchmarkPlan.model_validate_json((job_dir / PLAN_FILE).read_text(encoding="utf-8"))


def build_timeline(job_dir: Path, plan: BenchmarkPlan, sources: dict[str, dict]) -> dict:
    """Fill structure only with bounded evidence slices; explicitly mark replays.

    No slow-motion, frames beyond evidence endpoints, TTS, or new factual claims.
    Every evidence plays in full across first_evidence + interpretation. A long
    first clip continues into interpretation rather than losing its proof.
    """
    if plan.profile_snapshot.adapter != "legacy_clip":
        from .benchmark_structured import build
        return build(job_dir, plan, sources)
    candidate = plan.selection
    evidence = candidate.evidence_clips
    scenes, lines, structure = [], [], []
    shown: dict[int, list[tuple[float, float]]] = {}
    scale = plan.target_seconds / plan.profile_snapshot.default_seconds
    first_beat = plan.profile_snapshot.content_structure[1]
    first_budget = (first_beat.end - first_beat.start) * scale
    for beat in plan.profile_snapshot.content_structure:
        start, end = round(beat.start * scale, 3), round(beat.end * scale, 3)
        structure.append({"role": beat.role, "start": start, "end": end})
        pending = []
        if beat.role == "comparison_or_interpretation":
            if evidence[0].end - evidence[0].start > first_budget:
                pending.append((0, evidence[0].start + first_budget, evidence[0].end))
            pending += [(i, c.start, c.end) for i, c in enumerate(evidence) if i > 0]
        cursor = start
        replay_index = 0
        while end - cursor > 0.0005:
            if pending:
                idx, src_start, src_end = pending.pop(0)
                if src_end - src_start > end - cursor + 0.002:
                    raise ValueError("complete evidence cannot fit the saved structure")
            else:
                idx = replay_index % len(evidence) if beat.role == "comparison_or_interpretation" else 0
                replay_index += 1
                src_start, src_end = evidence[idx].start, evidence[idx].end
            clip = evidence[idx]
            duration = min(src_end - src_start, end - cursor)
            replay = any(lo <= src_start and hi >= src_start + duration - 0.001 for lo, hi in shown.get(idx, []))
            src = sources[clip.source_id]
            scenes.append({
                "duration": round(duration, 3), "title": "", "credit": "",
                "role": beat.role, "evidence_index": idx, "replay": replay,
                "visual": {"kind": "video", "path": src["path"], "src_start": src_start,
                           "has_audio": src["has_audio"] and plan.preserve_audio},
            })
            shown.setdefault(idx, []).append((src_start, src_start + duration))
            if beat.role in ("first_evidence", "comparison_or_interpretation") and duration >= 1:
                caption = candidate.reaction_captions[idx % len(candidate.reaction_captions)]
                caption = ("다시 보기 · " if replay else "") + caption
                lines.append({"start": round(cursor, 3), "end": round(cursor + duration, 3),
                              "text": caption, "words": []})
            cursor += duration
        if beat.role == "payoff_or_question":
            lines.append({"start": start, "end": end, "text": candidate.ending_question, "words": []})
    tl = timeline.build_timeline(
        job_dir, width=1080, height=1920, fps=30, mode="observation", narration=None,
        bgm=None, bgm_volume=0, source_volume=1 if plan.preserve_audio else 0, transition=0,
        scenes=scenes, lines=lines, subtitle_style={"font": "Malgun Gothic", "size": 54,
        "highlight": "#FFBD70", "outline": "#172034"}, titles_enabled=False,
    )
    for rendered, source in zip(tl["scenes"], scenes):
        rendered.update({k: source[k] for k in ("role", "evidence_index", "replay")})
    tl["benchmark"] = {"profile_id": plan.profile_id, "structure": structure,
                       "claim": candidate.claim, "reason_to_watch": candidate.reason_to_watch}
    return tl


def make_brand_overlay(job_dir: Path, hook: str) -> Path:
    """Our own plain navy/orange layout; profiles never supply design assets."""
    out = job_dir / "brand_overlay.png"
    img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 1080, 330), fill="#172034")
    draw.rectangle((0, 330, 1080, 338), fill="#FFBD70")
    draw.rectangle((0, 1690, 1080, 1920), fill="#172034")
    font, rows, line_h = cards.fit_text(draw, hook, 940, 220, 76, min_size=38, max_lines=3)
    y = 50 + (220 - line_h * len(rows)) / 2
    for row in rows:
        draw.text(((1080 - cards._width(draw, row, font)) / 2, y), row, font=font, fill="white")
        y += line_h
    brand_font, brand_rows, _ = cards.fit_text(draw, "AI 콘텐츠팩토리 · OBSERVATION", 940, 75, 38)
    row = brand_rows[0]
    draw.text(((1080 - cards._width(draw, row, brand_font)) / 2, 1770), row,
              font=brand_font, fill="#FFBD70")
    img.save(out)
    return out
