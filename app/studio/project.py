"""카드뉴스·인스타툰 스튜디오 엔진 — 웹 화면(app/studio/api.py)과 CLI 가 같이 쓴다.

새 제작은 Factory(core.make)를 그대로 부르고, 이 모듈은 만들어진 프로젝트를 열고·고치고·다시 그리고·내보낸다.
프로젝트 = output/<id>/ (project_state.json) 이고, 카드 상태는 output/<id>/<형식>/plan.json·manifest.json 이 원본이다.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from ..carousel import characters as charmod
from ..carousel.pipeline import MANIFEST, carousel_settings, render_kit, render_one, write_results
from ..carousel.schema import CAROUSEL_FORMATS, EMOTIONS, CardPage, CarouselPlan, ComicBeat, ComicPage, MasterContent
from ..carousel.scenes import SCENES
from ..carousel.templates import load_template
from ..factory import core
from ..factory import state as st
from ..factory.core import FactoryError
from ..pipeline.sources import SourceRegistry

CARD_FIELDS = ("label", "headline", "body", "items", "emphasis", "character_emotion", "character_pose")
COMIC_FIELDS = ("headline", "caption")
PANEL_FIELDS = ("dialogue", "partner_dialogue", "emotion", "partner_emotion", "pose", "background", "camera",
                "speech_bubble_position", "sfx", "scene")
MIN_PAGES, MAX_PAGES = 3, 10      # 스튜디오에서 추가·삭제할 때의 장수 범위
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
                      "version": png.stat().st_mtime_ns // 1_000_000 if png.is_file() else 0,
                      "fallback_used": rec.get("fallback_used", False), "image": rec.get("image"),
                      "art": [p.get("art") for p in rec.get("panels", [])]})
    caption = (out_dir / "caption.txt").read_text(encoding="utf-8") if (out_dir / "caption.txt").is_file() else ""
    return {"project_id": job.name, "format": fmt, "status": state.get("status"), "title": manifest.get("title", ""),
            "topic": manifest.get("topic") or state.get("topic", ""), "template": plan.template,
            "characters": manifest.get("characters", []), "pages": pages, "caption": caption,
            "pose_gaps": manifest.get("pose_gaps", []), "undo_count": len(_snapshots(out_dir)),
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


def _kit(job: Path, state: dict[str, Any], fmt: str, plan: CarouselPlan, manifest: dict[str, Any]):
    cfg = core._run_cfg(state.get("request") or {})
    chars = manifest.get("characters") or []
    default_id = chars[0]["id"] if chars else (state.get("request") or {}).get("character") or carousel_settings(cfg)["character"]
    kit = render_kit(job, fmt=fmt, tpl=load_template(plan.template, fmt), cfg=cfg, default_id=default_id,
                     total=len(plan.pages))
    if manifest.get("pins_in_records"):   # 순서 편집 뒤에는 파일 이름 번호 대신 페이지 기록의 이미지를 쓴다
        kit.pinned = {}
    return kit


def _master(out_dir: Path, job: Path) -> MasterContent:
    raw = _read(out_dir / "master.json") or _read(job / "master.json")
    return MasterContent.model_validate(raw)


async def rerender(project_id: str, page_no: int) -> dict[str, Any]:
    """plan.json 의 page_no 장만 다시 그리고 manifest·캡션·출처를 맞춘다 (사진은 처음 고른 것 그대로)."""
    job, state, fmt, out_dir = _paths(project_id)
    plan = CarouselPlan.model_validate(_read(out_dir / "plan.json"))
    if not 1 <= page_no <= len(plan.pages):
        raise FactoryError("invalid", f"페이지 번호는 1~{len(plan.pages)} 입니다.")
    manifest = _read(out_dir / MANIFEST, {}) or {}
    records = manifest.get("pages", [])
    old = next((r for r in records if r.get("page") == page_no), {})
    kit = _kit(job, state, fmt, plan, manifest)
    rec = await render_one(kit, page_no, plan.pages[page_no - 1], old.get("image"))
    records = [rec if r.get("page") == page_no else r for r in records] if old else records + [rec]
    write_results(kit, _master(out_dir, job), records, manifest)
    return rec


# ---------- 순서 바꾸기 · 추가 · 삭제 ----------

def _backup(out_dir: Path) -> None:
    """바꾸기 전 plan·manifest 를 history/ 에 남긴다 = 실행 취소 목록 (지우지 않음)."""
    hist = out_dir / "history"
    hist.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    for name in ("plan.json", MANIFEST):
        if (out_dir / name).is_file():
            (hist / f"{stamp}_{name}").write_bytes((out_dir / name).read_bytes())


def _snapshots(out_dir: Path) -> list[str]:
    """실행 취소할 수 있는 저장 시점 (오래된 것부터). plan 과 manifest 가 둘 다 있는 것만."""
    hist = out_dir / "history"
    stamps = sorted(f.name[:-len("_plan.json")] for f in hist.glob("*_plan.json")) if hist.is_dir() else []
    return [t for t in stamps if (hist / f"{t}_{MANIFEST}").is_file()]


async def _render_pages(job: Path, state: dict[str, Any], fmt: str, out_dir: Path, plan: CarouselPlan,
                        manifest: dict[str, Any], items: list[dict[str, Any]]) -> None:
    """items(새 순서의 페이지·사진)로 plan 을 쓰고 전체를 새 번호로 다시 그린다. 순서 편집과 실행 취소가 같이 쓴다."""
    pages = [it["page"] for it in items]
    comics = sum(isinstance(pg, ComicPage) for pg in pages)
    mix = {"card": round(100 * (len(pages) - comics) / len(pages)), "comic": round(100 * comics / len(pages))}
    plan = plan.model_copy(update={"pages": pages, "mix": mix})
    (out_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    kit = _kit(job, state, fmt, plan, manifest)
    # 파일 이름 번호로 고정된 업로드 그림(uploads/toon_NN_*)은 그 페이지의 이미지 기록으로 옮겨 페이지와 함께 움직이게 한다
    for it in items:
        if it.get("old") in kit.pinned and not it.get("image"):
            it["image"] = {"path": str(kit.pinned[it["old"]]), "credit": "", "page_url": "", "upload": True}
    kit.pinned = {}
    for it in items:                # 사진의 장면 번호는 새 순서로 다시 기록
        item = kit.registry.by_path(it["image"]["path"]) if it.get("image") else None
        if item:
            item.scene_ids.clear()
    records = [await render_one(kit, n, it["page"], it["image"]) for n, it in enumerate(items, start=1)]
    for png in out_dir.glob("card_*.png"):            # 줄어든 장수만큼 남은 옛 번호 파일 정리 (이 프로젝트가 만든 렌더 파일)
        if png.name not in {r["file"] for r in records}:
            png.unlink()
    write_results(kit, _master(out_dir, job), records, {**manifest, "mix": mix, "pins_in_records": True})


def _items(plan: CarouselPlan, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    recs = {r.get("page"): r for r in manifest.get("pages", [])}
    return [{"page": pg, "old": i, "image": (recs.get(i) or {}).get("image")} for i, pg in enumerate(plan.pages, start=1)]


async def _restructure(project_id: str, change) -> dict[str, Any]:
    """페이지 목록을 바꾼 뒤 전체를 새 번호로 다시 그린다. 문구(plan)·그림(사진)·기록(manifest)·파일명이 함께 움직인다."""
    job, state, fmt, out_dir = _paths(project_id)
    plan = CarouselPlan.model_validate(_read(out_dir / "plan.json"))
    manifest = _read(out_dir / MANIFEST, {}) or {}
    items = change(_items(plan, manifest))
    if not MIN_PAGES <= len(items) <= MAX_PAGES:
        raise FactoryError("invalid", f"장수는 {MIN_PAGES}~{MAX_PAGES}장 사이여야 합니다.")
    _backup(out_dir)
    await _render_pages(job, state, fmt, out_dir, plan, manifest, items)
    return load(project_id)


async def undo(project_id: str) -> dict[str, Any]:
    """마지막 편집(문구·장면·순서·추가·삭제·이미지) 직전 상태로 되돌린다. 쓴 저장 시점은 history/undone/ 으로 옮긴다."""
    job, state, fmt, out_dir = _paths(project_id)
    stamps = _snapshots(out_dir)
    if not stamps:
        raise FactoryError("not_ready", "되돌릴 편집 기록이 없습니다.")
    hist, stamp = out_dir / "history", stamps[-1]
    plan = CarouselPlan.model_validate(_read(hist / f"{stamp}_plan.json"))
    manifest = _read(hist / f"{stamp}_{MANIFEST}", {}) or {}
    await _render_pages(job, state, fmt, out_dir, plan, manifest, _items(plan, manifest))
    (hist / "undone").mkdir(exist_ok=True)
    for name in (f"{stamp}_plan.json", f"{stamp}_{MANIFEST}"):
        shutil.move(str(hist / name), str(hist / "undone" / name))
    return load(project_id)


# ---------- 카드 이미지 직접 올리기 · 빼기 ----------

IMAGE_TYPES = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}   # 확장자 → 실제 파일 형식
MAX_UPLOAD = 20 * 1024 * 1024        # 20MB
MAX_PIXELS = 40_000_000              # 가로×세로 4천만 화소 (메모리를 과하게 쓰는 그림 방지)


async def _set_record_image(project_id: str, page_no: int, image: dict[str, Any] | None) -> dict[str, Any]:
    job, state, fmt, out_dir = _paths(project_id)
    plan = CarouselPlan.model_validate(_read(out_dir / "plan.json"))
    if not 1 <= page_no <= len(plan.pages):
        raise FactoryError("invalid", f"페이지 번호는 1~{len(plan.pages)} 입니다.")
    manifest = _read(out_dir / MANIFEST, {}) or {}
    _backup(out_dir)
    for r in manifest.get("pages", []):
        if r.get("page") == page_no:
            r["image"] = image
    (out_dir / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    rec = await rerender(project_id, page_no)
    shown = rec.get("layout") == "image" or any(pn.get("art") == "upload" for pn in rec.get("panels") or [])
    return {**rec, "image_shown": bool(image) and shown}


async def set_image(project_id: str, page_no: int, src: Path, name: str, *, confirm_rights: bool) -> dict[str, Any]:
    """PC 의 이미지를 n장에 넣는다(교체). 권리 확인한 사용자 이미지로 출처 대장에 남기고, 순서를 바꿔도 그 카드를 따라간다."""
    if not confirm_rights:
        raise FactoryError("invalid", "직접 찍었거나 만든 이미지, 또는 사용 허락을 받은 이미지만 넣을 수 있습니다. 권리를 확인해 주세요.")
    ext = Path(name).suffix.lower()
    if ext not in IMAGE_TYPES:
        raise FactoryError("invalid", "PNG·JPG·WEBP 이미지만 넣을 수 있습니다.")
    if src.stat().st_size > MAX_UPLOAD:
        raise FactoryError("invalid", "이미지는 20MB 이하만 넣을 수 있습니다.")
    try:
        from PIL import Image
        with Image.open(src) as im:
            fmt_, size = im.format, im.size
            im.verify()
    except Exception as e:  # noqa: BLE001 - 깨진 파일·지나치게 큰 그림(DecompressionBomb) 포함
        raise FactoryError("invalid", "이미지 파일을 열 수 없습니다.") from e
    if fmt_ != IMAGE_TYPES[ext]:
        raise FactoryError("invalid", f"파일 내용이 확장자({ext})와 다릅니다. 원본 이미지를 다시 저장해서 올려 주세요.")
    if size[0] * size[1] > MAX_PIXELS:
        raise FactoryError("invalid", "이미지 해상도가 너무 큽니다 (최대 약 4천만 화소). 크기를 줄여서 올려 주세요.")
    job, _, _, _ = _paths(project_id)
    dest = job / "uploads" / "studio" / f"{dt.datetime.now():%Y%m%d_%H%M%S_%f}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    SourceRegistry(job).add(kind="image", origin="upload", path=str(dest), title=Path(name).name, used_for="studio_upload",
                            rights=core._own_rights("my_channel", "스튜디오에서 사용자가 직접 올림 (사용 권리 확인)", True))
    return await _set_record_image(project_id, page_no, {"path": str(dest), "credit": "직접 올린 이미지", "page_url": "",
                                                         "upload": True, "name": Path(name).name})


async def clear_image(project_id: str, page_no: int) -> dict[str, Any]:
    """n장의 사진·올린 이미지를 빼고 앱 그래픽으로 다시 그린다 (파일은 지우지 않음)."""
    return await _set_record_image(project_id, page_no, None)


async def move_page(project_id: str, page_no: int, to: int) -> dict[str, Any]:
    def change(items):
        if not (1 <= page_no <= len(items) and 1 <= to <= len(items)):
            raise FactoryError("invalid", f"페이지 번호는 1~{len(items)} 입니다.")
        items = list(items)
        items.insert(to - 1, items.pop(page_no - 1))
        return items
    return await _restructure(project_id, change)


async def delete_page(project_id: str, page_no: int) -> dict[str, Any]:
    def change(items):
        if not 1 <= page_no <= len(items):
            raise FactoryError("invalid", f"페이지 번호는 1~{len(items)} 입니다.")
        return items[:page_no - 1] + items[page_no:]
    return await _restructure(project_id, change)


def _blank(kind: str, fmt: str, character: str):
    if kind == "comic":
        if fmt == "card_news":
            raise FactoryError("invalid", "카드뉴스에는 만화 컷을 넣지 않습니다. 인스타툰·섞기 형식에서 추가해 주세요.")
        return ComicPage(type="comic_scene", headline="", panels=[ComicBeat(
            character_id=character, emotion="happy", pose="standing", background="방", dialogue="대사를 입력하세요")])
    return CardPage(type="info_card", label="", headline="새 카드 제목", body="내용을 입력한 뒤 '저장하고 다시 그리기'를 눌러 주세요.")


async def add_page(project_id: str, after: int, kind: str = "card") -> dict[str, Any]:
    """after 장 뒤에 빈 카드(또는 만화 컷)를 넣는다. 0 이면 맨 앞."""
    job, state, fmt, out_dir = _paths(project_id)
    manifest = _read(out_dir / MANIFEST, {}) or {}
    chars = manifest.get("characters") or []
    character = chars[0]["id"] if chars else "hamtorich_01"
    page = _blank(kind, fmt, character)

    def change(items):
        if not 0 <= after <= len(items):
            raise FactoryError("invalid", f"위치는 0~{len(items)} 입니다.")
        return items[:after] + [{"page": page, "old": None, "image": None}] + items[after:]
    return await _restructure(project_id, change)


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
    _backup(out_dir)
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
    _backup(out_dir)
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
