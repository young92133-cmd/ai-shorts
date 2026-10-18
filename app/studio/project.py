"""카드뉴스·인스타툰 스튜디오 엔진 — 웹 화면(app/studio/api.py)과 CLI 가 같이 쓴다.

새 제작은 Factory(core.make)를 그대로 부르고, 이 모듈은 만들어진 프로젝트를 열고·고치고·다시 그리고·내보낸다.
프로젝트 = output/<id>/ (project_state.json) 이고, 카드 상태는 output/<id>/<형식>/plan.json·manifest.json 이 원본이다.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from ..carousel import characters as charmod
from ..carousel.pipeline import MANIFEST, carousel_settings, pose_gaps, render_kit, render_one
from ..carousel.schema import CAROUSEL_FORMATS, EMOTIONS, CardPage, CarouselPlan, ComicPage
from ..carousel.scenes import SCENES
from ..carousel.templates import load_template
from ..factory import core
from ..factory import state as st
from ..factory.core import FactoryError

CARD_FIELDS = ("label", "headline", "body", "items", "emphasis", "character_emotion", "character_pose")
COMIC_FIELDS = ("headline", "caption")
PANEL_FIELDS = ("dialogue", "partner_dialogue", "emotion", "partner_emotion", "pose", "background", "camera",
                "speech_bubble_position", "sfx", "scene")
LIMITS = {"headline": 60, "label": 20, "body": 200, "caption": 200, "dialogue": 80, "partner_dialogue": 80, "sfx": 12}


# ---------- 만들기 ----------

async def create(topic: str, *, fmt: str = "card_news", pages: int = 8, template: str | None = None,
                 character: str | None = None, image_search: bool = True, instructions: str = "",
                 log=lambda m: None) -> dict[str, Any]:
    """주제로 새 캐러셀 프로젝트를 만든다 (조사 → 문구 → 장면 → PNG). Factory make 와 같은 경로."""
    if fmt not in CAROUSEL_FORMATS:
        raise FactoryError("invalid", f"형식은 {' / '.join(CAROUSEL_FORMATS)} 중 하나입니다.")
    if not topic.strip():
        raise FactoryError("invalid", "주제를 입력해 주세요.")
    return await core.make(topic=topic.strip(), output_format=fmt, pages=pages, template=template or None,
                           character=character or None, visuals="auto" if image_search else "cards",
                           instructions=instructions, log=log)


# ---------- 열기 ----------

def _fmt_of(state: dict[str, Any]) -> str:
    return (state.get("request") or {}).get("output_format") or ""


def list_projects(limit: int = 30) -> list[dict[str, Any]]:
    """캐러셀 프로젝트만, 최근 것부터."""
    out = []
    for d in core._projects():
        state = st.load(d)
        fmt = _fmt_of(state)
        if fmt not in CAROUSEL_FORMATS:
            continue
        first = d / fmt / "card_01.png"
        out.append({"project_id": d.name, "format": fmt, "status": state.get("status", ""),
                    "topic": state.get("topic") or (state.get("request") or {}).get("input", ""),
                    "created": state.get("created", ""), "thumb": f"{fmt}/card_01.png" if first.is_file() else ""})
        if len(out) >= limit:
            break
    return out


def _paths(project_id: str) -> tuple[Path, dict[str, Any], str, Path]:
    job = core.project_dir(project_id)
    state = st.load(job)
    fmt = _fmt_of(state)
    if fmt not in CAROUSEL_FORMATS:
        raise FactoryError("invalid", "카드뉴스·인스타툰 프로젝트가 아닙니다.")
    out_dir = job / fmt
    if not (out_dir / "plan.json").is_file():
        raise FactoryError("not_ready", "아직 페이지 계획이 없습니다. 제작이 끝난 뒤 열어 주세요.",
                           status=state.get("status"), error=state.get("error", ""))
    return job, state, fmt, out_dir


def _read(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def load(project_id: str) -> dict[str, Any]:
    """화면에 필요한 것 한 번에: 페이지별 문구(plan) + 렌더 결과(manifest) + 캡션."""
    job, state, fmt, out_dir = _paths(project_id)
    plan = CarouselPlan.model_validate(_read(out_dir / "plan.json"))
    manifest = _read(out_dir / MANIFEST, {}) or {}
    records = {r["page"]: r for r in manifest.get("pages", [])}
    pages = []
    for i, page in enumerate(plan.pages, start=1):
        rec = records.get(i, {})
        png = out_dir / f"card_{i:02d}.png"
        pages.append({"page": i, "kind": page.kind, "type": page.type, "data": page.model_dump(),
                      "file": f"{fmt}/{png.name}" if png.is_file() else "",
                      "version": int(png.stat().st_mtime) if png.is_file() else 0,
                      "fallback_used": rec.get("fallback_used", False), "image": rec.get("image"),
                      "art": [p.get("art") for p in rec.get("panels", [])]})
    caption = (out_dir / "caption.txt").read_text(encoding="utf-8") if (out_dir / "caption.txt").is_file() else ""
    return {"project_id": job.name, "format": fmt, "status": state.get("status"), "title": manifest.get("title", ""),
            "topic": manifest.get("topic") or state.get("topic", ""), "template": plan.template,
            "characters": manifest.get("characters", []), "pages": pages, "caption": caption,
            "pose_gaps": manifest.get("pose_gaps", []),
            "options": options(manifest)}


def options(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """수정 칸의 선택지: 감정·자세(등록 포즈 기준)·배경 종류."""
    char_id = ((manifest or {}).get("characters") or [{}])[0].get("id")
    poses: list[str] = []
    if char_id:
        try:
            bible = charmod.get_character(char_id)
            poses = sorted({p.pose for p in bible.poses if p.approved})
        except KeyError:
            pass
    return {"emotions": list(EMOTIONS), "poses": poses or ["standing", "pointing", "thinking", "waving"],
            "backgrounds": [words[0] for words in SCENES.values()],
            "cameras": ["close_up", "medium", "wide"]}


# ---------- 고치기 · 다시 그리기 ----------

def _clean(field: str, value: Any) -> Any:
    if field == "items":
        if not isinstance(value, list):
            raise FactoryError("invalid", "items 는 문장 목록이어야 합니다.")
        return [str(v).strip()[:60] for v in value if str(v).strip()][:6]
    text = str(value or "").strip()
    return text[:LIMITS.get(field, 40)]


def _apply(page, fields: dict[str, Any]):
    if isinstance(page, CardPage):
        upd = {k: _clean(k, v) for k, v in fields.items() if k in CARD_FIELDS}
        return page.model_copy(update=upd)
    upd = {k: _clean(k, v) for k, v in fields.items() if k in COMIC_FIELDS}
    panels = list(page.panels)
    for k, pf in enumerate(fields.get("panels") or []):
        if k < len(panels) and isinstance(pf, dict):
            panels[k] = panels[k].model_copy(update={f: _clean(f, v) for f, v in pf.items() if f in PANEL_FIELDS})
    return page.model_copy(update={**upd, "panels": panels})


async def rerender(project_id: str, page_no: int) -> dict[str, Any]:
    """plan.json 의 page_no 장만 다시 그리고 manifest 기록을 바꾼다 (사진은 처음 고른 것 그대로)."""
    job, state, fmt, out_dir = _paths(project_id)
    plan = CarouselPlan.model_validate(_read(out_dir / "plan.json"))
    if not 1 <= page_no <= len(plan.pages):
        raise FactoryError("invalid", f"페이지 번호는 1~{len(plan.pages)} 입니다.")
    manifest = _read(out_dir / MANIFEST, {}) or {}
    records = manifest.get("pages", [])
    old = next((r for r in records if r.get("page") == page_no), {})
    cfg = core._run_cfg(state.get("request") or {})
    chars = manifest.get("characters") or []
    default_id = chars[0]["id"] if chars else (state.get("request") or {}).get("character") or carousel_settings(cfg)["character"]
    tpl = load_template(plan.template, fmt)
    kit = render_kit(job, fmt=fmt, tpl=tpl, cfg=cfg, default_id=default_id, total=len(plan.pages))
    rec = await render_one(kit, page_no, plan.pages[page_no - 1], old.get("image"))
    manifest["pages"] = [rec if r.get("page") == page_no else r for r in records] if old else records + [rec]
    manifest["fallback_pages"] = [r["page"] for r in manifest["pages"] if r.get("fallback_used")]
    manifest["pose_gaps"] = pose_gaps(manifest["pages"])
    (out_dir / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def _save_page(out_dir: Path, plan: CarouselPlan, page_no: int, page) -> None:
    pages = list(plan.pages)
    pages[page_no - 1] = page
    (out_dir / "plan.json").write_text(plan.model_copy(update={"pages": pages}).model_dump_json(indent=2),
                                       encoding="utf-8")


def _page(project_id: str, page_no: int):
    job, state, fmt, out_dir = _paths(project_id)
    plan = CarouselPlan.model_validate(_read(out_dir / "plan.json"))
    if not 1 <= page_no <= len(plan.pages):
        raise FactoryError("invalid", f"페이지 번호는 1~{len(plan.pages)} 입니다.")
    return out_dir, plan, plan.pages[page_no - 1]


async def update_page(project_id: str, page_no: int, fields: dict[str, Any]) -> dict[str, Any]:
    """카드 문구·컷 대사 등을 고치고 그 장만 다시 그린다."""
    out_dir, plan, page = _page(project_id, page_no)
    _save_page(out_dir, plan, page_no, _apply(page, fields))
    return await rerender(project_id, page_no)


def _next(options: list[str], current: str) -> str:
    if not options:
        return current
    return options[(options.index(current) + 1) % len(options)] if current in options else options[0]


async def vary_scene(project_id: str, page_no: int) -> dict[str, Any]:
    """장면 바꾸기(무료): 만화 컷은 감정·자세·배경을, 카드는 안내 캐릭터 표정을 다음 후보로 돌려 다시 그린다."""
    out_dir, plan, page = _page(project_id, page_no)
    opts = options(_read(out_dir / MANIFEST, {}))
    emotions = ["happy", "surprised", "worried", "thinking", "confident", "neutral"]
    if isinstance(page, ComicPage):
        panels = [b.model_copy(update={"emotion": _next(emotions, b.emotion), "pose": _next(opts["poses"], b.pose),
                                       "background": _next(opts["backgrounds"], b.background)})
                  for b in page.panels]
        page = page.model_copy(update={"panels": panels})
    else:
        page = page.model_copy(update={"character_emotion": _next(emotions, page.character_emotion or "happy"),
                                       "character_pose": _next(opts["poses"], page.character_pose)})
    _save_page(out_dir, plan, page_no, page)
    return await rerender(project_id, page_no)


# ---------- 내보내기 ----------

def export_zip(project_id: str) -> Path:
    """PNG 전부 + 캡션 + 출처를 ZIP 하나로 (output/<id>/<형식>/<id>_<형식>.zip)."""
    job, state, fmt, out_dir = _paths(project_id)
    cards = sorted(out_dir.glob("card_*.png"))
    if not cards:
        raise FactoryError("not_ready", "저장할 PNG 가 없습니다.")
    dest = out_dir / f"{job.name}_{fmt}.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in cards + [out_dir / n for n in ("caption.txt", "sources.json") if (out_dir / n).is_file()]:
            z.write(p, p.name)
    return dest
