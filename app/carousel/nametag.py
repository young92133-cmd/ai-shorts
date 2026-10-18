"""의인화 이름표 캐릭터 — 물가·금리·월급·한국은행 같은 경제 주체를 단순한 캐릭터로 (앱이 직접 그림, 무료).

벤치마크(@basic_newsreader): 국가·기업을 머리 이름표가 붙은 캐릭터로 세워 대결 구도로 설명한다.
우리 표현: 몸 모양(콩·지폐·동전·카드, SHAPES) + 색 머리띠 이름표 + 감정 얼굴. 실존 인물 얼굴은 그리지 않는다.
컷에서는 character_id 를 'tag:물가' 처럼 쓴다.
"""
from __future__ import annotations

import hashlib
import math

from PIL import Image, ImageDraw

from .render import font

W, H, SS = 600, 780, 2
INK = (45, 35, 30, 255)
COLORS = {"물가": (226, 72, 60), "금리": (60, 77, 101), "월급": (76, 160, 110), "대출": (240, 140, 50),
          "집값": (140, 90, 190), "전세": (90, 140, 210), "월세": (230, 110, 140), "환율": (40, 150, 160),
          "한국은행": (40, 90, 170), "정부": (90, 90, 100), "세금": (170, 120, 60), "주식": (210, 60, 90),
          "잔액": (214, 160, 30), "통장": (214, 160, 30), "자동이체": (110, 90, 200), "카드값": (200, 70, 120),
          "카드": (200, 70, 120), "보험료": (40, 140, 150), "적금": (60, 130, 200), "보너스": (60, 170, 90)}
# 몸 모양: 같은 컷에 여러 경제 주체가 나와도 모양으로 구별되게 (2026-10-18). 없으면 기본 콩 모양
SHAPES = {"bill": ("월급", "급여", "보너스", "성과급", "용돈", "현금"),
          "coin": ("잔액", "통장", "저축", "적금", "예금", "동전", "이자"),
          "card": ("자동이체", "카드", "결제", "할부", "구독", "보험료", "관리비", "월세")}
TAG_PREFIX = "tag:"


def is_tag(char_id: str) -> bool:
    return (char_id or "").startswith(TAG_PREFIX)


def label_of(char_id: str) -> str:
    return (char_id or "")[len(TAG_PREFIX):].strip()[:6]


def color_for(label: str) -> tuple[int, int, int]:
    if label in COLORS:
        return COLORS[label]
    h = int(hashlib.md5(label.encode()).hexdigest()[:6], 16)
    return (60 + h % 160, 60 + (h >> 8) % 160, 60 + (h >> 16) % 160)


def shape_for(label: str) -> str:
    return next((k for k, words in SHAPES.items() if any(w in label for w in words)), "egg")


def _light(color, k: float = 0.78) -> tuple[int, int, int, int]:
    return (*(int(c + (255 - c) * k) for c in color), 255)


def _body(d, shape: str, color, s: int, lw: int) -> None:
    """몸통. 얼굴(y 400~500)·머리띠(y 205~315) 자리는 모든 모양에서 같다."""
    if shape == "bill":          # 지폐: 연한 색 직사각형 + 안쪽 테두리 + 모서리 원(₩ 자리)
        d.rounded_rectangle([105 * s, 150 * s, 495 * s, 712 * s], 26 * s, fill=_light(color), outline=INK, width=lw)
        d.rounded_rectangle([135 * s, 340 * s, 465 * s, 682 * s], 14 * s, outline=(*color, 255), width=4 * s)
        for cx, cy in ((170, 640), (430, 640)):
            d.ellipse([(cx - 22) * s, (cy - 22) * s, (cx + 22) * s, (cy + 22) * s], fill=(*color, 255), outline=INK, width=3 * s)
    elif shape == "coin":        # 동전: 금색 타원 + 테두리 고리 + 톱니 눈금
        d.ellipse([95 * s, 130 * s, 505 * s, 725 * s], fill=_light(color, 0.45), outline=INK, width=lw)
        d.ellipse([130 * s, 170 * s, 470 * s, 685 * s], outline=(*color, 255), width=6 * s)
        for k in range(18):
            a = k / 18 * 2 * math.pi
            cx, cy, rx, ry = 300, 427, 205, 297
            d.line([((cx + rx * 0.93 * math.cos(a)) * s, (cy + ry * 0.93 * math.sin(a)) * s),
                    ((cx + rx * math.cos(a)) * s, (cy + ry * math.sin(a)) * s)], fill=INK, width=3 * s)
    elif shape == "card":        # 카드: 둥근 사각형 + IC 칩 + 카드 번호 점
        d.rounded_rectangle([115 * s, 150 * s, 485 * s, 712 * s], 44 * s, fill=_light(color, 0.6), outline=INK, width=lw)
        d.rounded_rectangle([150 * s, 548 * s, 218 * s, 604 * s], 10 * s, fill=(236, 196, 90, 255), outline=INK, width=3 * s)
        for k in range(4):
            x = 260 + k * 52
            for j in range(3):
                d.ellipse([(x + j * 12) * s, 640 * s, (x + j * 12 + 8) * s, 648 * s], fill=INK)
    else:
        d.ellipse([110 * s, 140 * s, 490 * s, 720 * s], fill=(255, 253, 248, 255), outline=INK, width=lw)


def draw_tag_character(label: str, emotion: str = "neutral") -> Image.Image:
    """투명 배경 RGBA (600x780). 머리띠 이름표 글자는 렌더러 글꼴로 합성한다."""
    s = SS
    img = Image.new("RGBA", (W * s, H * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = color_for(label)
    lw = 7 * s
    # 다리·몸
    for x in (230, 370):
        d.rounded_rectangle([(x - 28) * s, 690 * s, (x + 28) * s, 760 * s], 20 * s, fill=(255, 255, 255, 255), outline=INK, width=lw)
    _body(d, shape_for(label), color, s, lw)
    # 팔
    arm_up = emotion in ("happy", "confident", "surprised", "angry")
    for side in (-1, 1):
        sx = 300 + side * 182
        ex = 300 + side * (235 if arm_up else 215)
        ey = 330 if arm_up else 560
        d.line([(sx * s, 470 * s), (ex * s, ey * s)], fill=INK, width=lw * 2)
        d.ellipse([(ex - 22) * s, (ey - 22) * s, (ex + 22) * s, (ey + 22) * s], fill=(255, 255, 255, 255), outline=INK, width=lw)
    # 머리띠 이름표
    d.rounded_rectangle([118 * s, 205 * s, 482 * s, 315 * s], 22 * s, fill=(*color, 255), outline=INK, width=lw)
    f = font(int((86 if len(label) <= 2 else 64 if len(label) <= 4 else 50) * s), bold=True)
    d.text((300 * s, 260 * s), label, font=f, fill=(255, 255, 255, 255), anchor="mm", stroke_width=3 * s, stroke_fill=INK)
    # 얼굴
    ey, lx, rx = 400, 240, 360
    if emotion == "happy":
        for x in (lx, rx):
            d.arc([(x - 26) * s, (ey - 18) * s, (x + 26) * s, (ey + 26) * s], 200, 340, fill=INK, width=lw)
    elif emotion == "angry":
        for x, k in ((lx, 1), (rx, -1)):
            d.line([((x - 30) * s, (ey - 34 - 12 * k) * s), ((x + 30) * s, (ey - 34 + 12 * k) * s)], fill=INK, width=lw)
            d.ellipse([(x - 13) * s, (ey - 10) * s, (x + 13) * s, (ey + 16) * s], fill=INK)
    else:
        r = 20 if emotion == "surprised" else 14
        for x in (lx, rx):
            d.ellipse([(x - r) * s, (ey - r) * s, (x + r) * s, (ey + r) * s], fill=INK)
    my = 480
    if emotion in ("happy", "confident"):
        d.chord([255 * s, (my - 30) * s, 345 * s, (my + 40) * s], 0, 180, fill=(225, 90, 90, 255), outline=INK, width=lw)
    elif emotion == "surprised":
        d.ellipse([280 * s, (my - 20) * s, 320 * s, (my + 30) * s], fill=(225, 90, 90, 255), outline=INK, width=lw)
    elif emotion in ("sad", "worried", "angry"):
        d.arc([260 * s, my * s, 340 * s, (my + 50) * s], 200, 340, fill=INK, width=lw)
    else:
        d.line([(270 * s, (my + 10) * s), (330 * s, (my + 10) * s)], fill=INK, width=lw)
    return img.resize((W, H), Image.LANCZOS)
