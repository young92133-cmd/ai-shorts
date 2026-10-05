"""Benchmark contracts: structural profiles and annotated claim/evidence pairs.

Stage 1 consumes human-authored observations, not automatic video understanding.
Unknown fields are rejected so channel artwork/media cannot become profile data.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
CaptionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,80}$")]
Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Role = Literal["reason_to_watch", "first_evidence", "comparison_or_interpretation", "payoff_or_question"]
EvidenceType = Literal["visual", "clip", "fact", "timeline", "comparison", "reaction", "quote",
                       "multiple_examples", "experiment_result", "before_after", "current_update"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ObservationRule(Contract):
    description: Text
    min_evidence: int = Field(ge=1, le=4)
    distinct_perspectives: bool = False
    question_template: ShortText


class StructureBeat(Contract):
    role: Identifier
    start: Seconds
    end: Seconds


class BenchmarkProfile(Contract):
    schema_version: Literal[1] = 1
    id: Identifier
    name: Text
    philosophy: list[Text] = Field(min_length=5, max_length=5)
    observation_types: dict[Identifier, ObservationRule]
    minimum_confidence: Confidence = 0.65
    default_seconds: int = Field(default=30, ge=10, le=180)
    content_structure: list[StructureBeat] = Field(min_length=4, max_length=10)
    selection_rules: list[Text] = Field(min_length=1)
    content_type: Identifier = "observation_clip"
    adapter: Literal["legacy_clip", "evidence_sequence", "evidence_cards"] = "legacy_clip"
    evidence_types: list[EvidenceType] = Field(default_factory=lambda: ["visual", "clip"])
    evidence_roles: list[Identifier] = Field(default_factory=list)
    source_ids: list[Identifier] = Field(default_factory=list)
    strategy: dict[Identifier, list[Text]] = Field(default_factory=dict)
    min_seconds: int = Field(default=20, ge=10, le=180)
    max_seconds: int = Field(default=35, ge=10, le=180)

    @model_validator(mode="after")
    def structure_valid(self):
        roles = ["reason_to_watch", "first_evidence", "comparison_or_interpretation", "payoff_or_question"]
        cursor = 0.0
        for i, beat in enumerate(self.content_structure):
            if ((self.adapter == "legacy_clip" and (i >= 4 or beat.role != roles[i]))
                    or beat.start != cursor or beat.end <= beat.start):
                raise ValueError("profile beats must be ordered, contiguous and positive")
            cursor = beat.end
        if cursor != self.default_seconds:
            raise ValueError("profile beats must cover default_seconds")
        if not self.observation_types:
            raise ValueError("profile requires observation rules")
        if not self.min_seconds <= self.default_seconds <= self.max_seconds:
            raise ValueError("profile duration range is invalid")
        if len({b.role for b in self.content_structure}) != len(self.content_structure):
            raise ValueError("duplicate structure roles")
        if not self.evidence_types or len(set(self.evidence_types)) != len(self.evidence_types):
            raise ValueError("evidence types must be nonempty and unique")
        if any(role not in {b.role for b in self.content_structure} for role in self.evidence_roles):
            raise ValueError("evidence roles must be present in structure")
        if self.adapter != "legacy_clip" and not self.evidence_roles:
            raise ValueError("structured profiles require evidence roles")
        return self


class SourceInput(Contract):
    id: Identifier
    path: Text | None = None
    reference: Text | None = None

    @model_validator(mode="after")
    def has_provenance(self):
        if bool(self.path) == bool(self.reference):
            raise ValueError("source requires either a local path or an annotation reference")
        return self


class EvidenceClip(Contract):
    source_id: Identifier
    start: Seconds
    end: Seconds
    perspective: ShortText
    observation: Text
    supports_claim: Text
    confidence: Confidence

    @model_validator(mode="after")
    def valid_range(self):
        if self.end - self.start < 2:
            raise ValueError("evidence clips must be at least 2 seconds")
        return self


class ObservationCandidate(Contract):
    id: Identifier
    observation_type: Identifier
    reason_to_watch: Text
    hook: ShortText
    claim: Text
    evidence_clips: list[EvidenceClip] = Field(min_length=1, max_length=4)
    reaction_captions: list[CaptionText] = Field(min_length=1, max_length=4)
    ending_question: CaptionText
    confidence: Confidence
    reasoning_summary: Text


class StructuredEvidence(Contract):
    id: Identifier
    evidence_type: EvidenceType
    role: Identifier
    source_id: Identifier
    content: Text
    supports_claim: Text
    caption: CaptionText
    confidence: Confidence
    clip: EvidenceClip | None = None
    rank: int | None = Field(default=None, ge=1, le=10)
    condition_value: ShortText | None = None

    @model_validator(mode="after")
    def clip_required(self):
        if self.evidence_type in ("visual", "clip", "experiment_result") and not self.clip:
            raise ValueError("visual/clip/experiment evidence requires a timed clip")
        if self.clip and self.clip.source_id != self.source_id:
            raise ValueError("evidence and clip sources disagree")
        return self


class Experiment(Contract):
    variable: Identifier
    controls: dict[Identifier, ShortText] = Field(min_length=1)


class StructuredCandidate(Contract):
    id: Identifier
    observation_type: Identifier
    reason_to_watch: Text
    viewer_question: CaptionText
    hook: ShortText
    claim: Text
    evidence_type: EvidenceType
    evidence: list[StructuredEvidence] = Field(min_length=1, max_length=10)
    payoff: CaptionText
    ending_question: CaptionText
    confidence: Confidence
    reasoning_summary: Text
    experiment: Experiment | None = None

    @model_validator(mode="after")
    def consistent_evidence(self):
        if len({e.id for e in self.evidence}) != len(self.evidence):
            raise ValueError("evidence IDs must be unique")
        if self.evidence_type != "multiple_examples" and any(e.evidence_type != self.evidence_type for e in self.evidence):
            raise ValueError("evidence_type must match evidence or be multiple_examples")
        return self


class BenchmarkInput(Contract):
    schema_version: Literal[1] = 1
    topic: Text
    sources: list[SourceInput] = Field(min_length=1, max_length=10)
    observations: list[ObservationCandidate | StructuredCandidate] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_ids(self):
        for items in (self.sources, self.observations):
            if len({x.id for x in items}) != len(items):
                raise ValueError("source and observation IDs must be unique")
        return self


class BenchmarkPlan(Contract):
    schema_version: Literal[1] = 1
    profile_id: Identifier
    profile_snapshot: BenchmarkProfile
    topic: Text
    selection: ObservationCandidate | StructuredCandidate
    confidence: Confidence
    reasoning_summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]
    selection_method: Literal["annotated_claim_evidence_v1"] = "annotated_claim_evidence_v1"
    semantic_verification: Literal["user_annotations_only"] = "user_annotations_only"
    rejected_candidates: list[dict[str, str]]
    target_seconds: int = Field(ge=10, le=180)
    preserve_audio: bool = True
