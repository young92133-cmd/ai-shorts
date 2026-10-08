"""캐러셀 제작 흐름: 입력 수집 → Master Content → Format Planner → 그림 → Renderer → manifest.

쇼츠 엔진(app/pipeline)의 리서치·기사 수집·유튜브 자막·Source Resolver·소스 대장을 그대로 쓰고,
쇼츠 run_pipeline 은 건드리지 않는다. 결과는 <job_dir>/<format>/ 폴더에 쌓인다.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

from ..pipeline import article as articlemod, research, script as scriptmod, youtube
from ..pipeline import source_resolver
from ..pipeline.models import ResearchDoc
from ..pipeline.sources import SourceRegistry
from . import characters as charmod
from .master import build_master
from .planner import plan_pages
from .render import PageAssets, render_page
from .schema import CAROUSEL_FORMATS, CardPage, ComicPage, MasterContent, CarouselPlan
from .templates import load_template
from .visuals import CharacterArtist, find_card_images, guard_image, pinned_uploads

Progress = Callable[[str, int, str], None]
MANIFEST = "manifest.json"


def _noop(stage: str, pct: int, msg: str) -> None:
    print(f"[{stage:8s} {pct:3d}%] {msg}", flush=True)


def carousel_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    base = {"pages": 8, "character": charmod.DEFAULT_CHARACTER, "image_search": True, "max_images": 4,
            "image_provider": "none", "templates": {}}
    return {**base, **(cfg.get("carousel") or {})}


def load_research_file(path: str | Path) -> list[ResearchDoc]:
    """기존 리서치 결과 JSON: [{title, url, text}] 또는 {"docs": [...]}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("docs", data) if isinstance(data, dict) else data
    docs = [ResearchDoc(title=str(r.get("title", "")), url=str(r.get("url", "")), text=str(r.get("text", "")))
            for r in rows if isinstance(r, dict) and (r.get("text") or r.get("title"))]
    if not docs:
        raise ValueError("리서치 파일에 쓸 수 있는 자료가 없습니다 (title/url/text 목록이어야 합니다)")
    return docs


async def gather_inputs(mode: str, text: str, cfg: dict[str, Any], job_dir: Path, registry: SourceRegistry,
                        progress: Progress = _noop) -> dict[str, Any]:
    """입력 종류별 자료 수집. 쇼츠와 같은 모듈을 쓴다. {topic, docs, script_text, source_info}."""
    preset = cfg.get("preset") or {}
    topic, docs, script_text, source_info = text, [], "", ""
    if mode == "script":
        script_text = text
        topic = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")[:40]
        progress("research", 100, "직접 입력한 원고를 사용합니다. 별도 자료 조사는 하지 않습니다.")
    elif mode == "research":
        docs = load_research_file(text)
        topic = docs[0].title
        progress("research", 100, f"기존 리서치 결과 {len(docs)}건을 사용합니다.")
    elif mode == "url":
        urls = articlemod.split_urls(text)
        art = [u for u in urls if not articlemod.is_youtube(u)]
        yt = [u for u in urls if articlemod.is_youtube(u)]
        if art:
            progress("research", 10, f"링크 {len(art)}개 분석 중")
            docs, _ = await articlemod.fetch_articles(art, job_dir / "sourced", with_images=False,
                                                      log=lambda m: progress("research", 40, m))
            if not docs:
                raise RuntimeError("링크에서 본문을 읽지 못했습니다. 주소를 확인해 주세요.")
            topic = docs[0].title
            source_info = "참고 기사: " + " / ".join(d.title for d in docs)
        elif yt:
            progress("research", 10, "유튜브 정보 가져오는 중")
            info = await youtube.fetch_info(yt[0])
            rights = source_resolver.classify_youtube(info)
            registry.add(kind="video", origin="url", url=yt[0], title=info.get("title", ""), used_for="script_research",
                         source_type="youtube", usage=rights["usage"], rights_status=rights["rights_status"],
                         rights_basis=rights["rights_basis"])
            words = await youtube.fetch_transcript(yt[0], job_dir)
            body = youtube.words_to_text(words)[:12000] if words else info.get("description", "")
            topic = info.get("title", "")
            docs = [ResearchDoc(title=topic, url=info.get("webpage_url", yt[0]), text=body)]
            source_info = f"참고 유튜브: {topic} / 채널 {info.get('channel', '')} (내용 참고만, 화면에 쓰지 않음)"
    elif mode == "auto":
        kws = await research.hot_keywords(log=lambda m: progress("research", 8, m))
        if not kws:
            raise RuntimeError("트렌드 키워드를 가져오지 못했습니다. 주제를 직접 입력해 주세요.")
        pick = await scriptmod.pick_trend(cfg["llm"], preset, kws, "")
        topic = pick.keyword
        docs = await research.research_topic(pick.search_query, log=lambda m: progress("research", 60, m))
    else:  # topic
        progress("research", 5, "자료 검색 중")
        query = f"{text} {preset.get('research_queries_suffix', '')}".strip()
        docs = await research.research_topic(query, log=lambda m: progress("research", 60, m))
    for d in docs:
        if d.url:
            registry.add(kind="article", origin="url", url=d.url, title=d.title, used_for="script_research")
    progress("research", 100, f"자료 {len(docs)}건")
    return {"topic": topic, "docs": docs, "script_text": script_text, "source_info": source_info}


def _page_record(i: int, page, info: dict[str, Any], img: dict[str, Any] | None, art_sources: list[str]) -> dict:
    rec: dict[str, Any] = {"page": i, "file": Path(info["path"]).name, "type": page.type, "kind": page.kind,
                           "headline": page.headline, "fallback_used": info.get("fallback_used", False)}
    if info.get("fallback_reason"):
        rec["fallback_reason"] = info["fallback_reason"]
    if isinstance(page, CardPage):
        rec.update(label=page.label, body=page.body, items=page.items, emphasis=page.emphasis, layout=info.get("image_use"),
                   visual_query=page.visual_query, source=page.source)
        if page.compare:
            rec["compare"] = page.compare.model_dump()
    else:
        rec.update(caption=page.caption, layout=info.get("image_use"), source=page.source,
                   characters=sorted({b.character_id for b in page.panels if b.character_id}),
                   panels=[{**b.model_dump(), "art": art_sources[k] if k < len(art_sources) else "none"}
                           for k, b in enumerate(page.panels)])
    rec["image"] = ({"path": img["path"], "credit": img.get("credit", ""), "page_url": img.get("page_url", ""),
                     "reason": img.get("reason", "")} if img else None)
    return rec


def _caption_text(master: MasterContent, used_credits: list[str]) -> str:
    tags = " ".join(f"#{h.lstrip('#')}" for h in master.hashtags)
    lines = [master.title, "", master.summary or master.angle, "", master.cta, "", tags, ""]
    if master.sources or used_credits:
        lines.append("[출처]")
        lines += [f"- {s.get('title', '')} {s.get('url', '')}".rstrip() for s in master.sources]
        lines += [f"- {c}" for c in used_credits]
    return "\n".join(lines).strip() + "\n"


async def run_carousel(job_dir: Path, *, fmt: str, mode: str, text: str, cfg: dict[str, Any],
                       progress: Progress = _noop, template: str | None = None, character: str | None = None,
                       n_pages: int | None = None, instructions: str = "", image_search: bool = True,
                       inputs: dict[str, Any] | None = None, character_root: Path | None = None,
                       prepared_master: MasterContent | None = None,
                       prepared_plan: CarouselPlan | None = None) -> dict[str, Any]:
    """카드뉴스/인스타툰/하이브리드 한 벌을 만든다. inputs 를 주면 자료 수집을 건너뛴다(all 모드)."""
    if fmt not in CAROUSEL_FORMATS:
        raise ValueError(f"캐러셀 형식이 아닙니다: {fmt}")
    if (prepared_master is None) != (prepared_plan is None):
        raise ValueError('저장된 Master와 페이지 계획은 함께 전달해야 합니다')
    if prepared_plan is not None:
        if prepared_plan.format != fmt or not 6 <= len(prepared_plan.pages) <= 10:
            raise ValueError('저장된 페이지 계획의 형식·장수가 올바르지 않습니다')
        for page in prepared_plan.pages:
            if isinstance(page, ComicPage):
                for beat in page.panels:
                    charmod.get_character(beat.character_id, character_root)
    cs = carousel_settings(cfg)
    llm = cfg["llm"]
    out_dir = job_dir / fmt
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("card_*.png"):
        old.unlink()
    registry = SourceRegistry(job_dir)
    registry.save()
    tpl = load_template(template or (prepared_plan.template if prepared_plan else None) or (cs.get("templates") or {}).get(fmt), fmt)

    # 1. 입력
    if inputs is None:
        inputs = await gather_inputs(mode, text, cfg, job_dir, registry, progress)
    topic, docs = inputs["topic"], inputs["docs"]

    # 2. Master Content
    progress("script", 10, "핵심 내용(Master Content) 정리 중")
    if prepared_master is not None:
        master, master_method = prepared_master, 'topic_strategy_saved'
    else:
        master, master_method = await build_master(llm, topic, docs, script_text=inputs.get("script_text", ""),
                                                   instructions=instructions, source_info=inputs.get("source_info", ""))
    (job_dir / "master.json").write_text(master.model_dump_json(indent=2), encoding="utf-8")
    progress("script", 40, f"Master Content ({master_method}) · 성격 점수 {master.story_score:.2f}")

    # 3. Format Planner
    bible = None
    if fmt in ("insta_toon", "hybrid"):
        try:
            bible = charmod.get_character(character or cs["character"], character_root)
        except KeyError:
            bible = charmod.ensure_default(character_root)
    valid = {c.id for c in charmod.list_characters(character_root)}
    progress("script", 50, "페이지 구성 중")
    plan = prepared_plan if prepared_plan is not None else await plan_pages(llm, master, fmt, template=tpl.id, character=bible, valid_chars=valid,
                            n_pages=n_pages or int(cs["pages"]), instructions=instructions)
    (out_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    progress("script", 100, f"{len(plan.pages)}장 구성 ({plan.method}) · 카드 {plan.mix.get('card')}% / 만화 {plan.mix.get('comic')}%")

    # 4. 그림
    images: dict[int, dict[str, Any]] = {}
    report: dict[str, Any] = {}
    if image_search and cs.get("image_search", True):
        progress("images", 20, "카드에 쓸 공개 사진 찾는 중 (권리 확인되는 것만)")
        images, report = await find_card_images(plan, llm=llm, topic=master.topic, work_dir=out_dir, registry=registry,
                                                cfg=cfg, max_images=int(cs["max_images"]), progress=progress)
    registry = SourceRegistry(job_dir)    # resolver 가 등록한 항목 다시 읽기
    provider_cfg = {"images": {**cfg.get("images", {}), "provider": cs.get("image_provider") or "none"}}
    artist = CharacterArtist(job_dir=job_dir, registry=registry, provider_cfg=provider_cfg,
                             default_id=bible.id if bible else (character or cs["character"]), root=character_root,
                             log=lambda m: progress("images", 60, m))
    pinned = pinned_uploads(job_dir, registry)
    if fmt == "card_news" and tpl.character.get("on_cards"):
        charmod.ensure_default(character_root)      # 캐릭터 템플릿이면 카드뉴스에도 안내 캐릭터
    guide = artist.guide() if (fmt != "card_news" or tpl.character.get("on_cards")) else None

    # 5. 렌더 (페이지마다 독립 — 하나가 실패해도 계속)
    total = len(plan.pages)
    records: list[dict[str, Any]] = []
    used_credits: list[str] = []
    for i, page in enumerate(plan.pages, start=1):
        img = images.get(i - 1)
        if img and not guard_image(img.get("path"), registry):
            progress("render", 50, f"{i}번 페이지 사진의 사용 근거가 확인되지 않아 그래픽으로 바꿉니다")
            img = None
        panels, art_sources = [], []
        if isinstance(page, ComicPage):
            for k, beat in enumerate(page.panels):
                art = await artist.art(beat, i, pinned.get(i) if k == 0 else None)
                panels.append(art)
                art_sources.append(art.source or art.kind)
        assets = PageAssets(image=Path(img["path"]) if img else None, credit=img.get("credit", "") if img else "",
                            panels=panels, guide=guide, index=i, total=total)
        out = out_dir / f"card_{i:02d}.png"
        info = render_page(page, tpl, out, assets)
        registry.add(kind="image", origin="generated", path=str(out), title=f"{fmt} {i}장", used_for=f"page_{i:02d}")
        if img:
            registry.mark_used(img["path"], i)
            used_credits.append(f"{i}장 {img.get('credit', '')} — {img.get('page_url', '')}")
        if pinned.get(i) and art_sources and art_sources[0] == "upload":
            registry.mark_used(pinned[i], i)
        records.append(_page_record(i, page, info, img, art_sources))
        progress("render", int(100 * i / total), f"{i}/{total} {page.type}" + (" (대체 레이아웃)" if info.get("fallback_used") else ""))

    # 6. 결과 기록
    manifest = {"format": fmt, "template": tpl.id, "size": f"{tpl.width}x{tpl.height}", "pages": records,
                "page_count": total, "mix": plan.mix, "plan_method": plan.method, "master_method": master_method,
                "topic": master.topic, "title": master.title, "story_score": master.story_score,
                "characters": [bible.model_dump(include={"id", "name", "role"})] if bible else [],
                "fallback_pages": [r["page"] for r in records if r["fallback_used"]],
                "image_search": {k: report.get(k) for k in ("providers", "query_method", "fit_method", "errors") if k in report},
                "sources": master.sources, "image_credits": used_credits}
    (out_dir / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(job_dir / "master.json", out_dir / "master.json")
    # 이 형식에 쓴 자료만 모은 출처 파일 (전체 대장은 job_dir/sources.json)
    used_paths = {str(Path(r["image"]["path"]).resolve()) for r in records if r.get("image")}
    rows = [x.model_dump() for x in registry.items.values()
            if (x.usage in ("research", "reference_only") and x.url)
            or (x.path and str(Path(x.path).resolve()) in used_paths)]
    (out_dir / "sources.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "caption.txt").write_text(_caption_text(master, used_credits), encoding="utf-8")
    progress("render", 100, f"{fmt} {total}장 완료 → {out_dir}")
    return {"format": fmt, "dir": str(out_dir), "pages": [str(out_dir / r["file"]) for r in records],
            "manifest": str(out_dir / MANIFEST), "topic": master.topic, "title": master.title, "mix": plan.mix,
            "plan_method": plan.method, "master_method": master_method,
            "fallback_pages": manifest["fallback_pages"], "image_pages": [r["page"] for r in records if r.get("image")],
            "image_search_error": report.get("error", "")}


def inputs_from_shorts(job_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    """all 모드: 쇼츠가 이미 조사·작성한 대본을 Master Content 의 재료로 다시 쓴다 (조사를 두 번 하지 않는다)."""
    script = json.loads((job_dir / "script.json").read_text(encoding="utf-8"))
    narration = "\n".join(s.get("narration", "") for s in script.get("scenes", []))
    docs = [ResearchDoc(title=d.get("title", ""), url=d.get("url", ""), text="") for d in result.get("docs", [])]
    docs.insert(0, ResearchDoc(title=script.get("topic", ""), url="", text=narration))
    return {"topic": result.get("topic") or script.get("topic", ""), "docs": docs, "script_text": "",
            "source_info": "같은 프로젝트의 쇼츠 대본 (조사 자료에서 확인된 내용)"}

