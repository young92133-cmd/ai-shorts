"""카드뉴스·인스타툰·하이브리드 캐러셀의 데이터 구조.

Master Content(형식과 무관한 핵심 내용) → CarouselPlan(페이지 목록) → PNG.
쇼츠의 Script 와 같은 역할이지만 시간축이 없고 페이지 단위다.
"""
from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field

OUTPUT_FORMATS = ("shorts", "card_news", "insta_toon", "hybrid", "all")
CAROUSEL_FORMATS = ("card_news", "insta_toon", "hybrid")
CARD_TYPES = ("cover", "hook", "info_card", "checklist", "comparison", "quote", "summary", "cta")
COMIC_TYPES = ("comic_scene", "dialogue_scene", "reaction_scene", "explanation_scene")
PAGE_TYPES = CARD_TYPES + COMIC_TYPES
BUBBLE_POSITIONS = ("top_left", "top_right", "bottom_left", "bottom_right", "top", "bottom")
EMOTIONS = ("neutral", "happy", "surprised", "worried", "thinking", "confident", "sad", "angry")


# ---------- Master Content (모든 출력 형식의 공통 원천) ----------

class MasterFact(BaseModel):
    text: str = Field(description="자료에서 확인된 사실 한 문장")
    source_index: int = Field(default=0, description="근거 자료 번호 (1부터). 모르면 0")


class Comparison(BaseModel):
    title: str = Field(default="", description="비교 제목 (예: 전세 vs 월세)")
    left_label: str
    right_label: str
    left_points: list[str] = Field(default_factory=list, description="왼쪽 특징 1~3개 (짧게)")
    right_points: list[str] = Field(default_factory=list, description="오른쪽 특징 1~3개 (짧게)")


class MasterContent(BaseModel):
    topic: str = Field(description="콘텐츠 주제 한 줄")
    title: str = Field(description="표지 제목 (20자 안팎)")
    subtitle: str = Field(default="", description="표지 부제 (30자 안팎)")
    hook: str = Field(default="", description="첫 장에서 넘기게 만드는 질문·문장")
    angle: str = Field(default="", description="이 콘텐츠가 주는 관점·답")
    story_score: float = Field(default=0.5, description="0=순수 정보형, 1=순수 이야기형")
    key_points: list[str] = Field(default_factory=list, description="핵심 포인트 3~6개 (각 40자 이내)")
    facts: list[MasterFact] = Field(default_factory=list, description="확인된 사실 3~8개")
    checklist: list[str] = Field(default_factory=list, description="독자가 확인할 체크 항목 3~5개 (각 25자 이내)")
    comparison: Comparison | None = Field(default=None, description="비교 요소가 있을 때만")
    quote: str = Field(default="", description="인용할 만한 한 문장 (자료 속 발언·명언). 없으면 빈 문자열")
    quote_by: str = Field(default="", description="인용 출처")
    story_beats: list[str] = Field(default_factory=list,
                                   description="인스타툰용 상황 흐름 2~5개 (인물이 겪는 일, 한 줄씩)")
    summary: str = Field(default="", description="한 문장 정리")
    cta: str = Field(default="", description="마지막 장 행동 유도 문장 (저장·공유·댓글)")
    hashtags: list[str] = Field(default_factory=list)
    sources: list[dict[str, str]] = Field(default_factory=list, description="[{title, url}] 조사 자료")


# ---------- 페이지 ----------

class ComicBeat(BaseModel):
    character_id: str = Field(description="Character Registry 의 캐릭터 id")
    scene: str = Field(default="", description="이 컷에서 일어나는 일 (그림 지시, 한국어)")
    emotion: str = Field(default="neutral", description=" | ".join(EMOTIONS))
    pose: str = Field(default="standing", description="자세 (standing, pointing, arms_crossed, thinking, waving ...)")
    dialogue: str = Field(default="", description="말풍선 대사 (40자 이내). 렌더러가 직접 글자를 합성한다")
    background: str = Field(default="", description="배경 설명 (예: 부동산 사무실, 거실)")
    camera: str = Field(default="medium", description="close_up | medium | wide")
    speech_bubble_position: str = Field(default="top_right", description=" | ".join(BUBBLE_POSITIONS))


class CardPage(BaseModel):
    kind: Literal["card"] = "card"
    type: str = Field(description=" | ".join(CARD_TYPES))
    label: str = Field(default="", description="작은 태그 (예: POINT 1, 핵심, 체크). 비워도 됨")
    headline: str = Field(default="", description="큰 제목 (25자 이내)")
    body: str = Field(default="", description="본문 (90자 이내)")
    items: list[str] = Field(default_factory=list, description="체크리스트/요약 항목 (각 25자 이내)")
    compare: Comparison | None = None
    visual_query: str = Field(default="", description="이미지 검색어 (영어 권장). 이미지가 필요 없으면 빈 문자열")
    layout: str = Field(default="", description="템플릿 레이아웃 이름. 비우면 타입 기본값")
    source: str = Field(default="", description="이 페이지 내용의 출처 (자료 제목/URL)")
    emphasis: str = Field(default="", description="강조할 단어나 숫자 (headline/body 안의 일부)")


class ComicPage(BaseModel):
    kind: Literal["comic"] = "comic"
    type: str = Field(description=" | ".join(COMIC_TYPES))
    headline: str = Field(default="", description="상단 캡션 (선택)")
    panels: list[ComicBeat] = Field(default_factory=list, description="컷 1~2개")
    caption: str = Field(default="", description="하단 설명 문장 (explanation_scene 에서 주로 사용)")
    layout: str = ""
    source: str = ""
    emphasis: str = ""


Page = Union[CardPage, ComicPage]


class CarouselPlan(BaseModel):
    format: str
    template: str
    mix: dict[str, int] = Field(default_factory=dict, description="{'card': 80, 'comic': 20}")
    pages: list[Page] = Field(default_factory=list)
    method: str = "rules"   # llm | rules


def page_from_dict(raw: dict[str, Any]) -> Page:
    kind = raw.get("kind") or ("comic" if raw.get("type") in COMIC_TYPES else "card")
    return ComicPage.model_validate({**raw, "kind": "comic"}) if kind == "comic" else CardPage.model_validate({**raw, "kind": "card"})
