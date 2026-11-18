"""Genre-neutral contracts. Profile-specific rules live in JSON, not enums here."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

Text = Annotated[str, Field(min_length=1, max_length=2000)]
Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")]
Positive = Annotated[FiniteFloat, Field(gt=0)]
Nonnegative = Annotated[FiniteFloat, Field(ge=0)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LengthSettings(Contract):
    recommended_min: Positive = 20
    recommended_max: Positive = 35
    target: Positive = 30

    @model_validator(mode="after")
    def ordered(self):
        if not self.recommended_min <= self.target <= self.recommended_max:
            raise ValueError("length.target must be within the recommended range")
        return self


class ContentStage(Contract):
    key: Name
    seconds: Positive
    caption: Name
    evidence_start: int = Field(default=0, ge=0)


class RenderSettings(Contract):
    width: int = Field(default=1080, gt=0, multiple_of=2)
    height: int = Field(default=1920, gt=0, multiple_of=2)
    fps: int = Field(default=30, ge=1, le=120)
    narration: bool = False
    preserve_source_audio: bool = True
    source_volume: FiniteFloat = Field(default=1.0, ge=0, le=2)
    blur_background: bool = True
    frame_layout: Name = "evidence"
    branding: Text = "콘텐츠팩토리"
    font: Text = "Malgun Gothic"
    caption_size: int = Field(default=60, ge=12, le=120)
    accent: str = Field(default="#38BDF8", pattern=r"^#[0-9A-Fa-f]{6}$")
    outline: str = Field(default="#122033", pattern=r"^#[0-9A-Fa-f]{6}$")


class AnalysisSettings(Contract):
    frame_interval_seconds: Positive = 2
    max_frames: int = Field(default=24, ge=2, le=48)
    rules: list[Text] = Field(default_factory=list)


class ObservationRule(Contract):
    description: Text
    min_evidence: int = Field(default=1, ge=1)


class BenchmarkProfile(Contract):
    version: int = Field(default=1, ge=1, le=1)
    profile_name: Name
    content_type: Name
    render_adapter: Name = "visual_clip"
    length: LengthSettings = Field(default_factory=LengthSettings)
    # Empty is deliberate: no K-pop/default story structure in the common schema.
    stages: list[ContentStage] = Field(default_factory=list)
    evidence_types: list[Name] = Field(default_factory=lambda: ["visual"])
    observation_types: dict[Name, ObservationRule] = Field(default_factory=dict)
    viewer_question_rules: list[Text] = Field(default_factory=list)
    hook_types: list[Text] = Field(default_factory=list)
    title_strategy: list[Text] = Field(default_factory=list)
    minimum_confidence: FiniteFloat = Field(default=0, ge=0, le=1)
    caption_rules: list[Text] = Field(default_factory=list)
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    render: RenderSettings = Field(default_factory=RenderSettings)

    @model_validator(mode="after")
    def unique_keys(self):
        keys = [s.key for s in self.stages]
        if len(set(keys)) != len(keys) or not self.evidence_types or len(set(self.evidence_types)) != len(self.evidence_types):
            raise ValueError("stage keys and evidence_types must be unique and evidence_types nonempty")
        return self


class EvidenceClip(Contract):
    source_id: Name
    start: Nonnegative
    end: Positive

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("evidence clip end must be after start")
        return self


class Evidence(Contract):
    id: Name
    evidence_type: Name
    content: Text
    supports_claim: Text
    source_id: str = ""
    clip: EvidenceClip | None = None
    observation_ids: list[Name] = Field(default_factory=list)

    @model_validator(mode="after")
    def visual_requires_clip(self):
        if self.evidence_type == "visual" and self.clip is None:
            raise ValueError("visual evidence requires a timed clip")
        if self.clip and self.source_id and self.source_id != self.clip.source_id:
            raise ValueError("evidence source_id and clip source_id disagree")
        return self


class WatchIntent(Contract):
    """First decision: a viewing reason, without any clip selection or timestamps."""
    observation_type: str = ""
    reason_to_watch: Text
    viewer_question: Text
    hook: Annotated[str, Field(min_length=1, max_length=60)]
    claim: Text
    confidence: FiniteFloat = Field(ge=0, le=1)
    reasoning_summary: Text


class EvidenceSelection(Contract):
    """Second decision: concrete evidence supporting an already locked intent."""
    evidence_type: Name
    evidence: list[Evidence] = Field(min_length=1)
    reaction_captions: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(default_factory=list)
    payoff: Text
    ending_question: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def consistent(self):
        ids = [e.id for e in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence ids must be unique")
        if self.evidence_type != "multiple_examples" and any(e.evidence_type != self.evidence_type for e in self.evidence):
            raise ValueError("evidence_type must match individual evidence (or use multiple_examples)")
        return self


class BenchmarkPlan(WatchIntent, EvidenceSelection):
    version: int = Field(default=1, ge=1, le=1)
    profile_name: Name
    content_type: Name


class Observation(Contract):
    id: Name
    description: Text
    evidence_type: Name = "visual"
    source_id: str = ""
    start: Nonnegative | None = None
    end: Positive | None = None

    @model_validator(mode="after")
    def optional_window(self):
        if (self.start is None) != (self.end is None):
            raise ValueError("observation start/end must be supplied together")
        if self.evidence_type == "visual" and (self.start is None or not self.source_id):
            raise ValueError("visual observations require a source and time window")
        if self.start is not None and (not self.source_id or self.end <= self.start):
            raise ValueError("observation window requires a source and ordered timestamps")
        return self


class Material(Contract):
    subject: Text
    observations: list[Observation] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [o.id for o in self.observations]
        if len(set(ids)) != len(ids):
            raise ValueError("observation ids must be unique")
        return self
