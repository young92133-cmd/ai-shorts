"""Format Planner — Master Content 를 출력 형식(card_news / insta_toon / hybrid)의 페이지 목록으로 바꾼다.

1. mix_ratio: 콘텐츠 성격(story_score)으로 카드/만화 비율을 정한다 (정보형 80/20, 일반형 50/50, 스토리형 20/80).
2. skeleton: 비율과 장수에 맞는 페이지 타입 순서 (규칙).
3. AI 가 골격을 참고해 페이지 문구·컷을 쓴다. AI 가 타입을 바꿔도 normalize 가 규칙(첫 장 cover, 끝 장 cta,
   6~10장, 형식별 허용 타입, 캐릭터 id, 말풍선 위치)을 다시 맞춘다.
4. AI 가 실패하면 rule_pages 가 Master Content 만으로 완성된 계획을 만든다.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..pipeline.llm import ask_structured
from .characters import CharacterBible
from .schema import (BUBBLE_POSITIONS, CARD_TYPES, COMIC_TYPES, EMOTIONS, CardPage, CarouselPlan, ComicBeat,
                     ComicPage, Comparison, MasterContent, Page)

MIN_PAGES, MAX_PAGES, DEFAULT_PAGES = 6, 10, 8
POSES = ("standing", "pointing", "waving", "arms_crossed", "thinking", "cheering", "shrug")
COMIC_ROTATION = ("comic_scene", "dialogue_scene", "reaction_scene", "explanation_scene")


def mix_ratio(fmt: str, story_score: float) -> dict[str, int]:
    """{'card': %, 'comic': %} — 표지·마지막 CTA 를 뺀 본문 페이지 기준."""
    if fmt == "card_news":
        return {"card": 100, "comic": 0}
    if fmt == "insta_toon":
        return {"card": 0, "comic": 100}
    if story_score >= 0.66:
        return {"card": 20, "comic": 80}
    if story_score <= 0.33:
        return {"card": 80, "comic": 20}
    return {"card": 50, "comic": 50}


def skeleton(fmt: str, master: MasterContent, n_pages: int = DEFAULT_PAGES) -> list[str]:
    """페이지 타입 순서. 첫 장 cover, 끝 장 cta."""
    n = max(MIN_PAGES, min(MAX_PAGES, int(n_pages or DEFAULT_PAGES)))
    mid = n - 2
    mix = mix_ratio(fmt, master.story_score)
    n_comic = round(mid * mix["comic"] / 100)
    if fmt == "hybrid":
        n_comic = max(1, min(mid - 2, n_comic))      # 하이브리드는 양쪽이 최소 1~2장씩 있어야 섞인다
    n_card = mid - n_comic
    # 카드 슬롯: 정보 → (체크리스트|비교) → 요약 순. 장수가 적으면 뒤쪽 특수 카드부터 뺀다.
    extras = []
    if master.comparison:
        extras.append("comparison")
    if master.checklist:
        extras.append("checklist")
    if not extras:
        extras.append("checklist" if fmt != "card_news" else "info_card")
    if master.quote and fmt == "card_news":
        extras.append("quote")
    cards: list[str] = []
    if n_card:
        tail = ["summary"] if n_card >= 2 else []
        hook = ["hook"] if n_comic == 0 and n_card >= 4 else []
        room = n_card - len(tail) - len(hook)
        special = extras[:max(0, room - 1)] if room > 1 else []
        infos = ["info_card"] * max(0, room - len(special))
        cards = hook + infos + special + tail
    comics = [COMIC_ROTATION[k % len(COMIC_ROTATION)] for k in range(n_comic)]
    if fmt == "insta_toon":
        body = comics
    elif not comics:
        body = cards
    else:
        # 이야기로 문을 열고(만화 1~2컷), 정보 카드 사이사이에 남은 컷을 끼운다. 요약은 끝 쪽에.
        lead = comics[:2] if n_comic >= 2 and n_card <= mid / 2 + 1 else comics[:1]
        rest = comics[len(lead):]
        body = list(lead)
        summary = [c for c in cards if c == "summary"]
        others = [c for c in cards if c != "summary"]
        for c in others:
            body.append(c)
            if rest:
                body.append(rest.pop(0))
        body += rest + summary
    return ["cover", *body, "cta"]


# ---------- 규칙 기반 페이지 채우기 ----------

def _beat(char_id: str, k: int, dialogue: str, scene: str = "", emotion: str = "", pose: str = "",
          background: str = "", camera: str = "medium") -> ComicBeat:
    emo = emotion or ("worried", "thinking", "surprised", "happy", "confident")[k % 5]
    return ComicBeat(character_id=char_id, scene=scene, emotion=emo,
                     pose=pose or {"worried": "thinking", "thinking": "thinking", "surprised": "waving",
                                   "happy": "pointing", "confident": "arms_crossed"}.get(emo, "standing"),
                     dialogue=dialogue[:60], background=background, camera=camera,
                     speech_bubble_position=("top_right", "top_left")[k % 2])


def rule_pages(types: list[str], master: MasterContent, char_id: str) -> list[Page]:
    points = list(master.key_points) or [f.text for f in master.facts] or [master.summary or master.title]
    beats = list(master.story_beats) or [master.hook or master.title, *points]
    src = master.sources[0]["title"] if master.sources else ""
    pi = bi = 0
    pages: list[Page] = []
    for k, t in enumerate(types):
        if t == "cover":
            pages.append(CardPage(type="cover", label=master.topic[:16], headline=master.title, body=master.subtitle))
        elif t == "hook":
            pages.append(CardPage(type="hook", headline=master.hook or master.title, body=master.angle))
        elif t == "info_card":
            text = points[pi % len(points)]
            pi += 1
            pages.append(CardPage(type="info_card", label=f"POINT {pi}", headline=text[:28], body=text if len(text) > 28 else "",
                                  source=src))
        elif t == "checklist":
            items = master.checklist or points[:4]
            pages.append(CardPage(type="checklist", headline="꼭 확인하세요", items=items[:5]))
        elif t == "comparison":
            cmp = master.comparison or Comparison(left_label="A", right_label="B")
            pages.append(CardPage(type="comparison", headline=cmp.title or f"{cmp.left_label} vs {cmp.right_label}",
                                  compare=cmp))
        elif t == "quote":
            pages.append(CardPage(type="quote", headline=master.quote or master.summary, body=master.quote_by))
        elif t == "summary":
            pages.append(CardPage(type="summary", headline="한눈에 정리", items=points[:4]))
        elif t == "cta":
            pages.append(CardPage(type="cta", headline=master.cta or "저장하고 다시 보세요", items=["저장", "공유", "댓글"]))
        elif t in COMIC_TYPES:
            line = beats[bi % len(beats)]
            bi += 1
            if t == "explanation_scene":
                text = points[pi % len(points)]
                pi += 1
                pages.append(ComicPage(type=t, panels=[_beat(char_id, k, "이건 꼭 알아 두세요!", emotion="happy",
                                                             pose="pointing")], caption=text, source=src))
            elif t == "dialogue_scene":
                nxt = beats[bi % len(beats)]
                bi += 1
                pages.append(ComicPage(type=t, panels=[_beat(char_id, k, line), _beat(char_id, k + 1, nxt)]))
            else:
                pages.append(ComicPage(type=t, panels=[_beat(char_id, k, line,
                                                             emotion="surprised" if t == "reaction_scene" else "")]))
    return pages


# ---------- AI 페이지 작성 ----------

class DraftPage(BaseModel):
    type: str = Field(description="페이지 타입 (골격의 타입을 기본으로)")
    label: str = Field(default="", description="작은 태그 (예: POINT 1). 카드에서만")
    headline: str = Field(default="", description="제목 25자 이내 (만화는 상단 캡션, 비워도 됨)")
    body: str = Field(default="", description="본문 90자 이내 (카드)")
    items: list[str] = Field(default_factory=list, description="checklist/summary/cta 항목 (각 25자 이내)")
    compare: Comparison | None = Field(default=None, description="comparison 페이지에서만")
    visual_query: str = Field(default="", description="사진이 어울리는 카드면 영어 검색어 2~4단어. 아니면 빈 문자열")
    emphasis: str = Field(default="", description="headline/body 안에서 형광펜으로 강조할 짧은 부분 (그대로 포함된 문자열)")
    source: str = Field(default="", description="근거 자료 제목 (사실을 담은 카드)")
    panels: list[ComicBeat] = Field(default_factory=list, description="만화 페이지의 컷 1~2개")
    caption: str = Field(default="", description="만화 페이지 하단 설명 (explanation_scene)")


class DraftPlan(BaseModel):
    pages: list[DraftPage]


PLAN_SYSTEM = """당신은 인스타그램 캐러셀(카드뉴스·인스타툰) 편집자입니다. Master Content 와 페이지 골격을 받아
각 페이지의 실제 문구와 만화 컷을 씁니다.

규칙:
- 골격의 장수와 순서를 기본으로 따른다. 내용상 더 나으면 본문 페이지 타입을 바꿔도 되지만 첫 장은 cover, 끝 장은 cta.
- 사실은 Master Content 의 facts·key_points 범위 안에서만. 숫자를 새로 만들지 않는다.
- 글자는 짧게: headline 25자, body 90자, 항목 25자, 말풍선 대사 40자 이내. 존댓말/반말은 캐릭터 말투를 따른다.
- 이미지 안에 글자를 넣지 않는다. visual_query 는 실제 사진이 내용을 보여 줄 때만 (실존 인물 얼굴·로고 금지).
- 만화 컷(panels): character_id 는 주어진 캐릭터 id, emotion 은 [EMOTIONS], pose 는 [POSES],
  camera 는 close_up|medium|wide, speech_bubble_position 은 [BUBBLES]. scene·background 는 그림 지시(한국어).
- cta 의 items 는 아이콘 아래 붙는 2~4글자 단어 2~4개 (예: 저장, 공유, 댓글). 이모지는 쓰지 않는다.
- dialogue_scene 은 컷 2개, 나머지 만화는 컷 1개. explanation_scene 은 caption 에 정보 문장을 넣는다.
- 만화는 정보를 이야기로 풀어 주는 역할: 상황 공감 → 궁금증 → 깨달음 흐름이 이어지게."""


def _plan_prompt(master: MasterContent, types: list[str], fmt: str, bible: CharacterBible | None) -> str:
    char = (f"[캐릭터] id={bible.id}, 이름={bible.name}, 역할={bible.role}, 성격={bible.personality}, "
            f"말투={bible.speech_style}" if bible else "[캐릭터] 없음 (만화 페이지를 쓰지 않는다)")
    return (f"[형식] {fmt}\n{char}\n[페이지 골격] {', '.join(f'{i + 1}:{t}' for i, t in enumerate(types))}\n\n"
            f"[Master Content]\n{master.model_dump_json(indent=1, exclude={'sources', 'hashtags'})}\n\n"
            f"[자료 제목] {', '.join(s.get('title', '') for s in master.sources[:5])}")


def _to_page(d: DraftPage) -> Page | None:
    if d.type in CARD_TYPES:
        return CardPage(type=d.type, label=d.label, headline=d.headline, body=d.body, items=d.items, compare=d.compare,
                        visual_query=d.visual_query, emphasis=d.emphasis, source=d.source)
    if d.type in COMIC_TYPES:
        return ComicPage(type=d.type, headline=d.headline, panels=d.panels, caption=d.caption, source=d.source,
                         emphasis=d.emphasis)
    return None


def _short(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def normalize(pages: list[Page], fmt: str, master: MasterContent, char_id: str | None,
              valid_chars: set[str]) -> list[Page]:
    """AI 가 쓴 계획을 규칙에 맞춘다. 실패한 부분은 규칙 페이지로 채운다."""
    pages = [p for p in pages if p is not None]
    allow_comic = fmt in ("insta_toon", "hybrid") and char_id
    out: list[Page] = []
    for p in pages:
        if isinstance(p, ComicPage) and not allow_comic:
            body = " ".join(b.dialogue for b in p.panels if b.dialogue)
            p = CardPage(type="info_card", headline=_short(p.headline or body, 28), body=_short(p.caption or body, 90),
                         source=p.source, emphasis=p.emphasis)
        if isinstance(p, ComicPage):
            p.panels = (p.panels or [_beat(char_id or "", 0, p.headline or master.title)])[:2]
            for k, b in enumerate(p.panels):
                if b.character_id not in valid_chars:
                    b.character_id = char_id or ""
                b.emotion = b.emotion if b.emotion in EMOTIONS else "neutral"
                b.pose = b.pose if b.pose in POSES else "standing"
                b.camera = b.camera if b.camera in ("close_up", "medium", "wide") else "medium"
                if b.speech_bubble_position not in BUBBLE_POSITIONS:
                    b.speech_bubble_position = ("top_right", "top_left")[k % 2]
                b.dialogue = _short(b.dialogue, 60)
            p.caption = _short(p.caption, 120)
            p.headline = _short(p.headline, 30)
        else:
            p.headline = _short(p.headline, 44)
            p.body = _short(p.body, 160)
            p.items = [_short(i, 40) for i in p.items if i and i.strip()][:6]
            if p.emphasis and p.emphasis not in f"{p.headline} {p.body}":
                p.emphasis = ""
            if p.type == "comparison" and not p.compare:
                p = CardPage(type="info_card", headline=p.headline, body=p.body, source=p.source)
            if p.type in ("checklist", "summary") and not p.items:
                p.items = [_short(x, 40) for x in (master.checklist or master.key_points)[:4]] or [p.body or p.headline]
        out.append(p)
    if not out or out[0].type != "cover":
        out = [p for p in out if p.type != "cover"]
        out.insert(0, rule_pages(["cover"], master, char_id or "")[0])
    if out[-1].type != "cta":
        out = [p for p in out if p.type != "cta"]
        out.append(rule_pages(["cta"], master, char_id or "")[0])
    middle = [p for p in out[1:-1] if p.type not in ("cover", "cta")]
    if len(middle) > MAX_PAGES - 2:
        middle = middle[:MAX_PAGES - 2]
    while len(middle) < MIN_PAGES - 2:
        middle.append(rule_pages(["info_card"], master, char_id or "")[0])
    if fmt == "hybrid" and allow_comic:
        kinds = {p.kind for p in middle}
        if "comic" not in kinds:     # 섞는 형식인데 한쪽만 나오면 첫 본문을 만화로
            middle[0] = rule_pages(["comic_scene"], master, char_id or "")[0]
        if "card" not in kinds:
            middle[-1] = rule_pages(["summary"], master, char_id or "")[0]
    return [out[0], *middle, out[-1]]


async def plan_pages(llm: dict[str, Any] | None, master: MasterContent, fmt: str, *, template: str,
                     character: CharacterBible | None, valid_chars: set[str], n_pages: int = DEFAULT_PAGES,
                     instructions: str = "") -> CarouselPlan:
    types = skeleton(fmt, master, n_pages)
    char_id = character.id if character else None
    method = "rules"
    pages: list[Page] = []
    if llm:
        prompt = _plan_prompt(master, types, fmt, character)
        if instructions.strip():
            prompt += f"\n[사용자 지침] {instructions.strip()}"
        system = (PLAN_SYSTEM.replace("[EMOTIONS]", "|".join(EMOTIONS)).replace("[POSES]", "|".join(POSES))
                  .replace("[BUBBLES]", "|".join(BUBBLE_POSITIONS)))
        try:
            draft = await ask_structured(llm, system, prompt, DraftPlan)
            pages = [_to_page(d) for d in draft.pages]
            pages = [p for p in pages if p is not None]
            method = "ai" if len(pages) >= MIN_PAGES - 2 else "rules"
        except Exception:  # noqa: BLE001 - AI 없이도 규칙으로 끝까지 만든다
            pages = []
    if method == "rules":
        pages = rule_pages(types, master, char_id or "")
    pages = normalize(pages, fmt, master, char_id, valid_chars)
    mid = pages[1:-1]
    n_comic = sum(1 for p in mid if p.kind == "comic")
    actual = {"card": round(100 * (len(mid) - n_comic) / len(mid)), "comic": round(100 * n_comic / len(mid))}
    return CarouselPlan(format=fmt, template=template, mix=actual, pages=pages, method=method)
