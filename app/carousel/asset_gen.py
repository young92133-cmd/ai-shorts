"""브랜드 그림 세트 생성 (캐릭터 추가 표정·조연·장면 배경). 유료 이미지 API 를 쓰므로 비용 확인 후에만 실행한다.

asset_plans/<plan>.yaml → Gemini(마스터 시트 참조) → 캐릭터는 흰 배경 제거 후 투명 PNG → 등록.
생성 그림은 approved=False 로 등록돼 렌더에 쓰이지 않는다. 마스터 시트와 대조한 뒤 approve 해야 쓴다.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

import yaml
from PIL import Image, ImageDraw, ImageFilter

from . import characters as charmod
from .backgrounds import BG_ROOT, load_index, save_index

PLAN_DIR = Path(__file__).parent / "asset_plans"
PRICE_WON = {"lite": 49, "flash": 97, "pro": 194}     # 1K 장당 (config.yaml images 주석과 같은 기준)
POSE_SIZE = 1254
SENTINEL = (255, 0, 255)


def load_plan(name: str) -> dict[str, Any]:
    path = PLAN_DIR / f"{name}.yaml"
    if not path.is_file():
        raise ValueError(f"그림 계획이 없습니다: {name} (가능: {', '.join(p.stem for p in PLAN_DIR.glob('*.yaml'))})")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def jobs(plan: dict[str, Any], *, brand: str = charmod.BRAND_DEFAULT, only: str = "all",
         root: Path | None = None, bg_root: Path | None = None) -> list[dict[str, Any]]:
    """만들 그림 목록. 이미 있는 파일은 건너뛴다 (다시 만들 땐 파일을 지우고 실행)."""
    out: list[dict[str, Any]] = []
    bible = charmod.get_character(brand, root)
    master = charmod.master_reference(bible, root)
    front = charmod.pose_for(bible, "happy", "standing", root)
    refs = [p for p in (master, front) if p]
    style, csuf, bsuf = plan["style"], plan["character_suffix"], plan["background_suffix"]
    if only in ("all", "backgrounds"):
        for b in plan.get("backgrounds", []):
            target = (bg_root or BG_ROOT) / f"{b['id']}.png"
            out.append({"kind": "background", "id": b["id"], "target": target, "aspect": "4:5", "meta": b,
                        "refs": [x for x in (master,) if x],
                        "prompt": f"{b['prompt']}. Same soft hand-drawn illustration style as the reference sheet. {style}. {bsuf}"})
    if only in ("all", "poses"):
        for p in plan.get("poses", []):
            target = charmod.character_dir(brand, root) / "poses" / f"{p['id']}.png"
            out.append({"kind": "pose", "id": p["id"], "target": target, "refs": refs, "aspect": "1:1", "meta": p,
                        "character": brand,
                        "prompt": (f"Draw the SAME character as in the reference images (master design sheet is the top authority). "
                                   f"{charmod.lock_text(bible)} New expression and pose: {p['prompt']}. {style}. {csuf}")})
    if only in ("all", "cast"):
        for c in plan.get("cast", []):
            for p in c["poses"]:
                target = charmod.character_dir(c["id"], root) / "poses" / f"{p['id']}.png"
                first = charmod.character_dir(c["id"], root) / "poses" / f"{c['poses'][0]['id']}.png"
                out.append({"kind": "cast", "id": f"{c['id']}/{p['id']}", "target": target, "aspect": "1:1",
                            "refs": [x for x in (master,) if x] + ([first] if p is not c["poses"][0] else []),
                            "meta": {**p, "cast": c}, "character": c["id"],
                            "prompt": (f"A new supporting character in exactly the same art style as the reference sheet "
                                       f"(do not draw the hamster): {c['look']}. Chibi proportions like the reference. "
                                       f"Expression and pose: {p['prompt']}. Keep this character identical across images. "
                                       f"{style}. {csuf}")})
    if only in ("all", "personas"):
        for c in plan.get("personas", []):
            for p in c["poses"]:
                target = charmod.character_dir(c["id"], root) / "poses" / f"{p['id']}.png"
                first = charmod.character_dir(c["id"], root) / "poses" / f"{c['poses'][0]['id']}.png"
                out.append({"kind": "persona", "id": f"{c['id']}/{p['id']}", "target": target, "aspect": "1:1",
                            "refs": [x for x in (master,) if x] + ([first] if p is not c["poses"][0] else []),
                            "meta": {**p, "cast": c}, "character": c["id"],
                            "prompt": (f"A new supporting character in exactly the same art style as the reference sheet "
                                       f"(do not draw the hamster): {c['look']}. Chibi proportions like the reference. "
                                       f"Expression and pose: {p['prompt']}. Keep this character identical across images. "
                                       f"{style}. {csuf}")})
    return [j for j in out if not Path(j["target"]).exists()]


def estimate(todo: list[dict[str, Any]], tier: str = "lite") -> dict[str, Any]:
    count = len(todo)
    return {"images": count, "tier": tier, "won_per_image": PRICE_WON[tier], "won_estimate": count * PRICE_WON[tier],
            "by_kind": {k: sum(1 for j in todo if j["kind"] == k) for k in ("background", "pose", "cast", "persona")}}


def remove_white_background(img: Image.Image, tolerance: int = 28, size: int = POSE_SIZE) -> Image.Image:
    """테두리에서 이어진 흰 배경만 지운다 (캐릭터 안쪽 흰 셔츠·크림색 털은 외곽선 안이라 남는다)."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    seeds = [(x, 0) for x in range(0, w, 16)] + [(x, h - 1) for x in range(0, w, 16)] + \
            [(0, y) for y in range(0, h, 16)] + [(w - 1, y) for y in range(0, h, 16)]
    for seed in seeds:
        if min(rgb.getpixel(seed)) >= 255 - tolerance:
            ImageDraw.floodfill(rgb, seed, SENTINEL, thresh=tolerance)
    mask = Image.new("L", rgb.size, 255)
    px, mp = rgb.load(), mask.load()
    for y in range(h):
        for x in range(w):
            if px[x, y] == SENTINEL:
                mp[x, y] = 0
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1))
    out = img.convert("RGBA")
    out.putalpha(mask)
    box = mask.getbbox()
    if not box:
        raise ValueError("배경을 지운 뒤 남은 그림이 없습니다")
    out = out.crop(box)
    # 기존 포즈처럼 정사각형 캔버스 가운데, 위아래 여백 약 6%
    scale = min(size * 0.88 / out.width, size * 0.88 / out.height)
    out = out.resize((max(1, int(out.width * scale)), max(1, int(out.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(out, ((size - out.width) // 2, size - out.height - int(size * 0.06)), out)
    return canvas


def _register(job: dict[str, Any], root: Path | None, bg_root: Path | None, tier: str) -> None:
    meta = job["meta"]
    note = f"AI 생성 (gemini-{tier}, 마스터 시트 참조) — 시트 대조 검토 전"
    if job["kind"] in ("pose", "cast", "persona"):
        cid = job["character"]
        try:
            bible = charmod.get_character(cid, root)
        except KeyError:
            c = meta["cast"]
            bible = charmod.CharacterBible(
                id=cid, name=c["name"], role=c["role"], visual_style="same style as hamtorich_01 master sheet",
                appearance={"tag": c["tag"]} if c.get("tag") else {},
                prompt_lock=c["look"], master_reference="", mascot_fallback=False, rights="owned",
                design_rules=["햄토리치 마스터 시트와 같은 그림체·외곽선·털 질감", "투명 배경, 글자 없음"])
        rel = f"poses/{Path(job['target']).name}"
        if not any(p.file == rel for p in bible.poses):
            bible.poses.append(charmod.PoseAsset(
                file=rel, emotion=meta["emotion"], pose=meta["pose"], also_emotions=meta.get("also_emotions", []),
                also_poses=meta.get("also_poses", []), description=meta["prompt"], differences=[note], approved=False))
        if not bible.default_pose:
            bible.default_pose = rel
        charmod.save_character(bible, root)
    else:
        index = load_index(bg_root)
        if not any(e["id"] == job["id"] for e in index):
            index.append({"id": job["id"], "file": Path(job["target"]).name, "tags": meta["tags"], "mood": meta["mood"],
                          "approved": False, "source": note})
        save_index(index, bg_root)


def select(todo: list[dict[str, Any]], items: list[str] | None, limit: int | None) -> list[dict[str, Any]]:
    """--item 으로 고른 그림만 (예: 시험 1장), 아니면 우선순위 순서대로 limit 장."""
    if items:
        todo = [j for j in todo if j["id"] in set(items)]
    return todo[: limit or None]


async def generate(plan_name: str, *, tier: str = "lite", only: str = "all", limit: int | None = None,
                   items: list[str] | None = None, provider: Any = None, root: Path | None = None,
                   bg_root: Path | None = None, log: Callable[[str], None] = print) -> dict[str, Any]:
    """그림을 만들고 등록한다. provider 를 주지 않으면 Gemini(tier) 를 쓴다 (유료)."""
    plan = load_plan(plan_name)
    todo = select(jobs(plan, only=only, root=root, bg_root=bg_root), items, limit)
    if provider is None:
        from ..pipeline.images.gemini import GeminiImages, GeminiImagesLite, GeminiImagesPro
        provider = {"lite": GeminiImagesLite, "flash": GeminiImages, "pro": GeminiImagesPro}[tier](image_size="1K")
    done, failed = [], []
    for i, job in enumerate(todo, 1):
        target = Path(job["target"])
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = target.with_suffix(".raw.png")
        try:
            await provider.generate(job["prompt"], raw, 1080, 1350, references=job["refs"], aspect_ratio=job["aspect"],
                                    mime_type="image/png", resize=False)
            img = Image.open(raw)
            if job["kind"] == "background":
                from ..pipeline.images.base import resize_cover
                img.convert("RGB").save(target)
                resize_cover(target, 1080, 1350)
                Image.open(target).save(target)       # resize_cover 는 jpg 품질로 저장 → png 로 다시
            else:
                remove_white_background(img).save(target, optimize=True)
            _register(job, root, bg_root, tier)
            done.append(job["id"])
            log(f"[{i}/{len(todo)}] {job['kind']} {job['id']} 완료")
        except Exception as e:  # noqa: BLE001 - 한 장 실패해도 나머지는 계속
            failed.append({"id": job["id"], "error": f"{type(e).__name__}: {str(e)[:200]}"})
            log(f"[{i}/{len(todo)}] {job['kind']} {job['id']} 실패: {e}")
        finally:
            raw.unlink(missing_ok=True)
    return {"status": "ok" if not failed else "partial_failure", "generated": done, "failed": failed,
            **estimate([j for j in todo if j["id"] in done], tier), "note": "생성 그림은 approved=false. 시트 대조 후 approve 해야 렌더에 쓰인다."}


def approve(items: list[str], *, root: Path | None = None, bg_root: Path | None = None) -> list[str]:
    """'hamtorich_01/poses/x.png' 형태(캐릭터 포즈) 또는 'bg:<id>'(배경)를 승인한다."""
    ok = []
    index = None
    for item in items:
        if item.startswith("bg:"):
            index = index or load_index(bg_root)
            for e in index:
                if e["id"] == item[3:]:
                    e["approved"] = True
                    ok.append(item)
            continue
        cid, rel = item.split("/", 1)
        bible = charmod.get_character(cid, root)
        for p in bible.poses:
            if p.file == rel:
                p.approved = True
                ok.append(item)
        charmod.save_character(bible, root)
    if index is not None:
        save_index(index, bg_root)
    return ok
