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


class SplitScene(BaseModel):
    sentence_ids: list[int] = Field(description="순서대로 묶을 문장 번호. 원문은 고치지 않는다")
    scene_type: str = Field(description="Hook/상황/핵심/변화/근거/결론/CTA 중 적절한 이야기 역할")
    visual_type: str = Field(description="화면 종류")
    visual_description: str = Field(description="화면에 보여줄 내용. 미확인 사실이나 실제 인물 얼굴을 만들지 않는다")
    emphasis_text: str = Field(description="강조 문구, 없으면 빈 문자열")
    motion: str = Field(description="zoom_in/zoom_out/pan_left/pan_right/static")
    transition: str = Field(description="cut/fade")
    source_requirement: str = Field(description="필요한 소스 권리와 근거. 허용 자료가 없으면 internal_generated")
    notes: str = Field(description="편집 메모, 없으면 빈 문자열")


class SplitPlan(BaseModel):
    scenes: list[SplitScene]


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
        role = "Hook" if i == 0 else "결론" if i == len(groups) - 1 else "핵심 정보"
        narration = " ".join(units[j - 1] for j in ids)
        scenes.append(SplitScene(sentence_ids=ids, scene_type=role, visual_type="text_card",
                                 visual_description=f"대본 핵심을 보여주는 내부 생성 배경 카드: {narration[:60]}",
                                 emphasis_text=units[ids[0] - 1][:24], motion="zoom_in" if i % 2 == 0 else "zoom_out",
                                 transition="cut" if i == 0 else "fade", source_requirement="internal_generated",
                                 notes="AI 응답 오류로 문장 경계 기준 자동 분할"))
    return SplitPlan(scenes=scenes)


def _validate(plan: SplitPlan, units: list[str]) -> None:
    if not 4 <= len(plan.scenes) <= 8:
        raise ValueError("장면 수는 4~8개여야 합니다.")
    flat = [number for scene in plan.scenes for number in scene.sentence_ids]
    if flat != list(range(1, len(units) + 1)) or any(not scene.sentence_ids for scene in plan.scenes):
        raise ValueError("원문 문장을 빠짐없이 순서대로 사용해야 합니다.")
    for scene in plan.scenes:
        if scene.visual_type not in VISUAL_TYPES or scene.motion not in MOTIONS or scene.transition not in TRANSITIONS:
            raise ValueError("지원하지 않는 화면 계획입니다.")
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
              "실존 인물 얼굴을 생성하도록 지시하지 마세요. 숫자/주장은 검증하지 않은 채 사실로 덧붙이지 마세요.")
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
    for item in plan.scenes:
        narration = " ".join(units[j - 1] for j in item.sentence_ids)
        # 외부 소스는 이 단계에서 검색/승인되지 않았으므로 실제 렌더는 내부 카드로 안전하게 진행한다.
        prompt = item.visual_description.strip() or narration[:80]
        scenes.append(PlannedScene(narration=narration, image_prompt=prompt,
                            on_screen_text=item.emphasis_text.strip()[:60], subtitle=narration,
                            scene_type=item.scene_type.strip(), visual_type=item.visual_type,
                            visual_description=prompt, source_requirement=item.source_requirement.strip(),
                            notes=item.notes.strip(), motion=item.motion, transition=item.transition))
    topic = units[0][:60]
    script = PlannedScript(topic=topic, scenes=scenes, titles=[topic[:30]],
                    description="사용자가 입력한 완성 대본으로 제작한 쇼츠입니다. 사실과 출처는 게시 전에 확인해 주세요.",
                    hashtags=[], sources=[])
    return script, method
