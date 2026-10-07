"""Card/Comic Renderer — 캐러셀 페이지 한 장을 1080x1350 PNG 로 그린다 (Pillow).

모든 글자(제목·본문·말풍선·체크리스트·CTA)는 여기서 직접 합성한다. 이미지 생성 모델에는 글자를 맡기지 않는다.
영역·색·글자 크기는 템플릿(YAML)에서 오고, 페이지 타입별 그리기 함수는 RENDERERS 에 등록돼 있다.
페이지 하나가 실패해도 render_page 가 안전한 텍스트 페이지로 다시 그린다.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..pipeline.cards import wrap_to_width
from .schema import CardPage, ComicBeat, ComicPage, Page
from .templates import Template

BOLD = ("malgunbd.ttf", "NanumGothicBold.ttf", "AppleSDGothicNeo.ttc", "arialbd.ttf", "arial.ttf")
REGULAR = ("malgun.ttf", "NanumGothic.ttf", "AppleSDGothicNeo.ttc", "arial.ttf")
_FONT_CACHE: dict[tuple[int, bool], Any] = {}


def font(size: int, bold: bool = True):
    key = (size, bold)
    if key not in _FONT_CACHE:
        for name in (BOLD if bold else REGULAR):
            try:
                _FONT_CACHE[key] = ImageFont.truetype(name, size)
                break
            except OSError:
                continue
        else:
            _FONT_CACHE[key] = ImageFont.load_default()
    return _FONT_CACHE[key]


@dataclass
class PanelArt:
    """컷 하나의 그림. cutout = 투명 배경 캐릭터(앱이 배경을 그림), scene = 배경까지 있는 완성 그림(AI·업로드)."""
    kind: str                      # cutout | scene | none
    image: Image.Image | None = None
    source: str = ""               # mascot | reference | ai_generated | upload


@dataclass
class PageAssets:
    image: Path | None = None              # 카드 이미지 (권리 확인된 공개 자료·업로드)
    credit: str = ""                       # 이미지 출처 표기
    panels: list[PanelArt] = field(default_factory=list)
    guide: Image.Image | None = None       # character_info 템플릿의 안내 캐릭터
    index: int = 1
    total: int = 1


# ---------- 글자 ----------

_EMOJI = re.compile("[\U00010000-\U0010FFFF\u2600-\u27BF\uFE0F\u200D]")


def _clean(text: str) -> str:
    """공백 정리 + 글꼴에 없는 이모지 제거 (한글 글꼴에는 컬러 이모지가 없어 네모로 찍힌다)."""
    return " ".join(_EMOJI.sub("", text or "").split())


def _wrap(draw, text: str, fnt, max_w: float) -> list[str]:
    lines: list[str] = []
    for para in _EMOJI.sub("", text or "").split("\n"):
        para = _clean(para)
        if para:
            lines += wrap_to_width(draw, para, fnt, max_w)
    return lines or [""]


def fit(draw, text: str, max_w: float, max_h: float, start: int, min_size: int, max_lines: int,
        bold: bool = True, spacing: float = 1.32):
    """상자에 들어가는 가장 큰 글꼴. 최소 크기에서도 넘치면 줄을 자르고 말줄임표를 붙인다."""
    size = max(start, min_size)
    while True:
        fnt = font(size, bold)
        lines = _wrap(draw, text, fnt, max_w)
        line_h = int(size * spacing)
        if (len(lines) <= max_lines and line_h * len(lines) <= max_h) or size <= min_size:
            limit = max(1, min(max_lines, int(max_h // line_h) or 1))
            if len(lines) > limit:
                lines = lines[:limit]
                lines[-1] = lines[-1].rstrip()[:-1] + "…" if len(lines[-1]) > 1 else lines[-1]
            return fnt, lines, line_h
        size -= 2


def draw_text(draw, lines: list[str], fnt, line_h: int, box, *, align: str = "left", fill=(0, 0, 0),
              valign: str = "top", emphasis: str = "", highlight=None) -> int:
    """줄 목록을 상자 안에 그린다. emphasis 가 들어간 부분은 형광펜으로 칠한다. 마지막 y 를 돌려준다."""
    x0, y0, x1, y1 = box
    total = line_h * len(lines)
    y = y0 if valign == "top" else y0 + (y1 - y0 - total) / 2 if valign == "middle" else y1 - total
    emph = _clean(emphasis)
    for line in lines:
        w = draw.textlength(line, font=fnt)
        x = x0 if align == "left" else (x0 + x1 - w) / 2 if align == "center" else x1 - w
        if emph and highlight and emph in line:
            k = line.index(emph)
            hx = x + draw.textlength(line[:k], font=fnt)
            hw = draw.textlength(emph, font=fnt)
            size = fnt.size if hasattr(fnt, "size") else line_h
            draw.rectangle([hx - 4, y + size * 0.55, hx + hw + 4, y + size * 1.12], fill=highlight)
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_h
    return int(y)


def text_in(draw, tpl: Template, text: str, box, *, kind: str = "body", bold: bool | None = None,
            align: str | None = None, fill=None, valign: str = "top", emphasis: str = "", max_lines: int | None = None,
            start: int | None = None) -> int:
    if not _clean(text):
        return box[1]
    x0, y0, x1, y1 = box
    bold = (kind != "body") if bold is None else bold
    start = start or tpl.font_px(kind)
    min_size = tpl.font_px(f"{kind}_min", 0.028) if f"{kind}_min" in tpl.fonts else max(14, int(start * 0.6))
    max_lines = max_lines or int(tpl.style.get(f"{kind}_lines", 4))
    fnt, lines, lh = fit(draw, text, x1 - x0, y1 - y0, start, min_size, max_lines, bold=bold,
                         spacing=1.22 if kind == "title" or kind == "cover_title" else 1.42)
    return draw_text(draw, lines, fnt, lh, box, align=align or tpl.style.get("title_align", "left"),
                     fill=fill or tpl.color("ink"), valign=valign, emphasis=emphasis,
                     highlight=tpl.color("highlight") if emphasis else None)


# ---------- 바탕 ----------

def _gradient(w: int, h: int, top, bottom) -> Image.Image:
    grad = Image.new("RGB", (1, 256))
    for y in range(256):
        t = y / 255
        grad.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return grad.resize((w, h))


def _canvas(tpl: Template, page_type: str) -> Image.Image:
    cover = tpl.page_option(page_type, "background") == "cover"
    top = tpl.color("cover_bg" if cover else "bg")
    bottom = tpl.color("cover_bg2" if cover else "bg2", "#000000") if (cover and "cover_bg2" in tpl.palette) or \
        (not cover and "bg2" in tpl.palette) else top
    img = _gradient(tpl.width, tpl.height, top, bottom)
    if tpl.style.get("texture") == "dots" and not cover:
        d = ImageDraw.Draw(img)
        dot = tuple(max(0, c - 14) for c in top)
        step = int(tpl.width * 0.04)
        for y in range(step // 2, tpl.height, step):
            for x in range((y // step % 2) * step // 2, tpl.width, step):
                d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=dot)
    border = int(tpl.style.get("card_border", 0))
    if border and not cover:
        ImageDraw.Draw(img).rectangle([border // 2, border // 2, tpl.width - border // 2 - 1, tpl.height - border // 2 - 1],
                                      outline=tpl.color("line"), width=border)
    return img


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def cover_fit(img: Image.Image, w: int, h: int) -> Image.Image:
    scale = max(w / img.width, h / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    left, top = (img.width - w) // 2, max(0, int((img.height - h) * 0.35))
    return img.crop((left, top, left + w, top + h))


def paste_image(canvas: Image.Image, path: Path, box, radius: int) -> None:
    x0, y0, x1, y1 = box
    src = Image.open(path).convert("RGB")
    w, h = x1 - x0, y1 - y0
    ratio, target = src.width / src.height, w / h
    if abs(ratio - target) / target <= 0.45:
        tile = cover_fit(src, w, h)
    else:
        # 비율이 많이 다르면 흐린 배경 위에 원본 전체 (도표·세로 사진이 잘리지 않게)
        tile = cover_fit(src, w, h).filter(ImageFilter.GaussianBlur(28))
        tile = Image.blend(tile, Image.new("RGB", (w, h), (0, 0, 0)), 0.25)
        k = min(w / src.width, h / src.height)
        fg = src.resize((max(1, int(src.width * k)), max(1, int(src.height * k))), Image.LANCZOS)
        tile.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    canvas.paste(tile, (x0, y0), _rounded_mask((w, h), radius) if radius else None)


def _radius(tpl: Template) -> int:
    return int(tpl.width * float(tpl.style.get("radius", 0.03)))


def graphic_block(canvas: Image.Image, tpl: Template, box, text: str, index: int, seed: str = "",
                  show_index: bool = True) -> None:
    """이미지가 없거나 맞지 않을 때의 그래픽 카드: 큰 키워드/숫자 + 도형 장식. 억지로 사진을 넣지 않는다."""
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    accent = tpl.color("accent")
    tile = Image.new("RGB", (w, h), tuple(int(c + (255 - c) * 0.84) for c in accent))
    d = ImageDraw.Draw(tile)
    r = h * 0.42
    d.ellipse([w - r * 1.2, -r * 0.25, w + r * 0.8, r * 1.75], fill=tuple(int(c + (255 - c) * 0.68) for c in accent))
    d.ellipse([w * 0.06, h - r * 0.7, w * 0.06 + r * 0.5, h - r * 0.2], fill=tuple(int(c + (255 - c) * 0.5) for c in accent))
    label = _clean(text) or (f"{index:02d}" if show_index else "")
    if not label:
        canvas.paste(tile, (x0, y0), _rounded_mask((w, h), _radius(tpl)))
        return
    pad = int(w * 0.08)
    inner = (pad, pad, w - pad, h - pad)
    fnt, lines, lh = fit(d, label, inner[2] - inner[0], inner[3] - inner[1], tpl.font_px("big_number", 0.18),
                         tpl.font_px("title_min", 0.045), 3)
    draw_text(d, lines, fnt, lh, inner, align="center", valign="middle", fill=accent)
    canvas.paste(tile, (x0, y0), _rounded_mask((w, h), _radius(tpl)))


def pill(draw, tpl: Template, text: str, box, *, fill=None, ink=None) -> None:
    text = _clean(text)
    if not text:
        return
    x0, y0, x1, y1 = box
    fnt = font(tpl.font_px("label", 0.03))
    tw = draw.textlength(text, font=fnt)
    h = y1 - y0
    pad = h * 0.6
    align = tpl.style.get("title_align", "left")
    left = x0 if align == "left" else (x0 + x1 - tw) / 2 - pad
    draw.rounded_rectangle([left, y0, left + tw + pad * 2, y1], radius=h // 2, fill=fill or tpl.color("accent"))
    draw.text((left + pad, (y0 + y1) / 2), text, font=fnt, fill=ink or tpl.color("on_accent"), anchor="lm")


def footer(canvas: Image.Image, tpl: Template, page: Page, assets: PageAssets, *, dark: bool = False) -> None:
    d = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = tpl.box(page.type, "footer")
    fnt = font(tpl.font_px("footer", 0.021), bold=False)
    ink = tpl.color("cover_ink") if dark else tpl.color("sub")
    parts = [p for p in (assets.credit, f"출처: {page.source}" if _clean(page.source) and not assets.credit else "") if p]
    if parts:
        text = " · ".join(_clean(p) for p in parts)
        while d.textlength(text, font=fnt) > (x1 - x0) * 0.82 and len(text) > 4:
            text = text[:-2]
        if text != " · ".join(_clean(p) for p in parts):
            text = text.rstrip() + "…"
        d.text((x0, (y0 + y1) / 2), text, font=fnt, fill=ink, anchor="lm")
    if tpl.style.get("page_number", True) and assets.total > 1:
        d.text((x1, (y0 + y1) / 2), f"{assets.index} / {assets.total}", font=font(tpl.font_px("footer", 0.021)),
               fill=ink, anchor="rm")


# ---------- 카드 페이지 ----------

def _image_or_graphic(canvas, tpl, page: CardPage, assets: PageAssets, box, fallback_text: str) -> str:
    if assets.image and Path(assets.image).is_file():
        paste_image(canvas, Path(assets.image), box, _radius(tpl))
        return "image"
    graphic_block(canvas, tpl, box, fallback_text, assets.index, seed=page.headline)
    return "graphic"


def _guide(canvas: Image.Image, tpl: Template, page: CardPage, assets: PageAssets) -> bool:
    """character_info: 정보 카드 구석의 안내 캐릭터 + 짧은 한마디."""
    if not (tpl.character.get("on_cards") and assets.guide is not None and tpl.has_box(page.type, "character")):
        return False
    box = tpl.box(page.type, "character")
    paste_cutout(canvas, assets.guide, box, anchor="bottom")
    note = _clean(page.emphasis)
    if note and tpl.has_box(page.type, "card_bubble") and page.type not in ("cover", "cta"):
        bx = tpl.box(page.type, "card_bubble")
        speech_bubble(canvas, tpl, note, bx, tail_to=((box[0] + box[2]) / 2, box[1] + (box[3] - box[1]) * 0.2))
    return True


def r_cover(canvas, tpl, page: CardPage, assets: PageAssets) -> dict:
    d = ImageDraw.Draw(canvas)
    used = "none"
    if tpl.has_box("cover", "image"):
        box = tpl.box("cover", "image")
        if assets.image and Path(assets.image).is_file():
            paste_image(canvas, Path(assets.image), box, 0 if box[0] == 0 else _radius(tpl))
            used = "image"
        elif assets.guide is not None and not tpl.character.get("on_cards"):
            # 하이브리드·인스타툰 표지: 캐릭터를 크게 (그래픽 배경 위)
            graphic_block(canvas, tpl, box, "", assets.index, show_index=False)
            paste_cutout(canvas, assets.guide, box, anchor="bottom", scale=1.0)
            used = "character"
        else:
            graphic_block(canvas, tpl, box, page.emphasis or "", assets.index, show_index=False)
            used = "graphic"
    pill(d, tpl, page.label, tpl.box("cover", "label"),
         fill=tpl.color("highlight"), ink=tpl.color("ink"))
    text_in(d, tpl, page.headline, tpl.box("cover", "title"), kind="cover_title", bold=True,
            fill=tpl.color("cover_ink"), max_lines=3, start=tpl.font_px("cover_title", 0.095),
            emphasis="")
    text_in(d, tpl, page.body, tpl.box("cover", "body"), kind="body", fill=tpl.color("cover_ink"), max_lines=2)
    _guide(canvas, tpl, page, assets)
    footer(canvas, tpl, page, assets, dark=True)
    return {"image_use": used}


def r_hook(canvas, tpl, page: CardPage, assets: PageAssets) -> dict:
    d = ImageDraw.Draw(canvas)
    pill(d, tpl, page.label, tpl.box("hook", "label"))
    text_in(d, tpl, page.headline, tpl.box("hook", "title"), kind="title", max_lines=4,
            start=int(tpl.font_px("title") * 1.15), valign="middle", emphasis=page.emphasis)
    used = "text"
    if assets.image and Path(assets.image).is_file():
        paste_image(canvas, Path(assets.image), tpl.box("hook", "image"), _radius(tpl))
        used = "image"
    elif _clean(page.body):
        text_in(d, tpl, page.body, tpl.box("hook", "body"), kind="body", valign="top", max_lines=6)
    else:
        graphic_block(canvas, tpl, tpl.box("hook", "image"), "?", assets.index)
        used = "graphic"
    _guide(canvas, tpl, page, assets)
    footer(canvas, tpl, page, assets)
    return {"image_use": used}


def r_info(canvas, tpl, page: CardPage, assets: PageAssets) -> dict:
    d = ImageDraw.Draw(canvas)
    t = page.type
    pill(d, tpl, page.label, tpl.box(t, "label"))
    text_in(d, tpl, page.headline, tpl.box(t, "title"), kind="title", emphasis=page.emphasis)
    has_image = bool(assets.image and Path(assets.image).is_file())
    if has_image or _clean(page.emphasis):
        used = _image_or_graphic(canvas, tpl, page, assets, tpl.box(t, "image"), page.emphasis)
        body_box = tpl.box(t, "body")
    else:
        # 이미지도 강조 키워드도 없으면 본문이 그 자리까지 쓴다 (텍스트 중심 레이아웃)
        used = "text_only"
        ib, bb = tpl.box(t, "image"), tpl.box(t, "body")
        body_box = (bb[0], ib[1], bb[2], bb[3])
    text_in(d, tpl, page.body, body_box, kind="body", emphasis="" if used == "graphic" else page.emphasis,
            max_lines=int(tpl.style.get("body_lines", 6)) + (4 if used == "text_only" else 0),
            start=int(tpl.font_px("body") * (1.3 if used == "text_only" else 1.0)))
    _guide(canvas, tpl, page, assets)
    footer(canvas, tpl, page, assets)
    return {"image_use": used}


def _check_icon(d, box, color, ink) -> None:
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=int((x1 - x0) * 0.25), fill=color)
    d.line([(x0 + (x1 - x0) * 0.24, y0 + (y1 - y0) * 0.52), (x0 + (x1 - x0) * 0.43, y0 + (y1 - y0) * 0.72),
            (x0 + (x1 - x0) * 0.78, y0 + (y1 - y0) * 0.30)], fill=ink, width=max(3, int((x1 - x0) * 0.12)), joint="curve")


def _num_icon(d, box, n: int, color, ink, tpl) -> None:
    d.ellipse(box, fill=color)
    d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), str(n), font=font(int((box[3] - box[1]) * 0.55)),
           fill=ink, anchor="mm")


def _item_rows(canvas, tpl, items: list[str], box, icon: str) -> None:
    """체크리스트·요약 항목: 아이콘 + 글자, 모든 항목이 상자에 들어가는 가장 큰 크기로."""
    d = ImageDraw.Draw(canvas)
    items = [_clean(i) for i in items if _clean(i)][:6] or ["-"]
    x0, y0, x1, y1 = box
    gap = int(tpl.height * 0.018)
    size = int(tpl.font_px("item", 0.042) * 1.25)
    min_size = tpl.font_px("body_min", 0.03)
    while True:
        fnt = font(size, bold=True)
        icon_w = int(size * 1.25)
        text_w = (x1 - x0) - icon_w - size * 0.9 - size * 0.6
        wrapped = [_wrap(d, it, fnt, text_w)[:2] for it in items]
        lh = int(size * 1.35)
        heights = [max(icon_w, lh * len(w)) + int(size * 0.9) for w in wrapped]
        if sum(heights) + gap * (len(items) - 1) <= (y1 - y0) or size <= min_size:
            break
        size -= 2
    total = sum(heights) + gap * (len(items) - 1)
    y = y0 + max(0, ((y1 - y0) - total) // 2)
    for n, (lines, h) in enumerate(zip(wrapped, heights), start=1):
        d.rounded_rectangle([x0, y, x1, y + h], radius=_radius(tpl) // 2, fill=tpl.color("panel"),
                            outline=tpl.color("line"), width=max(2, int(tpl.style.get("card_border", 2)) // 2))
        ix = x0 + size * 0.45
        iy = y + (h - icon_w) / 2
        ibox = [ix, iy, ix + icon_w, iy + icon_w]
        if icon == "check":
            _check_icon(d, ibox, tpl.color("accent"), tpl.color("on_accent"))
        else:
            _num_icon(d, ibox, n, tpl.color("accent"), tpl.color("on_accent"), tpl)
        tx = ix + icon_w + size * 0.6
        ty = y + (h - lh * len(lines)) / 2
        for line in lines:
            d.text((tx, ty), line, font=fnt, fill=tpl.color("ink"))
            ty += lh
        y += h + gap


def r_checklist(canvas, tpl, page: CardPage, assets: PageAssets) -> dict:
    d = ImageDraw.Draw(canvas)
    pill(d, tpl, page.label or "CHECK", tpl.box("checklist", "label"))
    text_in(d, tpl, page.headline, tpl.box("checklist", "title"), kind="title", max_lines=2, emphasis=page.emphasis)
    items = page.items or [s for s in page.body.split("\n") if s.strip()]
    _item_rows(canvas, tpl, items, tpl.box("checklist", "items"), "check")
    _guide(canvas, tpl, page, assets)
    footer(canvas, tpl, page, assets)
    return {"image_use": "none"}


def r_summary(canvas, tpl, page: CardPage, assets: PageAssets) -> dict:
    d = ImageDraw.Draw(canvas)
    pill(d, tpl, page.label or "SUMMARY", tpl.box("summary", "label"))
    text_in(d, tpl, page.headline, tpl.box("summary", "title"), kind="title", max_lines=2, emphasis=page.emphasis)
    items = page.items or [s for s in page.body.split("\n") if s.strip()] or [page.body]
    _item_rows(canvas, tpl, items, tpl.box("summary", "items"), "number")
    _guide(canvas, tpl, page, assets)
    footer(canvas, tpl, page, assets)
    return {"image_use": "none"}


def bullets(d, tpl: Template, points: list[str], box, start: int) -> None:
    """글머리표 목록. 줄이 넘어가면 글머리표 뒤에 맞춰 들여쓴다 (글머리표만 한 줄에 남지 않게)."""
    x0, y0, x1, y1 = box
    points = [_clean(p) for p in points if _clean(p)] or ["-"]
    size = start
    while True:
        fnt = font(size, bold=False)
        indent = d.textlength("• ", font=fnt)
        wrapped = [_wrap(d, p, fnt, (x1 - x0) - indent) for p in points]
        lh = int(size * 1.4)
        total = sum(len(w) for w in wrapped) * lh + (len(points) - 1) * int(size * 0.4)
        if total <= (y1 - y0) or size <= 18:
            break
        size -= 2
    y = y0
    for lines in wrapped:
        d.text((x0, y), "•", font=fnt, fill=tpl.color("accent"))
        for line in lines:
            if y + lh > y1 + lh * 0.3:
                return
            d.text((x0 + indent, y), line, font=fnt, fill=tpl.color("ink"))
            y += lh
        y += int(size * 0.4)


def r_comparison(canvas, tpl, page: CardPage, assets: PageAssets) -> dict:
    d = ImageDraw.Draw(canvas)
    pill(d, tpl, page.label or "COMPARE", tpl.box("comparison", "label"))
    text_in(d, tpl, page.headline, tpl.box("comparison", "title"), kind="title", max_lines=2, emphasis=page.emphasis)
    cmp = page.compare
    left, right = (cmp.left_label, cmp.right_label) if cmp else ("A", "B")
    lp, rp = (cmp.left_points, cmp.right_points) if cmp else ([page.body], [])
    x0, y0, x1, y1 = tpl.box("comparison", "compare")
    gap = (x1 - x0) * 0.06
    col_w = ((x1 - x0) - gap) / 2
    head_h = int(tpl.height * 0.075)
    colors = (tpl.color("accent"), tpl.color("ink"))
    # 항목 글자 양에 맞춰 칸 높이를 정하고 세로 가운데에 둔다 (빈 칸이 길게 남지 않게)
    psize = int(tpl.font_px("item", 0.042) * 1.1)
    pfont = font(psize, bold=False)
    plines = max(len(_wrap(d, "\n".join(f"• {_clean(p)}" for p in pts if _clean(p)) or "-", pfont, col_w * 0.84))
                 for pts in (lp, rp))
    need = head_h + int(psize * 1.42 * plines + col_w * 0.2)
    if need < y1 - y0:
        y0 = y0 + ((y1 - y0) - need) // 3
        y1 = y0 + need
    for k, (label, points) in enumerate(((left, lp), (right, rp))):
        cx0 = x0 + k * (col_w + gap)
        cx1 = cx0 + col_w
        d.rounded_rectangle([cx0, y0, cx1, y1], radius=_radius(tpl), fill=tpl.color("panel"),
                            outline=colors[k], width=5)
        d.rounded_rectangle([cx0, y0, cx1, y0 + head_h], radius=_radius(tpl), fill=colors[k])
        d.rectangle([cx0, y0 + head_h - _radius(tpl), cx1, y0 + head_h], fill=colors[k])
        fnt, lines, lh = fit(d, _clean(label), col_w * 0.86, head_h * 0.8, tpl.font_px("item", 0.042), 20, 1)
        draw_text(d, lines, fnt, lh, (cx0, y0, cx1, y0 + head_h), align="center", valign="middle",
                  fill=tpl.color("on_accent"))
        pad = col_w * 0.08
        bullets(d, tpl, points, (int(cx0 + pad), int(y0 + head_h + pad), int(cx1 - pad), int(y1 - pad)), psize)
    r = gap * 1.1
    cx, cy = (x0 + x1) / 2, y0 + head_h / 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tpl.color("highlight"), outline=tpl.color("ink"), width=4)
    d.text((cx, cy), "VS", font=font(int(r * 0.9)), fill=tpl.color("ink"), anchor="mm")
    if tpl.has_box("comparison", "body") and "body" in (tpl._pages.get("comparison") or {}):
        text_in(d, tpl, page.body, tpl.box("comparison", "body"), kind="body")
    _guide(canvas, tpl, page, assets)
    footer(canvas, tpl, page, assets)
    return {"image_use": "none"}


def r_quote(canvas, tpl, page: CardPage, assets: PageAssets) -> dict:
    d = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = tpl.box("quote", "title")
    qf = font(int(tpl.width * 0.26))
    d.text((x0 - tpl.width * 0.02, y0 - tpl.height * 0.13), "“", font=qf, fill=tpl.color("accent"))
    text_in(d, tpl, page.headline, (x0, y0, x1, y1), kind="title", align="center", valign="middle", max_lines=5,
            emphasis=page.emphasis)
    by = _clean(page.body)
    if by:
        text_in(d, tpl, by if by.startswith("—") else f"— {by}", tpl.box("quote", "body"), kind="body",
                align="center", fill=tpl.color("sub"), max_lines=2)
    _guide(canvas, tpl, page, assets)
    footer(canvas, tpl, page, assets)
    return {"image_use": "none"}


def _icon(d, kind: str, cx: float, cy: float, s: float, color) -> None:
    w = max(4, int(s * 0.1))
    if kind == "save":
        d.polygon([(cx - s * 0.32, cy - s * 0.45), (cx + s * 0.32, cy - s * 0.45), (cx + s * 0.32, cy + s * 0.45),
                   (cx, cy + s * 0.2), (cx - s * 0.32, cy + s * 0.45)], outline=color, width=w)
    elif kind == "share":
        d.polygon([(cx - s * 0.45, cy - s * 0.05), (cx + s * 0.45, cy - s * 0.45), (cx + s * 0.1, cy + s * 0.45),
                   (cx, cy + s * 0.05)], outline=color, width=w)
    elif kind == "like":
        r = s * 0.24
        d.ellipse([cx - 2 * r, cy - s * 0.35, cx, cy - s * 0.35 + 2 * r], outline=color, width=w)
        d.ellipse([cx, cy - s * 0.35, cx + 2 * r, cy - s * 0.35 + 2 * r], outline=color, width=w)
        d.line([(cx - 2 * r + w / 2, cy - s * 0.1), (cx, cy + s * 0.42), (cx + 2 * r - w / 2, cy - s * 0.1)],
               fill=color, width=w, joint="curve")
    else:  # comment
        d.ellipse([cx - s * 0.45, cy - s * 0.38, cx + s * 0.45, cy + s * 0.3], outline=color, width=w)
        d.polygon([(cx - s * 0.25, cy + s * 0.18), (cx - s * 0.35, cy + s * 0.48), (cx, cy + s * 0.26)], fill=color)


def r_cta(canvas, tpl, page: CardPage, assets: PageAssets) -> dict:
    d = ImageDraw.Draw(canvas)
    ink = tpl.color("cover_ink")
    text_in(d, tpl, page.headline, tpl.box("cta", "title"), kind="cover_title", align="center", valign="middle",
            fill=ink, max_lines=3, start=tpl.font_px("cover_title", 0.09))
    text_in(d, tpl, page.body, tpl.box("cta", "body"), kind="body", align="center", fill=ink, max_lines=3)
    labels = [_clean(i) for i in page.items if _clean(i)][:4] or ["저장", "공유", "댓글"]
    kinds = []
    for label in labels:
        kinds.append("save" if "저장" in label else "share" if "공유" in label else
                     "like" if ("좋아요" in label or "팔로" in label) else "comment")
    x0, y0, x1, y1 = tpl.box("cta", "items")
    slot = (x1 - x0) / len(labels)
    s = min(slot * 0.42, (y1 - y0) * 0.55)
    for k, (label, kind) in enumerate(zip(labels, kinds)):
        cx = x0 + slot * (k + 0.5)
        d.ellipse([cx - s * 0.8, y0, cx + s * 0.8, y0 + s * 1.6], fill=tuple(min(255, c + 30) for c in tpl.color("cover_bg")))
        _icon(d, kind, cx, y0 + s * 0.8, s, ink)
        ty = y0 + s * 1.6 + tpl.height * 0.012
        lf, lines, lh = fit(d, label, slot * 0.92, tpl.height * 0.07, tpl.font_px("label", 0.03), 16, 2)
        draw_text(d, lines, lf, lh, (cx - slot * 0.46, ty, cx + slot * 0.46, ty + lh * 2), align="center", fill=ink)
    if assets.guide is not None:
        gb = tpl.box("cta", "character") if tpl.has_box("cta", "character") else None
        if gb and tpl.character.get("on_cards"):
            paste_cutout(canvas, assets.guide, gb, anchor="bottom")
    footer(canvas, tpl, page, assets, dark=True)
    return {"image_use": "none"}


# ---------- 만화 페이지 ----------

def paste_cutout(canvas: Image.Image, art: Image.Image, box, *, anchor: str = "bottom", scale: float = 1.0,
                 align: str = "center") -> tuple[float, float]:
    """투명 배경 캐릭터를 상자에 맞춰 붙인다. 머리 위치(x, y)를 돌려준다 (말풍선 꼬리 방향용)."""
    x0, y0, x1, y1 = box
    h = (y1 - y0) * scale
    w = h * art.width / art.height
    if w > (x1 - x0) * 1.3 * scale:
        w = (x1 - x0) * 1.3 * scale
        h = w * art.height / art.width
    img = art.resize((max(1, int(w)), max(1, int(h))), Image.LANCZOS)
    x = x0 + ((x1 - x0) - w) / 2 if align == "center" else (x0 if align == "left" else x1 - w)
    y = y1 - h if anchor == "bottom" else y0
    # 상자 밖으로 나간 부분은 잘라 낸다
    region = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    region.paste(img, (int(x), int(y)), img)
    clip = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(clip).rectangle(box, fill=255)
    alpha = Image.composite(region.getchannel("A"), Image.new("L", canvas.size, 0), clip)
    canvas.paste(region.convert("RGB"), (0, 0), alpha)
    return x + w / 2, y + h * 0.33


INDOOR = ("사무실", "집", "거실", "방", "카페", "회사", "은행", "교실", "부엌", "실내", "office", "room", "home", "cafe")
OUTDOOR = ("거리", "공원", "밖", "길", "아파트 단지", "동네", "야외", "street", "park", "outside")


def scene_background(tpl: Template, size: tuple[int, int], beat: ComicBeat, reaction: bool) -> Image.Image:
    """AI 배경이 없을 때 앱이 그리는 단순한 배경 (실내/야외/집중선)."""
    w, h = size
    bg = beat.background or ""
    if reaction or beat.emotion in ("surprised", "angry"):
        img = Image.new("RGB", size, tpl.color("bg"))
        d = ImageDraw.Draw(img)
        cx, cy = w / 2, h * 0.45
        ink = tuple(int(c * 0.85) for c in tpl.color("bg2"))
        for k in range(48):
            a = k / 48 * 2 * math.pi
            a2 = a + 0.035
            r0, r1 = min(w, h) * 0.32, max(w, h)
            d.polygon([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + r1 * math.cos(a), cy + r1 * math.sin(a)),
                       (cx + r1 * math.cos(a2), cy + r1 * math.sin(a2))], fill=ink)
        return img
    if any(k in bg for k in OUTDOOR):
        img = _gradient(w, h, tpl.color("scene_sky", "#CFE6FF"), (255, 255, 255))
        d = ImageDraw.Draw(img)
        ground = int(h * 0.74)
        for k in range(6):
            bx = int(w * (k * 0.18 - 0.04))
            bh = int(h * (0.28 + 0.12 * ((k * 37) % 3)))
            d.rectangle([bx, ground - bh, bx + int(w * 0.15), ground], fill=(225, 232, 242))
        d.rectangle([0, ground, w, h], fill=tpl.color("scene_ground", "#BFD9A8"))
        return img
    img = Image.new("RGB", size, tpl.color("scene_wall", "#F3E9D7"))
    d = ImageDraw.Draw(img)
    floor = int(h * 0.76)
    d.rectangle([0, floor, w, h], fill=tpl.color("scene_floor", "#D9C7A8"))
    d.line([(0, floor), (w, floor)], fill=tuple(int(c * 0.8) for c in tpl.color("scene_floor", "#D9C7A8")), width=4)
    if any(k in bg for k in INDOOR) or not bg:
        wx0, wy0, wx1, wy1 = int(w * 0.08), int(h * 0.12), int(w * 0.36), int(h * 0.48)
        d.rectangle([wx0, wy0, wx1, wy1], fill=(214, 236, 255), outline=(255, 255, 255), width=10)
        d.line([((wx0 + wx1) / 2, wy0), ((wx0 + wx1) / 2, wy1)], fill=(255, 255, 255), width=8)
        d.line([(wx0, (wy0 + wy1) / 2), (wx1, (wy0 + wy1) / 2)], fill=(255, 255, 255), width=8)
    return img


def _bubble_box(panel, position: str, text_h_ratio: float = 0.30):
    x0, y0, x1, y1 = panel
    w, h = x1 - x0, y1 - y0
    bw, bh = w * 0.56, h * text_h_ratio
    m = w * 0.045
    pos = position if position in ("top_left", "top_right", "bottom_left", "bottom_right", "top", "bottom") else "top_right"
    bx = x0 + m if "left" in pos else x1 - m - bw if "right" in pos else x0 + (w - bw) / 2
    by = y0 + m if pos.startswith("top") else y1 - m - bh
    return (bx, by, bx + bw, by + bh)


def speech_bubble(canvas: Image.Image, tpl: Template, text: str, box, tail_to: tuple[float, float] | None = None,
                  shout: bool = False) -> None:
    """빈 말풍선을 그리고 실제 대사를 합성한다 (이미지 모델이 글자를 만들지 않는다)."""
    text = _clean(text)
    if not text:
        return
    d = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = [int(v) for v in box]
    pad_x, pad_y = (x1 - x0) * 0.1, (y1 - y0) * 0.16
    fnt, lines, lh = fit(d, text, (x1 - x0) - pad_x * 2, (y1 - y0) - pad_y * 2, tpl.font_px("bubble", 0.04),
                         tpl.font_px("bubble_min", 0.029), 4, bold=True, spacing=1.3)
    # 글자 양에 맞춰 말풍선을 줄인다
    tw = max(d.textlength(l, font=fnt) for l in lines)
    th = lh * len(lines)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    bw, bh = min(x1 - x0, tw + pad_x * 2.2), min(y1 - y0, th + pad_y * 2.4)
    bx0, by0, bx1, by1 = cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2
    line_c, fill_c = tpl.color("bubble_line", "#151515"), tpl.color("bubble", "#FFFFFF")
    lw = max(4, int(tpl.width * 0.005))
    if tail_to:
        tx, ty = tail_to
        bxm = min(max(tx, bx0 + bw * 0.25), bx1 - bw * 0.25)
        base_y = by1 if ty > by1 else by0
        dy = ty - base_y
        tip = (bxm + (tx - bxm) * 0.35, base_y + max(-bh * 0.6, min(bh * 0.6, dy * 0.45)))
        tail = [(bxm - bw * 0.07, base_y), tip, (bxm + bw * 0.07, base_y)]
        d.polygon(tail, fill=fill_c)
        d.line([tail[0], tail[1], tail[2]], fill=line_c, width=lw, joint="curve")
    if shout:
        pts = []
        for k in range(28):
            a = k / 28 * 2 * math.pi
            r = 1.0 if k % 2 == 0 else 0.86
            pts.append((cx + bw / 2 * 1.08 * r * math.cos(a), cy + bh / 2 * 1.12 * r * math.sin(a)))
        d.polygon(pts, fill=fill_c, outline=line_c)
        d.line(pts + [pts[0]], fill=line_c, width=lw)
    else:
        d.rounded_rectangle([bx0, by0, bx1, by1], radius=int(min(bw, bh) * 0.45), fill=fill_c, outline=line_c, width=lw)
        if tail_to:   # 꼬리와 몸통 사이 선을 지운다
            d.line([(tail[0][0] + lw, base_y), (tail[2][0] - lw, base_y)], fill=fill_c, width=lw + 2)
    draw_text(d, lines, fnt, lh, (bx0, by0, bx1, by1), align="center", valign="middle", fill=tpl.color("ink"))


def narration_box(canvas, tpl: Template, text: str, box, *, top: bool) -> None:
    text = _clean(text)
    if not text:
        return
    d = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = box
    w = x1 - x0
    fnt, lines, lh = fit(d, text, w * 0.86, (y1 - y0) * 0.30, tpl.font_px("body", 0.04), tpl.font_px("body_min", 0.03) - 4,
                         3, bold=True)
    tw = max(d.textlength(l, font=fnt) for l in lines)
    pad = fnt.size * 0.5 if hasattr(fnt, "size") else 10
    bx0 = x0 + w * 0.03
    by0 = y0 + w * 0.03 if top else y1 - w * 0.03 - lh * len(lines) - pad * 2
    rect = [bx0, by0, bx0 + tw + pad * 2, by0 + lh * len(lines) + pad * 2]
    d.rectangle(rect, fill=tpl.color("highlight"), outline=tpl.color("bubble_line", "#151515"), width=4)
    draw_text(d, lines, fnt, lh, (rect[0] + pad, rect[1] + pad, rect[2] - pad, rect[3] - pad), fill=tpl.color("ink"))


def draw_panel(canvas: Image.Image, tpl: Template, box, beat: ComicBeat, art: PanelArt, *, reaction: bool,
               headline: str = "", caption: str = "") -> str:
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    bubble_pos = beat.speech_bubble_position or "top_right"
    used = art.source or "none"
    if art.kind == "scene" and art.image is not None:
        canvas.paste(cover_fit(art.image.convert("RGB"), w, h), (x0, y0))
        head = (x0 + w * (0.3 if "right" in bubble_pos else 0.7), y0 + h * 0.4)
    else:
        canvas.paste(scene_background(tpl, (w, h), beat, reaction), (x0, y0))
        head = (x0 + w / 2, y0 + h * 0.4)
        if art.kind == "cutout" and art.image is not None:
            cam = (beat.camera or "medium").lower()
            scale = {"close_up": 1.55, "closeup": 1.55, "wide": 0.62}.get(cam, 0.92)
            side = "left" if "right" in bubble_pos else "right" if "left" in bubble_pos else "center"
            area = (x0 + int(w * (0.02 if side == "left" else 0.30 if side == "right" else 0.16)), y0,
                    x0 + int(w * (0.70 if side == "left" else 0.98 if side == "right" else 0.84)), y1)
            # 클로즈업은 아래로 내려 얼굴 위주로 보이게 한다
            if scale > 1.2:
                ah = (area[3] - area[1]) * scale
                area2 = (area[0], int(y1 - ah * 0.62), area[2], int(y1 - ah * 0.62 + ah))
                head = paste_cutout(canvas, art.image, area2, anchor="top", scale=1.0)
                head = (head[0], min(y1 - h * 0.2, head[1]))
            else:
                top_y = y1 - (y1 - y0) * scale
                head = paste_cutout(canvas, art.image, (area[0], int(top_y), area[2], y1), anchor="bottom")
    speech_bubble(canvas, tpl, beat.dialogue, _bubble_box((x0, y0, x1, y1), bubble_pos), tail_to=head,
                  shout=reaction and beat.emotion in ("surprised", "angry"))
    # 상단/하단 캡션은 말풍선 반대쪽에 하나로 모아 겹치지 않게 한다
    note = " ".join(t for t in (_clean(headline), _clean(caption)) if t)
    narration_box(canvas, tpl, note, (x0, y0, x1, y1), top=bubble_pos.startswith("bottom"))
    border = int(tpl.style.get("panel_border", 6))
    ImageDraw.Draw(canvas).rectangle([x0, y0, x1, y1], outline=tpl.color("line", "#151515"), width=border)
    return used


def r_comic(canvas, tpl, page: ComicPage, assets: PageAssets) -> dict:
    d = ImageDraw.Draw(canvas)
    t = page.type
    panel = tpl.box(t, "panel")
    beats = page.panels[:2] or [ComicBeat(character_id="", dialogue=page.headline)]
    arts = assets.panels + [PanelArt(kind="none")] * (len(beats) - len(assets.panels))
    reaction = t == "reaction_scene"
    used = []
    explanation = t == "explanation_scene"
    if len(beats) == 1:
        boxes = [panel]
    else:
        x0, y0, x1, y1 = panel
        gap = int(tpl.height * 0.018)
        mid = (y0 + y1) // 2
        boxes = [(x0, y0, x1, mid - gap // 2), (x0, mid + gap // 2, x1, y1)]
    for k, (beat, art, box) in enumerate(zip(beats, arts, boxes)):
        used.append(draw_panel(canvas, tpl, box, beat, art, reaction=reaction,
                               headline=page.headline if k == 0 else "",
                               caption=page.caption if (k == len(beats) - 1 and not explanation) else ""))
    if explanation and _clean(page.caption):
        cx0, cy0, cx1, cy1 = tpl.box(t, "caption")
        d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=_radius(tpl), fill=tpl.color("panel"),
                            outline=tpl.color("line"), width=int(tpl.style.get("card_border", 4)) or 4)
        pad = int((cx1 - cx0) * 0.05)
        text_in(d, tpl, page.caption, (cx0 + pad, cy0 + pad, cx1 - pad, cy1 - pad), kind="body", bold=False,
                valign="middle", emphasis=page.emphasis, max_lines=5)
    footer(canvas, tpl, page, assets)
    return {"image_use": ",".join(used), "panels": len(beats)}


RENDERERS: dict[str, Callable[..., dict]] = {
    "cover": r_cover, "hook": r_hook, "info_card": r_info, "checklist": r_checklist, "comparison": r_comparison,
    "quote": r_quote, "summary": r_summary, "cta": r_cta,
    "comic_scene": r_comic, "dialogue_scene": r_comic, "reaction_scene": r_comic, "explanation_scene": r_comic,
}


def render_safe(page: Page, tpl: Template, out_path: Path, assets: PageAssets) -> Path:
    """최후 대체: 이미지 없이 글자만 있는 단순 페이지. 어떤 페이지 타입이든 실패하지 않게 한다."""
    img = Image.new("RGB", (tpl.width, tpl.height), tpl.color("bg"))
    d = ImageDraw.Draw(img)
    m = int(tpl.width * 0.09)
    text = page.headline
    body = getattr(page, "body", "") or getattr(page, "caption", "")
    if isinstance(page, ComicPage):
        body = "\n".join(f"{b.dialogue}" for b in page.panels if b.dialogue) + ("\n" + page.caption if page.caption else "")
    elif getattr(page, "items", None):
        body = "\n".join(f"• {i}" for i in page.items)
    y = text_in(d, tpl, text or " ", (m, int(tpl.height * 0.12), tpl.width - m, int(tpl.height * 0.38)), kind="title")
    text_in(d, tpl, body, (m, max(y + 30, int(tpl.height * 0.42)), tpl.width - m, int(tpl.height * 0.9)), kind="body",
            max_lines=12)
    d.text((tpl.width - m, int(tpl.height * 0.955)), f"{assets.index} / {assets.total}",
           font=font(tpl.font_px("footer", 0.021)), fill=tpl.color("sub"), anchor="rm")
    img.save(out_path, "PNG", optimize=True)
    return out_path


def render_page(page: Page, tpl: Template, out_path: Path, assets: PageAssets) -> dict[str, Any]:
    """페이지 한 장을 PNG 로. 실패하면 render_safe 로 다시 그리고 fallback 사유를 남긴다."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fn = RENDERERS.get(page.type)
        if not fn:
            raise ValueError(f"지원하지 않는 페이지 타입: {page.type}")
        canvas = _canvas(tpl, page.type)
        info = fn(canvas, tpl, page, assets)
        canvas.save(out_path, "PNG", optimize=True)
        return {"path": str(out_path), "fallback_used": False, **info}
    except Exception as e:  # noqa: BLE001 - 페이지 하나 때문에 전체가 멈추지 않게
        render_safe(page, tpl, out_path, assets)
        return {"path": str(out_path), "fallback_used": True, "fallback_reason": f"{type(e).__name__}: {e}"[:200],
                "image_use": "none"}
