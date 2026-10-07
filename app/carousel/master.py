"""Master Content — 입력(주제·기사·유튜브·원고·리서치)을 분석해 형식과 무관한 핵심 내용 하나로 만든다.

카드뉴스·인스타툰·하이브리드는 모두 이 결과에서 파생된다. AI 1회, 실패하면 규칙으로 만든다.
"""
from __future__ import annotations

import re
from typing import Any

from ..pipeline.llm import ask_structured
from ..pipeline.models import ResearchDoc
from ..pipeline.script import _docs_block
from .schema import MasterContent, MasterFact

MASTER_SYSTEM = """당신은 한국어 인스타그램 카드뉴스·인스타툰 기획 에디터입니다.
조사 자료를 읽고, 여러 형식(카드뉴스·인스타툰·쇼츠)에 공통으로 쓸 핵심 내용(Master Content)을 정리합니다.

규칙:
- 자료에서 확인된 사실만 facts 에 넣고 source_index 로 근거 자료 번호를 적는다. 숫자·날짜를 지어내지 않는다.
- 모든 문장은 짧고 쉬운 한국어. 카드 한 장에 들어갈 길이(key_points 40자, checklist 25자 이내).
- story_score: 내용이 정보·방법·수치 중심이면 0~0.3, 일반 이슈면 0.4~0.6, 사연·상황·감정 흐름이 중심이면 0.7~1.
- story_beats: 독자가 공감할 상황을 인물이 겪는 일로 2~5줄 (인스타툰용). 실제 사건처럼 꾸미지 말고 일반적인 상황으로.
- comparison 은 비교 요소가 있을 때만, quote 는 자료에 실제 발언·인용이 있을 때만 채운다.
- cta 는 저장·공유·댓글을 자연스럽게 유도하는 한 문장."""


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s*|\n+", text or "")
    return [" ".join(p.split()) for p in parts if len(" ".join(p.split())) >= 12]


def rule_master(topic: str, docs: list[ResearchDoc], script_text: str = "") -> MasterContent:
    """AI 없이 만드는 Master Content. 자료 문장을 그대로 잘라 쓰므로 사실을 새로 만들지 않는다."""
    facts: list[MasterFact] = []
    pool = [(0, s) for s in _sentences(script_text)] if script_text else []
    for i, d in enumerate(docs, start=1):
        pool += [(i, s) for s in _sentences(d.text)[:6]]
    seen: set[str] = set()
    for idx, s in pool:
        key = s[:20]
        if key in seen:
            continue
        seen.add(key)
        facts.append(MasterFact(text=s[:120], source_index=idx))
        if len(facts) >= 8:
            break
    points = [f.text[:60] for f in facts[:5]]
    title = (topic or (docs[0].title if docs else "") or "오늘의 정리")[:30]
    return MasterContent(
        topic=topic or title, title=title, subtitle="", hook=f"{title}, 알고 계셨나요?", angle="",
        story_score=0.5 if not script_text else 0.6, key_points=points or [title], facts=facts,
        checklist=[], comparison=None, quote="", quote_by="", story_beats=[],
        summary=points[0] if points else title, cta="도움이 됐다면 저장하고 필요한 사람에게 공유해 주세요",
        hashtags=[], sources=[{"title": d.title, "url": d.url} for d in docs if d.url])


async def build_master(llm: dict[str, Any], topic: str, docs: list[ResearchDoc], *, script_text: str = "",
                       instructions: str = "", source_info: str = "") -> tuple[MasterContent, str]:
    """(Master Content, 방법 'ai'|'rules')."""
    user = (f"[주제] {topic}\n"
            + (f"[참고 원본] {source_info}\n" if source_info else "")
            + (f"[사용자 지침] {instructions.strip()}\n" if instructions.strip() else "")
            + (f"\n## 직접 입력 원고 (문장 의미를 바꾸지 말 것)\n{script_text[:6000]}\n" if script_text else "")
            + f"\n## 조사 자료\n{_docs_block(docs, limit_chars=2500) if docs else '(없음)'}")
    try:
        master = await ask_structured(llm, MASTER_SYSTEM, user, MasterContent)
        master.story_score = max(0.0, min(1.0, float(master.story_score)))
        if not master.sources:
            master.sources = [{"title": d.title, "url": d.url} for d in docs if d.url]
        return master, "ai"
    except Exception:  # noqa: BLE001 - AI 가 없어도 자료 문장으로 계속 만든다
        return rule_master(topic, docs, script_text), "rules"
