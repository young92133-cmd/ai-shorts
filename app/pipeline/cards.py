"""2D 내부 생성 카드. 권리 걱정 없이 앱이 직접 그리는 장면 화면.

분야와 무관하게 '내용 성격'별 모양만 다르다:
  hook_card(시선 끄는 질문) · statement_card(핵심 주장) · number_card(큰 숫자) · trend_card(숫자+증감 화살표)
  compare_card(두 대상 비교) · summary_card(결론 정리) · safe_card(최후 대체)

모든 글자는 실제 폭을 재서 줄바꿈·축소하므로 9:16 화면 밖으로 나가지 않는다.
하단 30%는 자막 자리라 비워 두고, 내용은 화면 위쪽 60% 안에 둔다.
"""
from __future__ import annotations

import colorsys
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CARD_KINDS = ("hook_card", "statement_card", "focus_card", "quote_card", "number_card", "trend_card",
              "compare_card", "summary_card", "safe_card")
TEXT_CARDS = ("statement_card", "focus_card", "quote_card")   # 같은 문구를 다른 모양으로 보여 주는 카드
SIDE = 0.085            # 좌우 여백 비율
CONTENT_BOTTOM = 0.62   # 이 아래는 자막 자리
TITLE_BOTTOM = 0.23     # 이 위는 상단 키워드 자리 (ASS Title: MarginV 14% + 최대 2줄)
LABELS = {"hook_card": "", "statement_card": "핵심", "focus_card": "포인트", "quote_card": "", "number_card": "숫자로 보면",
          "trend_card": "변화", "compare_card": "비교", "summary_card": "정리", "safe_card": ""}
HUES = {"hook_card": 0.02, "statement_card": 0.60, "focus_card": 0.08, "quote_card": 0.83, "number_card": 0.12,
        "trend_card": 0.40, "compare_card": 0.75, "summary_card": 0.53, "safe_card": 0.62}


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("malgunbd.ttf", "malgun.ttf", "NanumGothicBold.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    box = draw.textbbox((0, 0), text, font=font, stroke_width=0)
    return box[2] - box[0]


def wrap_to_width(draw: ImageDraw.ImageDraw, text: str, font, max_w: float) -> list[str]:
    """단어 단위로 줄바꿈하고, 한 단어가 너무 길면 글자 단위로 자른다."""
    lines: list[str] = []
    cur = ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if _width(draw, trial, font) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = ""
        for ch in word:
            if _width(draw, cur + ch, font) <= max_w:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def fit_text(draw: ImageDraw.ImageDraw, text: str, max_w: float, max_h: float, start: int,
             min_size: int = 34, max_lines: int = 3) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """상자 안에 들어가는 가장 큰 글자 크기와 줄 목록. (글꼴, 줄들, 줄 높이)"""
    size = start
    while True:
        font = _font(size)
        lines = wrap_to_width(draw, text, font, max_w)
        line_h = int(size * 1.22)
        if (len(lines) <= max_lines and line_h * len(lines) <= max_h) or size <= min_size:
            if len(lines) > max_lines:   # 최소 크기에서도 넘치면 줄 수를 자르고 말줄임
                lines = lines[:max_lines]
                lines[-1] = lines[-1].rstrip()[:-1] + "…" if len(lines[-1]) > 1 else lines[-1]
            return font, lines, line_h
        size -= 4


def _palette(kind: str, variant: int, seed: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    jitter = int(hashlib.md5(seed.encode()).hexdigest()[:2], 16) / 255 * 0.06
    h = (HUES.get(kind, 0.6) + variant * 0.18 + jitter) % 1
    top = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, 0.55, 0.36))
    bottom = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((h + 0.05) % 1, 0.70, 0.12))
    accent = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((h + 0.5) % 1, 0.75, 0.98))
    return top, bottom, accent


def _background(w: int, h: int, top, bottom, variant: int) -> Image.Image:
    grad = Image.new("RGB", (1, 256))
    for y in range(256):
        t = y / 255
        grad.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    img = grad.resize((w, h))
    # 은은한 도형 장식 (같은 종류 카드가 이어져도 달라 보이게 variant 로 배치를 바꾼다)
    deco = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(deco)
    if variant % 2 == 0:
        d.ellipse([int(w * 0.55), int(-h * 0.05), int(w * 1.35), int(h * 0.40)], fill=38)
        d.ellipse([int(-w * 0.35), int(h * 0.55), int(w * 0.45), int(h * 1.0)], fill=26)
    else:
        for k in range(7):
            x = int(-w * 0.2 + k * w * 0.22)
            d.polygon([(x, 0), (x + int(w * 0.08), 0), (x - int(w * 0.35), h), (x - int(w * 0.43), h)], fill=18)
    deco = deco.filter(ImageFilter.GaussianBlur(24))
    img.paste(Image.new("RGB", (w, h), (255, 255, 255)), (0, 0), deco)
    return img


def _center(draw, lines, font, line_h, cx, top, fill="white", stroke=5) -> int:
    y = top
    for line in lines:
        draw.text((cx, y), line, font=font, fill=fill, anchor="ma", stroke_width=stroke, stroke_fill=(0, 0, 0))
        y += line_h
    return y


def _pill(draw, text: str, cx: float, y: int, accent, w: int) -> int:
    if not text:
        return y
    font = _font(int(w * 0.045))
    tw = _width(draw, text, font)
    pad_x, pad_y = int(w * 0.035), int(w * 0.018)
    box = [cx - tw / 2 - pad_x, y, cx + tw / 2 + pad_x, y + font.size + pad_y * 2]
    draw.rounded_rectangle(box, radius=int(font.size * 0.9), fill=accent)
    draw.text((cx, y + pad_y), text, font=font, fill=(20, 20, 24), anchor="ma")
    return int(box[3]) + int(w * 0.05)


def _arrow(draw, cx: float, cy: float, size: float, up: bool, color) -> None:
    s = size
    if up:
        pts = [(cx, cy - s), (cx + s * 0.8, cy), (cx + s * 0.3, cy), (cx + s * 0.3, cy + s),
               (cx - s * 0.3, cy + s), (cx - s * 0.3, cy), (cx - s * 0.8, cy)]
    else:
        pts = [(cx, cy + s), (cx + s * 0.8, cy), (cx + s * 0.3, cy), (cx + s * 0.3, cy - s),
               (cx - s * 0.3, cy - s), (cx - s * 0.3, cy), (cx - s * 0.8, cy)]
    draw.polygon(pts, fill=color)


def render_card(kind: str, out_path: Path, *, width: int = 1080, height: int = 1920, emphasis: str = "",
                key_number: str = "", compare_a: str = "", compare_b: str = "", trend_up: bool = True,
                variant: int = 0, seed: str = "") -> Path:
    """카드 한 장을 그려 저장한다. 텍스트가 비어도 빈 화면이 아닌 장식 카드가 나온다."""
    if kind not in CARD_KINDS:
        kind = "statement_card"
    top, bottom, accent = _palette(kind, variant, seed or emphasis or kind)
    img = _background(width, height, top, bottom, variant)
    draw = ImageDraw.Draw(img)
    cx = width / 2
    max_w = width * (1 - 2 * SIDE)
    limit = height * CONTENT_BOTTOM
    y = int(height * 0.20)
    emphasis = " ".join(emphasis.split())

    if kind == "hook_card":
        mark = _font(int(width * 0.55))
        draw.text((cx, int(height * 0.10)), "?" if emphasis.endswith("?") else "!", font=mark,
                  fill=tuple(min(255, c + 40) for c in top), anchor="ma")
        font, lines, lh = fit_text(draw, emphasis, max_w, limit - height * 0.30, int(width * 0.12))
        _center(draw, lines, font, lh, cx, int(height * 0.30))
    elif kind in ("number_card", "trend_card"):
        y = _pill(draw, LABELS[kind], cx, y, accent, width)
        num = key_number or emphasis
        nfont, nlines, nlh = fit_text(draw, num, max_w * (0.72 if kind == "trend_card" else 1.0),
                                      height * 0.16, int(width * 0.24), max_lines=1)
        if kind == "trend_card":
            _arrow(draw, cx + max_w * 0.40, y + nlh * 0.55, width * 0.07, trend_up, accent)
            _center(draw, nlines, nfont, nlh, cx - max_w * 0.10, y, fill=accent, stroke=6)
        else:
            _center(draw, nlines, nfont, nlh, cx, y, fill=accent, stroke=6)
        y += nlh + int(height * 0.03)
        label = emphasis if emphasis and emphasis != num else ""
        if label:
            font, lines, lh = fit_text(draw, label, max_w, limit - y, int(width * 0.075), max_lines=2)
            _center(draw, lines, font, lh, cx, y)
    elif kind == "compare_card":
        if emphasis:
            font, lines, lh = fit_text(draw, emphasis, max_w, height * 0.12, int(width * 0.075), max_lines=2)
            y = _center(draw, lines, font, lh, cx, y) + int(height * 0.03)
        box_w, gap = max_w * 0.46, max_w * 0.08
        box_top, box_bottom = y, min(limit, y + height * 0.24)
        for k, (label, x0) in enumerate(((compare_a or "A", cx - gap / 2 - box_w), (compare_b or "B", cx + gap / 2))):
            fill = tuple(min(255, c + 25) for c in top) if k == 0 else tuple(min(255, c + 10) for c in bottom)
            draw.rounded_rectangle([x0, box_top, x0 + box_w, box_bottom], radius=int(width * 0.04),
                                   fill=fill, outline=accent, width=5)
            font, lines, lh = fit_text(draw, label, box_w * 0.84, (box_bottom - box_top) * 0.8,
                                       int(width * 0.075), min_size=30, max_lines=3)
            text_h = lh * len(lines)
            _center(draw, lines, font, lh, x0 + box_w / 2, int((box_top + box_bottom - text_h) / 2), stroke=3)
        vs = _font(int(width * 0.06))
        r = width * 0.055
        my = (box_top + box_bottom) / 2
        draw.ellipse([cx - r, my - r, cx + r, my + r], fill=accent)
        draw.text((cx, my), "VS", font=vs, fill=(20, 20, 24), anchor="mm")
    elif kind == "quote_card":
        qfont = _font(int(width * 0.30))
        draw.text((cx - max_w * 0.34, int(height * 0.13)), "“", font=qfont, fill=accent, anchor="ma")
        font, lines, lh = fit_text(draw, emphasis, max_w * 0.9, limit - height * 0.34, int(width * 0.10))
        end = _center(draw, lines, font, lh, cx, int(height * 0.30))
        draw.text((cx + max_w * 0.34, end - int(height * 0.02)), "”", font=qfont, fill=accent, anchor="ma")
    elif kind == "focus_card":
        y = _pill(draw, LABELS[kind], cx, y + int(height * 0.04), accent, width)
        font, lines, lh = fit_text(draw, emphasis, max_w * 0.86, limit - y - height * 0.06, int(width * 0.105))
        box_h = lh * len(lines) + int(height * 0.05)
        draw.rounded_rectangle([cx - max_w / 2, y, cx + max_w / 2, y + box_h], radius=int(width * 0.03),
                               fill=tuple(int(c * 0.35) for c in accent), outline=accent, width=6)
        _center(draw, lines, font, lh, cx, y + int(height * 0.025))
    else:  # statement / summary / safe
        y = _pill(draw, LABELS.get(kind, ""), cx, y + int(height * 0.04), accent, width)
        if kind == "summary_card":
            r = width * 0.07
            draw.ellipse([cx - r, y, cx + r, y + 2 * r], outline=accent, width=10)
            draw.line([(cx - r * 0.45, y + r), (cx - r * 0.1, y + r * 1.4), (cx + r * 0.5, y + r * 0.6)],
                      fill=accent, width=12)
            y += int(2 * r + height * 0.03)
        if emphasis:
            font, lines, lh = fit_text(draw, emphasis, max_w, limit - y, int(width * 0.11))
            _center(draw, lines, font, lh, cx, y)
    img.save(out_path, quality=92)
    return out_path


def fit_image(path: Path, width: int, height: int) -> str:
    """업로드 이미지를 9:16 에 맞춘다. 비율이 비슷하면 가운데를 채워 자르고(cover),
    많이 다르면 흐린 배경 위에 원본 전체를 얹어(contain) 잘리거나 찌그러지지 않게 한다. 쓴 방식을 돌려준다."""
    img = Image.open(path).convert("RGB")
    target = width / height
    ratio = img.width / img.height
    if abs(ratio - target) / target <= 0.12:
        scale = max(width / img.width, height / img.height)
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
        left, top = (img.width - width) // 2, (img.height - height) // 2
        img.crop((left, top, left + width, top + height)).save(path, quality=92)
        return "cover"
    bg_scale = max(width / img.width, height / img.height)
    bg = img.resize((round(img.width * bg_scale), round(img.height * bg_scale)), Image.LANCZOS)
    left, top = (bg.width - width) // 2, (bg.height - height) // 2
    bg = bg.crop((left, top, left + width, top + height)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (width, height), (0, 0, 0)), 0.35)
    # 원본 전체를 상단 키워드(14~22%)와 자막 자리(62%~) 사이에 비율 그대로 넣는다.
    # 도표·인포그래픽의 글자가 상단 키워드와 겹치지 않게 키워드 아래에서 시작한다.
    area_top, area_bottom = int(height * TITLE_BOTTOM), int(height * CONTENT_BOTTOM)
    fg_scale = min(width / img.width, (area_bottom - area_top) / img.height)
    fg = img.resize((round(img.width * fg_scale), round(img.height * fg_scale)), Image.LANCZOS)
    top_y = area_top + ((area_bottom - area_top) - fg.height) // 2
    bg.paste(fg, ((width - fg.width) // 2, top_y))
    bg.save(path, quality=92)
    return "contain"
