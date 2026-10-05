"""완성 대본을 문장 경계에서만 나누고, AI가 이야기 흐름과 화면을 설계한다."""
from __future__ import annotations

import re
import math

from pydantic import BaseModel, Field

from .llm import ask_structured
from .models import PlannedScene, PlannedScript
from .script import CHARS_PER_SEC


VISUAL_TYPES = {"generated_image", "stock_image", "stock_video", "source_material",
                "chart", "text_card", "motion_graphic"}
MOTIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right", "static"}
TRANSITIONS = {"cut", "fade"}


CONTENT_KINDS = ("hook", "subject", "number", "comparison", "trend", "story", "claim", "concept", "conclusion")
EMPHASIS_MAX = 12   # 상단 키워드·카드 강조문구 최대 글자 수 (9:16 한 줄에 들어가는 길이)

_KIND_DESC = ("장면 내용 성격: hook(시선 끄는 도입), subject(인물·물건·장소·사건 설명), number(중요한 숫자·기록·금액), "
              "comparison(두 대상 비교), trend(시간에 따른 변화), story(이야기·사연), claim(핵심 주장), "
              "concept(개념·원리 설명), conclusion(결론·정리) 중 하나")


class SplitScene(BaseModel):
    sentence_ids: list[int] = Field(description="순서대로 묶을 문장 번호. 원문은 고치지 않는다")
    scene_type: str = Field(description="Hook/상황/핵심/변화/근거/결론/CTA 중 적절한 이야기 역할")
    visual_type: str = Field(description="화면 종류")
    visual_description: str = Field(description="화면에 보여줄 내용. 미확인 사실이나 실제 인물 얼굴을 만들지 않는다")
    emphasis_text: str = Field(description=f"화면 강조 문구. {EMPHASIS_MAX}자 이내의 짧은 구. 문장 전체를 넣지 않는다")
    motion: str = Field(description="zoom_in/zoom_out/pan_left/pan_right/static")
    transition: str = Field(description="cut/fade")
    source_requirement: str = Field(description="필요한 소스 권리와 근거. 허용 자료가 없으면 internal_generated")
    notes: str = Field(description="편집 메모, 없으면 빈 문자열")
    content_kind: str = Field(default="", description=_KIND_DESC)
    key_number: str = Field(default="", description="장면에 실제로 나오는 핵심 숫자와 단위(예: 3배, 40%). 없으면 빈 문자열")
    compare_a: str = Field(default="", description="비교 장면이면 첫째 대상(짧게), 아니면 빈 문자열")
    compare_b: str = Field(default="", description="비교 장면이면 둘째 대상(짧게), 아니면 빈 문자열")


class SplitPlan(BaseModel):
    scenes: list[SplitScene]


# ---------- 2D: 분야와 무관한 장면 내용 분석 (AI 실패 대비 + AI 결과 검증) ----------

_NUM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(퍼센트|%|배|명|만\s?원|억\s?원|조\s?원|억|조|원|년|개월|개|위|kg|km|시간|분|초|살|세|번|점|달러|도|m)?")
_UP = ("증가", "늘었", "늘어", "올랐", "오른", "상승", "급등", "커졌", "많아", "높아", "치솟")
_DOWN = ("감소", "줄었", "줄어", "내렸", "내린", "하락", "급락", "작아", "적어", "낮아", "떨어")
_COMPARE = ("보다", " vs ", " VS ", "반면", "에 비해", "대비", "와 달리", "과 달리", "차이")
_STORY = ("그날", "어느 날", "사연", "그때", "당시", "했는데", "였는데", "했습니다", "였습니다")
_CLAIM = ("핵심", "중요한", "이유", "결국", "진짜", "비밀", "답은", "사실은")
_CONNECT = ("그래서", "하지만", "그런데", "사실", "결국", "그리고", "이제", "또한", "즉", "특히", "게다가", "반면", "예를 들어")
_PARTICLES = ("으로", "에서", "에게", "까지", "부터", "처럼", "보다", "이라", "라는", "은", "는", "이", "가", "을", "를",
              "에", "의", "도", "로", "와", "과", "만")
_REQUEST = {"hook": "generated_image", "subject": "generated_image", "story": "generated_image",
            "concept": "generated_image", "claim": "generated_image", "conclusion": "generated_image",
            "number": "text_card", "comparison": "text_card", "trend": "chart"}


def find_number(text: str) -> str:
    """장면에 실제로 적힌 숫자+단위. 날짜처럼 뜻이 약한 숫자보다 단위가 붙은 숫자를 먼저 고른다."""
    hits = [(m.group(1), (m.group(2) or "").replace(" ", "")) for m in _NUM_RE.finditer(text)]
    if not hits:
        return ""
    unit_hits = [h for h in hits if h[1] and h[1] != "년"] or hits
    num, unit = unit_hits[0]
    return num + ("%" if unit == "퍼센트" else unit)


def trend_direction(text: str) -> str:
    up = any(w in text for w in _UP)
    down = any(w in text for w in _DOWN)
    return "up" if up and not down else "down" if down and not up else ""


def _strip_particle(word: str) -> str:
    for p in _PARTICLES:
        if word.endswith(p) and len(word) > len(p) + 1:
            return word[: -len(p)]
    return word


def _clip_words(words: list[str], max_chars: int, from_end: bool = False) -> str:
    seq = list(reversed(words)) if from_end else words
    out: list[str] = []
    for w in seq:
        if len(" ".join([*out, w])) > max_chars:
            break
        out.append(w)
    if not out and seq:
        return seq[0][:max_chars]
    return " ".join(reversed(out) if from_end else out)


def compare_pair(text: str) -> tuple[str, str]:
    """두 대상 비교를 짧게 뽑는다. 확실하지 않으면 빈 값."""
    for sep in (" vs ", " VS "):
        if sep in text:
            a, b = text.split(sep, 1)
            return _clip_words(a.split(), 8, from_end=True), _clip_words(b.split(), 8)
    if "반면" in text:
        a, b = text.split("반면", 1)
        return (_strip_particle(_clip_words(a.strip(" ,.").split(), 10)),
                _strip_particle(_clip_words(b.strip(" ,.").split(), 10)))
    m = re.search(r"(\S+)(?:보다|에 비해)\s+(\S+)", text)
    if m:
        return _strip_particle(m.group(1)), _strip_particle(m.group(2))
    return "", ""


def classify(text: str, index: int, count: int) -> str:
    number = find_number(text)
    if any(c in text for c in _COMPARE) and all(compare_pair(text)):
        return "comparison"
    if number and trend_direction(text):
        return "trend"
    if number:
        return "number"
    if index == 0:
        return "hook"
    if index == count - 1:
        return "conclusion"
    if any(c in text for c in _CLAIM):
        return "claim"
    if any(c in text for c in _STORY):
        return "story"
    return "subject"


def short_phrase(text: str, kind: str = "", number: str = "", max_chars: int = EMPHASIS_MAX) -> str:
    """문장 전체가 아니라 화면에 들어갈 짧은 핵심 구. 대본에 없는 말은 만들지 않는다."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    if kind == "trend" and number:
        word = next((w for w in (*_UP, *_DOWN) if w in text), "")
        base = {"늘었": "증가", "늘어": "증가", "올랐": "상승", "오른": "상승", "줄었": "감소", "줄어": "감소",
                "내렸": "하락", "내린": "하락", "떨어": "하락"}.get(word, word)
        return f"{number} {base}".strip()[:max_chars]
    first = re.split(r"(?<=[.!?。？！])\s+", text)[0].strip()
    if first.endswith("?") or first.endswith("요?"):
        core = re.sub(r"(요)?\?$", "", first)
        return (_clip_words(core.split(), max_chars - 1, from_end=True) + "?")[:max_chars]
    words = first.rstrip(".!").split()
    while words and words[0].strip(",") in _CONNECT:
        words = words[1:]
    phrase = _clip_words(words, max_chars)
    parts = phrase.split()
    if parts:
        parts[-1] = _strip_particle(parts[-1])
    return " ".join(parts)[:max_chars]


def analyze_scene(narration: str, index: int, count: int) -> dict:
    """AI 없이도 쓸 수 있는 장면 설계 (분야 무관 규칙)."""
    kind = classify(narration, index, count)
    number = find_number(narration) if kind in ("number", "trend") else ""
    a, b = compare_pair(narration) if kind == "comparison" else ("", "")
    role = {"hook": "Hook", "conclusion": "결론", "comparison": "비교", "trend": "변화", "number": "근거"}.get(kind, "핵심")
    if index == 0:
        role = "Hook"
    elif index == count - 1:
        role = "결론"
    return {"scene_type": role, "content_kind": kind, "visual_type": _REQUEST[kind],
            "emphasis_text": short_phrase(narration, kind, number), "key_number": number,
            "compare_a": a, "compare_b": b}


def _number_in_text(number: str, text: str) -> bool:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", number)
    return bool(m) and m.group(0).replace(",", "") in text.replace(",", "")


def _checked(narration: str, note: dict, index: int, count: int) -> dict:
    """AI 설계를 검증한다: 없는 숫자를 지어내지 않았는지, 강조문구가 짧은지, 종류가 올바른지."""
    rule = analyze_scene(narration, index, count)
    kind = note.get("content_kind") if note.get("content_kind") in CONTENT_KINDS else rule["content_kind"]
    number = note.get("key_number", "").strip()
    if number and not _number_in_text(number, narration):
        number = ""   # 대본에 없는 숫자는 쓰지 않는다
    if kind in ("number", "trend") and not number:
        number = find_number(narration)
        if not number:
            kind = rule["content_kind"] if rule["content_kind"] not in ("number", "trend") else "claim"
    a, b = note.get("compare_a", "").strip(), note.get("compare_b", "").strip()
    if kind == "comparison" and not (a and b):
        a, b = compare_pair(narration)
        if not (a and b):
            kind = "claim"
    emphasis = " ".join(str(note.get("emphasis_text", "")).split())
    if not emphasis or len(emphasis) > EMPHASIS_MAX or emphasis == narration.strip():
        emphasis = short_phrase(emphasis if emphasis and emphasis != narration.strip() else narration, kind, number)
    return {**note, "content_kind": kind, "key_number": number if kind in ("number", "trend") else "",
            "compare_a": a[:14] if kind == "comparison" else "", "compare_b": b[:14] if kind == "comparison" else "",
            "emphasis_text": emphasis}


def sentences(text: str) -> list[str]:
    """빈 줄·문장 끝 표지를 경계로 삼아 원문 낭독 순서를 유지한다."""
    clean = text.strip()
    if not clean:
        raise ValueError("완성 대본을 입력해 주세요.")
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", clean)
    units = [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]
    if len(units) < 4:
        raise ValueError("장면을 나누려면 완성 대본을 최소 4문장으로 입력해 주세요. 문장 끝에는 마침표나 물음표를 넣어 주세요.")
    return units


def _groups(units: list[str]) -> list[list[int]]:
    """AI 실패 때 문장 중간을 자르지 않는 길이 균형 분할."""
    count = min(8, max(4, math.ceil(sum(len(s) for s in units) / (CHARS_PER_SEC * 6.3))))
    count = min(count, len(units))
    n = len(units)
    prefix = [0]
    for unit in units:
        prefix.append(prefix[-1] + len(unit))
    target = prefix[-1] / count
    costs = [[float("inf")] * (n + 1) for _ in range(count + 1)]
    previous = [[0] * (n + 1) for _ in range(count + 1)]
    costs[0][0] = 0.0
    for used in range(1, count + 1):
        for end in range(used, n - (count - used) + 1):
            for start in range(used - 1, end):
                chars = prefix[end] - prefix[start]
                penalty = max(0, chars - CHARS_PER_SEC * 10) ** 2 * 4
                score = costs[used - 1][start] + (chars - target) ** 2 + penalty
                if score < costs[used][end]:
                    costs[used][end], previous[used][end] = score, start
    groups: list[list[int]] = []
    end = n
    for used in range(count, 0, -1):
        start = previous[used][end]
        groups.append(list(range(start + 1, end + 1)))
        end = start
    return list(reversed(groups))


def _fallback(units: list[str]) -> SplitPlan:
    groups = _groups(units)
    scenes = []
    for i, ids in enumerate(groups):
        narration = " ".join(units[j - 1] for j in ids)
        info = analyze_scene(narration, i, len(groups))   # 강조문구는 짧은 핵심 구 (문장 전체 X)
        scenes.append(SplitScene(sentence_ids=ids, scene_type=info["scene_type"], visual_type=info["visual_type"],
                                 visual_description=f"장면 내용을 보여주는 화면: {narration[:60]}",
                                 emphasis_text=info["emphasis_text"], motion="zoom_in" if i % 2 == 0 else "zoom_out",
                                 transition="cut" if i == 0 else "fade", source_requirement="internal_generated",
                                 notes="AI 응답 오류로 문장 경계 기준 자동 분할",
                                 content_kind=info["content_kind"], key_number=info["key_number"],
                                 compare_a=info["compare_a"], compare_b=info["compare_b"]))
    return SplitPlan(scenes=scenes)


_PLAN_RULES = (
    "각 장면의 content_kind 는 내용 성격으로 고릅니다: hook(도입), subject(인물·물건·장소·사건), number(중요한 숫자), "
    "comparison(두 대상 비교), trend(시간에 따른 변화), story(이야기·사연), claim(핵심 주장), concept(개념), conclusion(결론). "
    "분야가 아니라 문장 내용으로 판단하세요. "
    f"emphasis_text 는 화면에 크게 들어갈 {EMPHASIS_MAX}자 이내의 짧은 구입니다(예: '3배 증가', '진짜 이유는?', '마지막 반전'). "
    "문장 전체를 넣지 마세요. key_number 는 장면 문장에 실제로 있는 숫자만 단위와 함께 쓰고, 없으면 빈 문자열입니다. "
    "comparison 이면 compare_a/compare_b 에 두 대상을 짧게 적습니다.")


class SceneNote(BaseModel):
    index: int = Field(description="장면 번호 (0부터)")
    scene_type: str = Field(description="Hook/상황/핵심/변화/근거/비교/결론/CTA 중 이야기 역할")
    content_kind: str = Field(description=_KIND_DESC)
    visual_type: str = Field(description="generated_image, stock_image, stock_video, source_material, chart, text_card, motion_graphic 중 하나")
    visual_description: str = Field(description="화면에 보여줄 내용. 실존 인물 얼굴·확인 안 된 사실을 만들지 않는다")
    emphasis_text: str = Field(description=f"화면 강조 문구. {EMPHASIS_MAX}자 이내의 짧은 구")
    key_number: str = Field(description="장면에 실제로 나오는 핵심 숫자와 단위. 없으면 빈 문자열")
    compare_a: str = Field(description="비교 장면이면 첫째 대상, 아니면 빈 문자열")
    compare_b: str = Field(description="비교 장면이면 둘째 대상, 아니면 빈 문자열")
    source_requirement: str = Field(description="필요한 소스 권리. 확인된 자료가 없으면 internal_generated")
    motion: str = Field(description="zoom_in/zoom_out/pan_left/pan_right/static")
    transition: str = Field(description="cut/fade")


class SceneNotes(BaseModel):
    scenes: list[SceneNote]


MAX_SCENES = 8


def _merge_to_max(scenes: list, limit: int = MAX_SCENES) -> list:
    """AI 대본 장면이 너무 많으면 가장 짧은 이웃끼리 합친다. 문장은 그대로, 순서도 그대로."""
    scenes = [s.model_copy() for s in scenes]
    while len(scenes) > limit:
        k = min(range(len(scenes) - 1), key=lambda i: len(scenes[i].narration) + len(scenes[i + 1].narration))
        a, b = scenes[k], scenes.pop(k + 1)
        a.narration = f"{a.narration.strip()} {b.narration.strip()}"
    return scenes


async def annotate_script(llm: dict, script, *, preset: dict | None = None,
                          instructions: str = "") -> tuple[PlannedScript, str]:
    """AI 가 쓴 대본(자동 모드)에 2B 와 같은 장면 설계 정보를 붙인다. 나레이션은 고치지 않는다.

    반환: (장면 설계가 붙은 대본, "ai" | "rules"). AI 가 실패하거나 형식이 틀리면 분야 무관 규칙으로 채운다.
    """
    scenes = _merge_to_max(list(script.scenes))
    count = len(scenes)
    system = ("당신은 한국어 쇼츠 편집감독입니다. 이미 완성된 장면별 대본을 받습니다. 문장은 고치지 말고 "
              "각 장면의 이야기 역할·내용 성격·화면 계획·짧은 강조문구를 정하세요. 첫 장면은 Hook, 마지막은 결론입니다. "
              "화면 계획일 뿐 사용권을 보증하지 않습니다. 다른 사람 영상·기사·댓글은 화면 소재로 쓰지 마세요. "
              + _PLAN_RULES)
    listing = "\n".join(f"{i}. {s.narration}" for i, s in enumerate(scenes))
    user = f"[프리셋] {(preset or {}).get('name', '')}\n[지침] {instructions}\n[주제] {script.topic}\n[장면]\n{listing}"
    method = "ai"
    notes: dict[int, dict] = {}
    try:
        result = await ask_structured(llm, system, user, SceneNotes)
        for n in result.scenes:
            if 0 <= n.index < count:
                _normalize(n, scenes[n.index].narration, n.index, count)   # 틀린 이름만 고쳐 쓴다
        notes = {n.index: n.model_dump() for n in result.scenes if 0 <= n.index < count}
        if len(notes) != count:
            raise ValueError("장면 수가 맞지 않습니다")
    except Exception:
        method = "rules"
        notes = {i: analyze_scene(s.narration, i, count) for i, s in enumerate(scenes)}
    planned: list[PlannedScene] = []
    for i, s in enumerate(scenes):
        own = " ".join(s.on_screen_text.split())
        if own and len(own) <= EMPHASIS_MAX and own != s.narration.strip():
            notes[i] = {**notes[i], "emphasis_text": own}   # 대본 작가가 이미 짧게 뽑은 키워드는 그대로 쓴다
        note = _checked(s.narration, notes[i], i, count)
        planned.append(PlannedScene(
            narration=s.narration, image_prompt=s.image_prompt, subtitle=s.narration,
            beat_role=getattr(s, "beat_role", ""),
            on_screen_text=note["emphasis_text"], scene_type=str(note.get("scene_type", "")).strip(),
            visual_type=note.get("visual_type", "generated_image"),
            visual_description=str(note.get("visual_description", "")).strip() or s.image_prompt,
            source_requirement=str(note.get("source_requirement", "")).strip() or "internal_generated",
            motion=note.get("motion") if note.get("motion") in MOTIONS else ("zoom_in" if i % 2 == 0 else "zoom_out"),
            transition=note.get("transition") if note.get("transition") in TRANSITIONS else ("cut" if i == 0 else "fade"),
            content_kind=note["content_kind"], key_number=note["key_number"],
            compare_a=note["compare_a"], compare_b=note["compare_b"],
            notes="" if method == "ai" else "AI 장면 분석 실패로 규칙 기반 설계"))
    data = script.model_dump()
    data["scenes"] = [p.model_dump() for p in planned]
    return PlannedScript.model_validate(data), method


def _normalize(scene, narration: str, index: int, count: int) -> None:
    """AI 가 화면 종류·움직임·전환을 정해진 이름 대신 자유 문구로 답해도 계획 전체를 버리지 않는다.

    틀린 값만 내용 성격에 맞는 기본값으로 바꾼다 (문장 묶음·장면 수 같은 구조 오류는 여전히 거절).
    """
    if scene.visual_type not in VISUAL_TYPES:
        kind = scene.content_kind if scene.content_kind in CONTENT_KINDS else classify(narration, index, count)
        scene.visual_type = _REQUEST.get(kind, "generated_image")
    if scene.motion not in MOTIONS:
        scene.motion = "zoom_in" if index % 2 == 0 else "zoom_out"
    if scene.transition not in TRANSITIONS:
        scene.transition = "cut" if index == 0 else "fade"


def _validate(plan: SplitPlan, units: list[str]) -> None:
    if not 4 <= len(plan.scenes) <= 8:
        raise ValueError("장면 수는 4~8개여야 합니다.")
    flat = [number for scene in plan.scenes for number in scene.sentence_ids]
    if flat != list(range(1, len(units) + 1)) or any(not scene.sentence_ids for scene in plan.scenes):
        raise ValueError("원문 문장을 빠짐없이 순서대로 사용해야 합니다.")
    for i, scene in enumerate(plan.scenes):
        _normalize(scene, " ".join(units[j - 1] for j in scene.sentence_ids), i, len(plan.scenes))
        chars = sum(len(units[j - 1]) for j in scene.sentence_ids)
        longest_sentence = max(len(unit) for unit in units)
        if chars / CHARS_PER_SEC > max(11, longest_sentence / CHARS_PER_SEC + 1):
            raise ValueError("한 장면이 너무 깁니다.")


async def split_finished_script(llm: dict, text: str, *, preset: dict | None = None,
                                instructions: str = "") -> tuple[PlannedScript, str]:
    """기존 Claude/GPT 구조화 호출을 이용하고, 실패하면 안전한 기본 계획을 반환한다."""
    units = sentences(text)
    system = ("당신은 한국어 쇼츠 편집감독입니다. 완성된 대본의 문장을 고치거나 생략하지 말고 "
              "의미와 전개에 따라 연속된 문장 번호를 4~8개 장면으로 묶으세요. "
              "첫 장면은 Hook, 마지막은 결론/CTA이며 중간은 상황·핵심·변화·근거 중 내용에 맞게 고르세요. "
              "장면당 약 3~10초를 지향하되 문장 경계를 우선합니다. "
              "화면 종류는 generated_image, stock_image, stock_video, source_material, chart, text_card, motion_graphic 중 하나입니다. "
              "화면 계획일 뿐 사용권을 보증하지 않습니다. 다른 사람 영상·기사·댓글 원문은 화면 소재로 쓰지 마세요. "
              "확인된 권리 소스가 없다면 internal_generated를 요구하고 내부 생성 카드로 대체합니다. "
              "실존 인물 얼굴을 생성하도록 지시하지 마세요. 숫자/주장은 검증하지 않은 채 사실로 덧붙이지 마세요. "
              + _PLAN_RULES)
    numbered = "\n".join(f"{i}. {unit}" for i, unit in enumerate(units, 1))
    user = f"[프리셋] {(preset or {}).get('name', '')}\n[지침] {instructions}\n[원문 문장]\n{numbered}"
    method = "ai"
    try:
        plan = await ask_structured(llm, system, user, SplitPlan)
        _validate(plan, units)
    except Exception:
        plan = _fallback(units)
        method = "fallback"
    scenes: list[PlannedScene] = []
    for i, item in enumerate(plan.scenes):
        narration = " ".join(units[j - 1] for j in item.sentence_ids)
        # 외부 소스는 이 단계에서 검색/승인되지 않았으므로 실제 렌더는 내부 카드로 안전하게 진행한다.
        prompt = item.visual_description.strip() or narration[:80]
        note = _checked(narration, item.model_dump(), i, len(plan.scenes))
        scenes.append(PlannedScene(narration=narration, image_prompt=prompt,
                            on_screen_text=note["emphasis_text"], subtitle=narration,
                            scene_type=item.scene_type.strip(), visual_type=item.visual_type,
                            visual_description=prompt, source_requirement=item.source_requirement.strip(),
                            notes=item.notes.strip(), motion=item.motion, transition=item.transition,
                            content_kind=note["content_kind"], key_number=note["key_number"],
                            compare_a=note["compare_a"], compare_b=note["compare_b"]))
    topic = units[0][:60]
    script = PlannedScript(topic=topic, scenes=scenes, titles=[topic[:30]],
                    description="사용자가 입력한 완성 대본으로 제작한 쇼츠입니다. 사실과 출처는 게시 전에 확인해 주세요.",
                    hashtags=[], sources=[])
    return script, method
