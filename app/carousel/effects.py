"""만화 연출 효과와 분위기 조명 (앱이 직접 그림, 무료).

벤치마크(2026-10-08): 인기 인스타툰은 집중선·식은땀·분노 표시·반짝이·색 조명으로 감정을 키운다.
효과는 패널 상자 안에만 그린다. 글자는 쓰지 않는다(느낌표처럼 기호 모양만).
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

MOODS = {   # 패널 배경에 덧입히는 색 (색, 세기)
    "night": ((40, 60, 140), 0.28),
    "sunset": ((255, 140, 60), 0.22),
    "gloomy": ((90, 100, 130), 0.35),
    "crisis": ((220, 40, 40), 0.22),
    "bright": ((255, 240, 200), 0.12),
}
EMOTION_MOOD = {"sad": "gloomy", "angry": "crisis"}


def mood_for(background: str, emotion: str) -> str:
    text = background or ""
    if any(w in text for w in ("밤", "야근", "새벽", "야경")):
        return "night"
    if any(w in text for w in ("노을", "퇴근길", "저녁")):
        return "sunset"
    return EMOTION_MOOD.get(emotion, "")


def apply_mood(img: Image.Image, mood: str) -> Image.Image:
    if mood not in MOODS:
        return img
    color, k = MOODS[mood]
    tint = Image.new("RGB", img.size, color)
    out = Image.blend(img.convert("RGB"), tint, k)
    if mood in ("crisis", "gloomy"):   # 가장자리를 어둡게 (비네트)
        w, h = out.size
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).ellipse([-w * 0.25, -h * 0.2, w * 1.25, h * 1.2], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) // 8))
        dark = Image.new("RGB", (w, h), tuple(int(c * 0.35) for c in color))
        out = Image.composite(out, dark, mask)
    return out


def _star(d, cx, cy, r, color):
    pts = []
    for k in range(8):
        rr = r if k % 2 == 0 else r * 0.28
        a = -math.pi / 2 + k * math.pi / 4
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=color)


def _drop(d, cx, cy, r, fill, line):
    d.polygon([(cx, cy - r * 1.8), (cx + r, cy), (cx - r, cy)], fill=fill)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=line, width=max(2, int(r * 0.18)))


def draw_effects(canvas: Image.Image, box, head: tuple[float, float], emotion: str, *, seed: str = "") -> None:
    """캐릭터 머리 주변에 감정 기호를 그린다. 패널 밖으로 나가지 않게 잘라 붙인다."""
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    hx, hy = head[0] - x0, head[1] - y0
    u = min(w, h) / 20                     # 효과 크기 단위
    rnd = random.Random(seed or emotion)
    ink = (40, 30, 30, 255)
    if emotion in ("happy", "confident"):
        for k in range(4):
            a = -math.pi * (0.15 + 0.7 * k / 3)
            r = u * rnd.uniform(4.5, 6.5)
            _star(d, hx + r * math.cos(a) * 1.3, hy + r * math.sin(a), u * rnd.uniform(0.55, 0.9), (255, 214, 64, 235))
    elif emotion == "surprised":
        for k in range(3):                 # 머리 위 놀람 선 (기호)
            a = -math.pi / 2 + (k - 1) * 0.45
            sx, sy = hx + u * 4.2 * math.cos(a), hy - u * 1.5 + u * 4.2 * math.sin(a)
            d.line([(sx, sy), (sx + u * 1.6 * math.cos(a), sy + u * 1.6 * math.sin(a))], fill=(255, 196, 0, 255), width=int(u * 0.45))
    elif emotion == "worried":
        _drop(d, hx + u * 3.6, hy - u * 1.6, u * 0.75, (150, 205, 255, 240), (60, 110, 170, 255))
        _drop(d, hx + u * 4.6, hy - u * 0.2, u * 0.5, (150, 205, 255, 240), (60, 110, 170, 255))
        for k in range(5):                 # 머리 위 그늘 세로줄
            x = hx - u * 2.2 + k * u * 1.1
            d.line([(x, hy - u * 5.5), (x, hy - u * 3.8)], fill=(80, 80, 120, 150), width=int(u * 0.22))
    elif emotion == "angry":
        cx, cy, r = hx + u * 3.4, hy - u * 3.0, u * 1.1     # 분노 표시 (네 갈래 혈관)
        for a in (math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4):
            px, py = cx + r * 0.55 * math.cos(a), cy + r * 0.55 * math.sin(a)
            d.arc([px - r * 0.55, py - r * 0.55, px + r * 0.55, py + r * 0.55], math.degrees(a) + 90, math.degrees(a) + 270,
                  fill=(225, 40, 40, 255), width=int(u * 0.4))
    elif emotion == "sad":
        for k in range(14):                # 비 같은 사선
            x, y = rnd.uniform(0, w), rnd.uniform(0, h * 0.6)
            d.line([(x, y), (x - u * 0.6, y + u * 2.2)], fill=(120, 150, 210, 120), width=int(u * 0.18))
    elif emotion == "thinking":
        for k, r in enumerate((0.35, 0.5, 0.7)):
            cx, cy = hx + u * (2.6 + k * 1.2), hy - u * (3.0 + k * 1.1)
            d.ellipse([cx - u * r, cy - u * r, cx + u * r, cy + u * r], fill=(255, 255, 255, 235), outline=ink, width=max(2, int(u * 0.15)))
    canvas.paste(layer, (x0, y0), layer)


def speed_lines(size: tuple[int, int], center: tuple[float, float], color=(0, 0, 0), alpha=60, count=56) -> Image.Image:
    """중심을 향하는 집중선 (투명 레이어)."""
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    rnd = random.Random(count)
    for k in range(count):
        a = k / count * 2 * math.pi + rnd.uniform(-0.03, 0.03)
        r0 = min(w, h) * rnd.uniform(0.32, 0.45)
        r1 = max(w, h) * 1.2
        da = rnd.uniform(0.008, 0.02)
        d.polygon([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + r1 * math.cos(a - da), cy + r1 * math.sin(a - da)),
                   (cx + r1 * math.cos(a + da), cy + r1 * math.sin(a + da))], fill=(*color, alpha))
    return layer


def screentone(size: tuple[int, int], color=(0, 0, 0), alpha=28, step=14) -> Image.Image:
    """만화 망점 (투명 레이어)."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(0, size[1], step):
        for x in range((y // step % 2) * step // 2, size[0], step):
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(*color, alpha))
    return layer
