"""주제 → 스토리(무료 규칙 | 선택 Claude) → 연출 → 무료 렌더 PNG. 검증된 사실만 쓴다.

    python -m app.factory toon --topic "9월 소비자물가와 내 장바구니" --facts-from-topic TOPIC_ID [--writer rules|claude]
    python -m app.factory toon --topic "…" --facts facts.json   # [{fact_id, claim, source_title, source_url}] — 사람이 확인한 사실

Claude 작가는 --writer claude 일 때만 부른다 (구독 CLI 경로, API 키를 비워 종량제로 넘어가지 않음).
초안이 검증(숫자·날짜·fact id·구조)에 실패하면 PNG 를 만들지 않고 status=rejected 와 이유를 돌려준다.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import core
from ..carousel import pipeline as carouselmod
from ..carousel.story_writer import StoryRejected, VerifiedFact, write_story
from ..pipeline.models import ResearchDoc


def facts_from_topic(topic_id: str) -> tuple[list[VerifiedFact], list[str]]:
    """Topic Strategy 저장소에서 verified 사실만. 게시 가능 여부(유효기간)는 경고로 알린다."""
    from ..topics.store import Store
    from ..topics.story import source_label
    from ..topics.verification import eligible
    store = Store(core.output_root() / "_factory" / "topics")
    topic = store.get(topic_id)
    docs = {e.evidence_id: e for e in store.evidence(topic)}
    out = []
    for f in topic.facts:
        if f.verification != "verified" or not f.citations or f.citations[0].evidence_id not in docs:
            continue
        e = docs[f.citations[0].evidence_id]
        out.append(VerifiedFact(fact_id=f.fact_id, claim=f.claim, source_title=source_label(e), source_url=e.url))
    warnings = [] if eligible(topic) else ["주제의 검증 유효기간이 지났거나 게시 조건이 아닙니다 — 게시 전 topics verify 로 재검증하세요"]
    return out, warnings


def facts_from_file(path: str) -> list[VerifiedFact]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [VerifiedFact.model_validate(r) for r in rows]


async def run(topic: str, *, facts: list[VerifiedFact], writer: str = "rules", fmt: str = "insta_toon",
              warnings: list[str] | None = None, log=print) -> dict[str, Any]:
    cfg = core._run_cfg({"preset": "daily", "llm": None, "visuals": "cards"})
    cfg["carousel"] = {**cfg.get("carousel", {}), "image_provider": "none", "image_search": False}
    job = core.output_root() / (dt.datetime.now().strftime("%Y%m%d_%H%M%S") + f"_toon_{writer}")
    job.mkdir(parents=True, exist_ok=True)
    calls: list[dict] = []
    try:
        with core.llmmod.provider_session(cfg["llm"], calls.append):
            plan, master, draft, report = await write_story(topic, facts, writer=writer, llm=cfg["llm"], fmt=fmt)
    except StoryRejected as e:
        (job / "story_rejected.json").write_text(json.dumps(
            {"reasons": e.reasons, "draft": e.draft.model_dump() if e.draft else None}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return {"status": "rejected", "reasons": e.reasons, "project_dir": str(job), "ai_calls": calls,
                "message": "스토리 초안이 검증을 통과하지 못해 자동으로 쓰지 않았습니다."}
    (job / "story.json").write_text(json.dumps({"draft": draft.model_dump(), "report": report,
                                                "facts": [f.model_dump() for f in facts]}, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    docs = [ResearchDoc(title=f.source_title, url=f.source_url, text=f.claim) for f in facts]
    out = await carouselmod.run_carousel(job, fmt=fmt, mode="script", text=topic, cfg=cfg, image_search=False,
                                         inputs={"topic": topic, "docs": docs}, prepared_master=master,
                                         prepared_plan=plan, progress=lambda *a: None)
    with (Path(out["dir"]) / "caption.txt").open("a", encoding="utf-8") as fh:
        fh.write("\n캐릭터 상황과 대사는 창작이며, 수치는 출처 기관의 공식 발표 원문입니다.\n")
    return {"status": "render_complete", "writer": writer, "project_dir": str(job), "dir": out["dir"], "pages": out["pages"],
            "fallback_pages": out["fallback_pages"], "facts_used": report["facts_used"], "warnings": warnings or [],
            "ai_calls": calls, "ai_provider_used": calls[-1]["provider"] if calls else "none"}
