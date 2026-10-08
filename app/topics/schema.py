from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict

KST = dt.timezone(dt.timedelta(hours=9))
CATEGORIES = ('housing', 'finance', 'economy')
Category = Literal['housing', 'finance', 'economy']
Verification = Literal['verified', 'needs_review', 'unverified', 'conflicting', 'outdated']
Status = Literal['discovered', 'verified', 'scored', 'shortlisted', 'approved', 'planned', 'generated',
                 'reviewed', 'published', 'excluded', 'held']


def now() -> str:
    return dt.datetime.now(KST).isoformat(timespec='seconds')


def timestamp(value: str) -> dt.datetime | None:
    from email.utils import parsedate_to_datetime
    if not value:
        return None
    try:
        result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            return None
    return result.replace(tzinfo=KST) if result.tzinfo is None else result.astimezone(KST)


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Evidence(Record):
    evidence_id: str
    url: str
    title: str = ''
    text: str = ''
    published_at: str = ''
    retrieved_at: str = Field(default_factory=now)
    event_date: str = ''
    source_kind: str = 'news'
    publisher_group: str = ''
    access: str = 'public'
    original_url: str = ''
    rights_status: str = 'reference_only'


class Citation(Record):
    evidence_id: str
    excerpt: str
    result: str = 'supports'


class Fact(Record):
    fact_id: str
    claim: str
    kind: Literal['fact', 'forecast', 'opinion'] = 'fact'
    important: bool = True
    citations: list[Citation] = Field(default_factory=list)
    as_of: str = ''
    unit: str = ''
    applies_to: str = ''
    statistic_original_url: str = ''
    conflict_key: str = ''
    value: str = ''
    verification: Verification = 'unverified'
    checks: list[str] = Field(default_factory=list)


class ScoreParts(Record):
    interest: float = Field(ge=0, le=5, allow_inf_nan=False)
    story: float = Field(ge=0, le=5, allow_inf_nan=False)
    utility: float = Field(ge=0, le=5, allow_inf_nan=False)
    business: float = Field(ge=0, le=5, allow_inf_nan=False)


class Score(Record):
    parts: ScoreParts
    total_score: float
    reasons: dict[str, str]
    audience: list[str]
    recommended_format: str = 'hybrid'
    recommendation: str = 'hold'
    method: str = 'rules_estimate'
    model: str = 'none'
    created_at: str = Field(default_factory=now)


class Opportunity(Record):
    b2b_fit_score: float
    target_industries: list[str]
    client_use_cases: list[str]
    sample_deliverables: list[str]
    recommended_package: str
    compliance_risks: list[str]
    content_type: str = 'independent_education'


class Topic(Record):
    topic_id: str
    title: str
    category: Category
    summary: str = ''
    target_audience: list[str] = Field(default_factory=lambda: ['25~39세 직장인'])
    source_urls: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    published_at: str = ''
    retrieved_at: str = Field(default_factory=now)
    event_date: str = ''
    freshness: Literal['unknown', 'current', 'evergreen', 'expired'] = 'unknown'
    source_confidence: float = 0
    verification: Verification = 'unverified'
    verification_reasons: list[str] = Field(default_factory=list)
    verified_at: str = ''
    valid_until: str = ''
    status: Status = 'discovered'
    created_at: str = Field(default_factory=now)
    event_key: str = ''
    core_claim: str = ''
    angle: str = ''
    keywords: list[str] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    score: Score | None = None
    opportunity: Opportunity | None = None
    duplicate_of: str = ''
    duplicate_reasons: list[str] = Field(default_factory=list)
    series_parent_id: str = ''
    update_of: str = ''
    followup_requested: bool = False
    compliance_flags: list[str] = Field(default_factory=list)
    approved_at: str = ''
    approval_fingerprint: str = ''
    scheduled_date: str = ''
    character_id: str = 'tory_01'
    character_rights: str = 'owned'
    projects: list[dict] = Field(default_factory=list)
    current_projects: list[dict] = Field(default_factory=list)


class StoryPage(Record):
    role: str
    page_type: str
    headline: str = ''
    body: str = ''
    scene: str = ''
    character_id: str = ''
    emotion: str = 'neutral'
    pose: str = 'standing'
    dialogue: str = ''
    visual_direction: str = ''
    source_refs: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    layout: str = ''


class StoryPlan(Record):
    topic_id: str
    format: str
    style: str
    title: str
    character_id: str
    pages: list[StoryPage]
    master: dict
    carousel_plan: dict
    provenance: dict
    dialogue_disclaimer: str = '캐릭터 상황과 대사는 이해를 돕기 위한 창작 예시이며 실제 관계자의 발언이 아닙니다.'


class CalendarEntry(Record):
    entry_id: str
    topic_id: str
    scheduled_date: str
    category: Category
    topic: str
    recommended_title: str
    audience: list[str]
    topic_score: float
    format: str
    purpose: str
    character: str
    verification: Verification
    b2b: list[str]
    production_status: str
    publication_gate: str = 'human_approval_required'


class Publication(Record):
    topic_id: str
    published_at: str
    category: Category
    title: str
    core_claim: str
    event_key: str = ''
    keywords: list[str] = Field(default_factory=list)
    target_audience: list[str] = Field(default_factory=list)
    url: str = ''
    project_id: str = ''
