"""Claude로 쇼츠 대본 / 클립 계획 / 트렌드 선택 생성."""
from __future__ import annotations

from typing import Any

from .llm import ask_structured
from .models import AutoPlan, ClipPlan, ResearchDoc, Script, TrendPick

# 한국어 나레이션 읽기 속도(자/초).
# 실측값: edge-tts ko-KR-InJoonNeural, rate +5% 에서 412자 -> 64.9초 = 6.35 자/초.
# 이 값이 낮으면 글자수를 적게 요청해 영상이 목표보다 짧아지고, 높으면 길어진다.
# TTS provider 나 rate 를 바꾸면 다시 실측할 것.
CHARS_PER_SEC = 6.35


def _preset_block(preset: dict[str, Any]) -> str:
    return (
        f"[카테고리] {preset.get('name', '')} - {preset.get('description', '')}\n"
        f"[말투] {preset.get('tone', '')}\n"
        f"[대본 규칙]\n{preset.get('script_rules', '')}\n"
        f"[이미지 스타일 접두어] {preset.get('image_style', '')}"
    )


def _docs_block(docs: list[ResearchDoc], limit_chars: int = 2500) -> str:
    parts = []
    for i, d in enumerate(docs, 1):
        body = d.text[:limit_chars].strip()
        parts.append(f"### 자료 {i}: {d.title}\nURL: {d.url}\n{('날짜: ' + d.published) if d.published else ''}\n{body}")
    return "\n\n".join(parts) if parts else "(리서치 자료 없음 - 일반 지식으로 작성하되 불확실한 수치는 피할 것)"


SCRIPT_SYSTEM = """당신은 조회수가 잘 나오는 한국어 유튜브 쇼츠 대본 작가입니다.
세로형 쇼츠(9:16) 나레이션 대본을 장면 단위로 작성합니다.

공통 규칙:
- **글자수 상한을 반드시 지킨다.** 나레이션 전체 글자수(공백 포함)가 지정된 범위를 넘으면 안 된다.
  내용이 많으면 장면을 줄이거나 문장을 쳐내서 맞춘다. 범위를 넘기느니 정보를 빼는 쪽을 택한다.
- 첫 장면(훅)은 3초 안에 시청자를 붙잡는 한 문장. 두 번째 장면부터 본론.
- 한 장면은 나레이션 1~2문장, TTS가 읽기 좋게 구어체로. 괄호·이모지·특수기호 금지.
- 숫자는 한국어로 읽기 쉽게 쓴다 (예: 3만 5천 명).
- image_prompt는 영어로, 이미지 스타일 접두어를 앞에 붙이고, 실존 인물의 이름이나 얼굴 묘사는 절대 넣지 않는다. 글자가 들어가지 않게 "no text"를 포함한다.
- on_screen_text는 화면에 크게 뜨는 핵심 키워드. 짧고 임팩트 있게.
- titles는 클릭을 부르는 제목 3개, 30자 이내. description에는 핵심 요약과 출처 URL을 넣는다.
- 리서치 자료에 없는 사실을 지어내지 않는다.
"""


def _style_block(style: dict[str, Any] | None) -> str:
    if not style:
        return ""
    rows = [
        ("훅 공식", style.get("hook_pattern")),
        ("전개 구조", style.get("structure")),
        ("말투", style.get("tone")),
        ("문장 스타일", style.get("sentence_style")),
        ("장면 수·호흡", style.get("pacing")),
        ("마무리", style.get("cta")),
        ("기타", style.get("notes")),
    ]
    body = "\n".join(f"- {k}: {v}" for k, v in rows if str(v or "").strip())
    if not body:
        return ""
    return (
        f"\n[스타일 지침 — '{style.get('name', '')}']\n"
        "이 영상은 아래 스타일을 그대로 따라 만듭니다. 위의 카테고리 기본 규칙과 충돌하면 이 스타일을 따르세요.\n"
        f"{body}\n"
    )


def _autoplan_block(plan: AutoPlan | None) -> str:
    if not plan:
        return ""
    return (
        "\n[제작 방향 - 앞선 분석 결과]\n"
        f"- 접근 각도: {plan.angle}\n"
        f"- 훅 유형: {plan.hook_type}\n"
        f"- 전개 구조: {plan.structure}\n"
        f"- 장면 수: {plan.scene_count}개\n"
    )


def _instructions_block(instructions: str) -> str:
    if not instructions.strip():
        return ""
    return (
        "\n[사용자 지침 - 최우선]\n"
        "아래 지침은 위의 카테고리 기본 규칙보다 우선합니다. 충돌하면 이 지침을 따르세요.\n"
        f"{instructions.strip()}\n"
    )


async def write_script(llm: dict[str, Any], preset: dict[str, Any], topic: str, docs: list[ResearchDoc], target_seconds: int,
                       extra_context: str = "", instructions: str = "", style: dict[str, Any] | None = None,
                       plan: AutoPlan | None = None) -> Script:
    target_chars = int(target_seconds * CHARS_PER_SEC)
    lo, hi = int(target_chars * 0.9), target_chars
    n_scenes = plan.scene_count if plan else 8
    scene_count = f"{plan.scene_count}개 내외" if plan else "6~10개"
    user = (
        f"{_preset_block(preset)}\n"
        f"{_style_block(style)}"
        f"{_autoplan_block(plan)}"
        f"{_instructions_block(instructions)}\n"
        f"[주제] {topic}\n"
        f"[분량] 나레이션 전체 합계 {lo}~{hi}자 (공백 포함). {hi}자를 절대 넘기지 말 것.\n"
        f"  = 약 {target_seconds}초 분량이며, 장면 {n_scenes}개 기준 장면당 평균 {hi // max(1, n_scenes)}자.\n"
        f"  글자수를 세어 가며 쓰고, 넘칠 것 같으면 장면을 줄이세요.\n"
        f"[장면 수] {scene_count}\n\n"
        f"{('[추가 맥락]' + chr(10) + extra_context + chr(10) + chr(10)) if extra_context else ''}"
        f"## 리서치 자료\n{_docs_block(docs)}\n\n"
        "위 자료를 바탕으로 대본을 작성하세요. sources에는 실제로 참고한 자료의 URL만 넣으세요."
    )
    return await ask_structured(llm, SCRIPT_SYSTEM, user, Script)


AUTOPLAN_SYSTEM = """당신은 유튜브 쇼츠 PD입니다. 소재를 먼저 읽고, 이 소재를 어떤 구성으로 만들지 결정합니다.

규칙:
- 소재의 성격에 맞는 구성을 고른다. 사건·논란이면 시간순 브리핑, 개념이면 질문-설명-정리, 꿀팁이면 문제-해결-실천 식으로.
- visual_mode 판단: 실제 현장 화면이나 인물 발언이 있어야 설득되는 소재(사건, 발언, 경기, 공연)는 broll.
  개념·원리·팁처럼 그림으로 설명하는 게 나은 소재는 images.
- scene_count 는 6~10 사이에서 소재의 정보량에 맞춰 정한다.
- 모든 내용은 한국어로."""


async def make_plan(llm: dict[str, Any], preset: dict[str, Any], topic: str, docs: list[ResearchDoc],
                    target_seconds: int, instructions: str = "") -> AutoPlan:
    user = (
        f"{_preset_block(preset)}\n"
        f"{_instructions_block(instructions)}\n"
        f"[소재] {topic}\n[목표 길이] 약 {target_seconds}초\n\n"
        f"## 수집한 자료\n{_docs_block(docs, limit_chars=1500)}\n\n"
        "이 소재로 쇼츠를 만든다면 어떤 구성이 가장 좋을지 정하세요."
    )
    return await ask_structured(llm, AUTOPLAN_SYSTEM, user, AutoPlan)


CLIP_SYSTEM = """당신은 유튜브 롱폼 영상에서 쇼츠로 잘라낼 하이라이트를 고르는 편집자입니다.
타임스탬프가 붙은 자막을 보고, 하나의 완결된 이야기가 되도록 1~3개 구간을 고릅니다.

규칙:
- 구간 합계는 45~60초. 각 구간은 문장 경계에서 시작하고 끝나야 한다 (말 중간에 끊지 말 것).
- 첫 구간의 시작은 시청자를 바로 붙잡을 수 있는 강한 발언/장면이어야 한다.
- 구간은 시간순으로 정렬한다.
- titles/description/hashtags는 한국어로, 쇼츠 업로드에 바로 쓸 수 있게 작성한다.
"""


async def plan_clips(llm: dict[str, Any], preset: dict[str, Any], video_title: str, transcript_lines: list[str],
                     instructions: str = "", style: dict[str, Any] | None = None) -> ClipPlan:
    user = (
        f"{_preset_block(preset)}\n"
        f"{_style_block(style)}"
        f"{_instructions_block(instructions)}\n"
        f"[원본 영상 제목] {video_title}\n\n"
        "## 자막 (초 단위 타임스탬프)\n" + "\n".join(transcript_lines)
    )
    return await ask_structured(llm, CLIP_SYSTEM, user, ClipPlan)


TREND_SYSTEM = """당신은 유튜브 쇼츠 채널의 기획자입니다. 지금 뜨는 트렌드 키워드 목록에서
주어진 채널 카테고리에 가장 잘 맞고, 쇼츠 한 편으로 만들기 좋은 키워드 하나를 고릅니다.
카테고리와 관계없는 키워드(스포츠 경기 결과, 단순 검색어 등)는 피하고, 이야기 거리가 있는 것을 고르세요."""


async def pick_trend(llm: dict[str, Any], preset: dict[str, Any], trends: list[str], instructions: str = "") -> TrendPick:
    user = (f"{_preset_block(preset)}\n{_instructions_block(instructions)}\n"
            "## 현재 트렌드 키워드\n" + "\n".join(f"- {t}" for t in trends))
    return await ask_structured(llm, TREND_SYSTEM, user, TrendPick)
