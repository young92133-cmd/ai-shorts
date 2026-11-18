"""AI 이미지 없이 앱이 직접 그리는 캐릭터(마스코트). 무료·오프라인이고 항상 같은 얼굴이 나온다.

Character Bible 의 mascot 색·머리 모양으로 그리고, 감정(눈·눈썹·입)과 자세(팔)만 바꾼다.
배경은 투명(RGBA). 2배 크기로 그린 뒤 줄여서 선을 부드럽게 한다.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

W, H = 600, 780          # 기준 좌표계
SS = 2                   # 슈퍼샘플링 배율
INK = (34, 28, 26, 255)
_INK = object()           # '그림체의 외곽선 색' 표시 (None 은 외곽선 없음)


def _rgb(value: str, default: str) -> tuple[int, int, int, int]:
    v = (value or default).lstrip("#")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), 255)


def _shade(c, k: float):
    return (int(c[0] * k), int(c[1] * k), int(c[2] * k), c[3])


class _Pen:
    """기준 좌표(600x780)로 그리면 슈퍼샘플 캔버스에 맞춰 그려 준다."""

    def __init__(self, img: Image.Image, ink=INK, scale: float = 1.0):
        self.d = ImageDraw.Draw(img)
        self.ink, self.scale = ink, scale

    def _w(self, width) -> int:
        return max(1, int(round(width * self.scale))) * SS

    def _c(self, color):
        return self.ink if color is _INK else color

    @staticmethod
    def _b(box):
        return [v * SS for v in box]

    def ellipse(self, box, fill=None, outline=_INK, width=5):
        outline = self._c(outline)
        self.d.ellipse(self._b(box), fill=fill, outline=outline, width=self._w(width) if outline else 0)

    def rect(self, box, r, fill=None, outline=_INK, width=5):
        outline = self._c(outline)
        self.d.rounded_rectangle(self._b(box), radius=r * SS, fill=fill, outline=outline, width=self._w(width) if outline else 0)

    def poly(self, pts, fill=None, outline=_INK, width=5):
        outline = self._c(outline)
        pts = [(x * SS, y * SS) for x, y in pts]
        self.d.polygon(pts, fill=fill)
        if outline:
            self.d.line(pts + [pts[0]], fill=outline, width=self._w(width), joint="curve")

    def line(self, pts, fill=_INK, width=5):
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=self._c(fill), width=self._w(width), joint="curve")

    def arc(self, box, start, end, fill=_INK, width=5):
        self.d.arc(self._b(box), start, end, fill=self._c(fill), width=self._w(width))

    def chord(self, box, start, end, fill=None, outline=_INK, width=5):
        outline = self._c(outline)
        self.d.chord(self._b(box), start, end, fill=fill, outline=outline, width=self._w(width) if outline else 0)

    def limb(self, a, b, color, width=46):
        """둥근 팔: 외곽선 굵은 선 위에 색 선."""
        edge = width + 10 * self.scale
        self.d.line([(a[0] * SS, a[1] * SS), (b[0] * SS, b[1] * SS)], fill=self.ink, width=int(round(edge * SS)))
        for p in (a, b):
            r = edge / 2
            self.d.ellipse(self._b([p[0] - r, p[1] - r, p[0] + r, p[1] + r]), fill=self.ink)
        self.d.line([(a[0] * SS, a[1] * SS), (b[0] * SS, b[1] * SS)], fill=color, width=width * SS)
        for p in (a, b):
            r = width / 2
            self.d.ellipse(self._b([p[0] - r, p[1] - r, p[0] + r, p[1] + r]), fill=color)


def _hand(p: _Pen, at, skin, r=26):
    p.ellipse([at[0] - r, at[1] - r, at[0] + r, at[1] + r], fill=skin)


def _arms(p: _Pen, pose: str, outfit, skin) -> None:
    """자세별 팔. 몸통(어깨 y≈520) 기준."""
    ls, rs = (205, 540), (395, 540)          # 왼/오른 어깨
    if pose in ("pointing", "explaining"):
        p.limb(ls, (185, 690), outfit)
        _hand(p, (185, 705), skin)
        p.limb(rs, (500, 430), outfit)
        _hand(p, (515, 415), skin)
        p.line([(530, 400), (565, 365)], width=14)
        p.line([(530, 400), (565, 365)], fill=skin, width=8)
    elif pose in ("waving", "greeting"):
        p.limb(ls, (185, 690), outfit)
        _hand(p, (185, 705), skin)
        p.limb(rs, (480, 400), outfit)
        _hand(p, (490, 375), skin, r=30)
        for k in range(3):
            p.arc([520 + k * 14, 330 - k * 10, 570 + k * 14, 380 - k * 10], 300, 30, width=4)
    elif pose in ("arms_crossed", "confident"):
        p.limb((215, 560), (390, 620), outfit)
        p.limb((385, 560), (210, 620), _shade(outfit, 0.92))
        _hand(p, (205, 615), skin, r=22)
        _hand(p, (395, 615), skin, r=22)
    elif pose in ("thinking", "chin"):
        p.limb(ls, (185, 690), outfit)
        _hand(p, (185, 705), skin)
        p.limb(rs, (400, 600), outfit)
        p.limb((400, 600), (345, 470), outfit)
        _hand(p, (340, 462), skin, r=24)
    elif pose in ("cheering", "celebrating", "both_hands_up"):
        p.limb(ls, (110, 400), outfit)
        _hand(p, (100, 380), skin, r=30)
        p.limb(rs, (490, 400), outfit)
        _hand(p, (500, 380), skin, r=30)
    elif pose in ("shrug", "confused"):
        p.limb(ls, (130, 560), outfit)
        _hand(p, (115, 540), skin)
        p.limb(rs, (470, 560), outfit)
        _hand(p, (485, 540), skin)
    else:  # standing
        p.limb(ls, (180, 690), outfit)
        _hand(p, (178, 705), skin)
        p.limb(rs, (420, 690), outfit)
        _hand(p, (422, 705), skin)


def _eyes(p: _Pen, emotion: str, eye, face: str = "cute") -> None:
    lx, rx, y = 238, 362, 330
    if face == "simple" and emotion not in ("happy", "confident"):
        r = 16 if emotion == "surprised" else 11
        for x in (lx, rx):
            p.ellipse([x - r, y - r, x + r, y + r], fill=eye, outline=None)
        return
    if emotion in ("happy", "confident"):
        for x in (lx, rx):
            p.arc([x - 26, y - 18, x + 26, y + 26], 200, 340, width=8)
        return
    if emotion == "angry":
        for x in (lx, rx):
            p.chord([x - 22, y - 16, x + 22, y + 28], 0, 180, fill=eye, outline=None)
        return
    if emotion == "sad":
        for x in (lx, rx):
            p.chord([x - 20, y - 20, x + 20, y + 26], 10, 170, fill=eye, outline=None)
        p.poly([(rx + 18, y + 22), (rx + 28, y + 52), (rx + 8, y + 52)], fill=(120, 190, 255, 255), outline=None)
        return
    big = emotion == "surprised"
    rw, rh = (24, 30) if big else (19, 26)
    for x in (lx, rx):
        if big:
            p.ellipse([x - rw - 6, y - rh - 6, x + rw + 6, y + rh + 6], fill=(255, 255, 255, 255), width=4)
        p.ellipse([x - rw, y - rh, x + rw, y + rh], fill=eye, outline=None)
        p.ellipse([x - rw * 0.15 - 8, y - rh * 0.55, x - rw * 0.15 + 4, y - rh * 0.55 + 12],
                  fill=(255, 255, 255, 255), outline=None)
    if emotion == "thinking":
        p.chord([rx - rw - 2, y - rh - 4, rx + rw + 2, y + rh + 4], 180, 360, fill=None, outline=None)


def _brows(p: _Pen, emotion: str, hair) -> None:
    lx, rx, y = 238, 362, 290
    color = _shade(hair, 0.8)
    shapes = {
        "angry": [((lx - 30, y - 10), (lx + 25, y + 10)), ((rx + 30, y - 10), (rx - 25, y + 10))],
        "worried": [((lx - 28, y + 6), (lx + 24, y - 10)), ((rx + 28, y + 6), (rx - 24, y - 10))],
        "sad": [((lx - 28, y + 8), (lx + 24, y - 8)), ((rx + 28, y + 8), (rx - 24, y - 8))],
        "surprised": [((lx - 26, y - 18), (lx + 24, y - 22)), ((rx - 24, y - 22), (rx + 26, y - 18))],
        "thinking": [((lx - 26, y), (lx + 24, y - 2)), ((rx - 24, y - 14), (rx + 26, y - 4))],
    }
    for a, b in shapes.get(emotion, [((lx - 26, y - 4), (lx + 24, y - 6)), ((rx - 24, y - 6), (rx + 26, y - 4))]):
        p.line([a, b], fill=color, width=8)


def _mouth(p: _Pen, emotion: str) -> None:
    cx, y = 300, 400
    red = (226, 92, 92, 255)
    if emotion == "happy":
        p.chord([cx - 34, y - 22, cx + 34, y + 30], 0, 180, fill=red)
    elif emotion == "surprised":
        p.ellipse([cx - 18, y - 12, cx + 18, y + 26], fill=red)
    elif emotion in ("sad", "angry"):
        p.arc([cx - 28, y, cx + 28, y + 34], 200, 340, width=7)
    elif emotion == "worried":
        p.line([(cx - 28, y + 10), (cx - 14, y + 2), (cx, y + 10), (cx + 14, y + 2), (cx + 28, y + 10)], width=6)
    elif emotion == "confident":
        p.arc([cx - 30, y - 22, cx + 30, y + 18], 20, 150, width=7)
    elif emotion == "thinking":
        p.line([(cx - 6, y + 8), (cx + 24, y + 4)], width=7)
    else:
        p.arc([cx - 24, y - 18, cx + 24, y + 14], 30, 150, width=7)


def _hair_back(p: _Pen, style: str, hair) -> None:
    if style == "long":
        p.rect([120, 170, 480, 650], 120, fill=hair)
    elif style in ("bob", "default"):
        p.rect([116, 150, 484, 500], 130, fill=hair)
    elif style == "ponytail":
        p.ellipse([400, 150, 540, 380], fill=hair)


def _hair_front(p: _Pen, style: str, hair) -> None:
    # 정수리 돔 + 앞머리. 앞머리 아랫선은 지그재그로 만화 느낌을 낸다.
    p.chord([128, 112, 472, 420], 180, 360, fill=hair)
    x0, x1 = 146, 454
    fringe = [(x0, 262)]
    for k in range(8):
        fringe += [(x0 + (x1 - x0) * (k + 0.5) / 8, 280 - (10 if k % 2 else 0)),
                   (x0 + (x1 - x0) * (k + 1) / 8, 266)]
    fringe += [(x1, 250), (x0, 250)]
    p.poly(fringe, fill=hair, outline=None)
    p.arc([128, 112, 472, 420], 180, 360, width=6)
    if style in ("bob", "long", "default"):
        p.rect([118, 250, 168, 470 if style == "bob" else 600], 24, fill=hair)
        p.rect([432, 250, 482, 470 if style == "bob" else 600], 24, fill=hair)
    p.arc([200, 130, 300, 200], 200, 300, fill=_shade(hair, 1.35), width=6)   # 머리 광택


def _curve(start, a, b, end):
    """고정 제어점의 곡선. 머리 실루엣을 감정·자세와 독립적으로 유지한다."""
    return [tuple((1-t)**3*start[k] + 3*(1-t)**2*t*a[k] + 3*(1-t)*t*t*b[k] + t**3*end[k]
                  for k in (0, 1)) for t in (i/24 for i in range(25))]


def _editorial(p: _Pen, mascot, emotion, pose, skin, hair, eye, outfit, detail, cheek):
    """사람형 고정 외형: 부드러운 옆가르마·작은 얼굴·봉제선·고정 색상. 기존 마스코트는 그대로."""
    # 머리 뒤와 의상은 표정에 따라 바뀌지 않는다.
    p.rect([146, 142, 454, 659], 128, fill=hair, width=4)
    p.poly(_curve((159, 340), (159, 470), (171, 615), (198, 648)) + [(160, 640)],
           fill=_shade(hair, 1.15), outline=None)
    p.rect([183, 500, 417, 815], 58, fill=outfit, width=4)
    p.poly([(191, 563), (211, 570), (218, 780), (190, 780)], fill=_shade(outfit, 0.95), outline=None)
    p.poly([(395, 563), (410, 550), (413, 780), (390, 780)], fill=_shade(outfit, 0.88), outline=None)
    p.rect([272, 425, 328, 516], 16, fill=skin, width=4)
    p.poly([(274, 435), (326, 435), (326, 471), (275, 453)], fill=_shade(skin, 0.92), outline=None)
    p.poly([(253, 503), (300, 550), (347, 503), (329, 540), (300, 566), (270, 540)], fill=detail, width=3)
    p.line([(300, 562), (300, 780)], fill=_shade(outfit, 0.80), width=3)
    for y in (610, 670, 730):
        p.ellipse([308, y-4, 316, y+4], fill=_shade(outfit, 0.70), outline=None)
    # 귀·얼굴·옆머리의 기준 좌표는 8개 감정과 모든 자세에서 고정.
    for x in (172, 428):
        p.ellipse([x-15, 306, x+15, 352], fill=skin, width=3)
        p.arc([x-8, 319, x+8, 343], 100, 270, fill=_shade(skin, 0.78), width=2)
    p.ellipse([172, 176, 428, 459], fill=skin, width=4)
    p.arc([179, 188, 424, 452], 15, 92, fill=_shade(skin, 0.90), width=7)
    fringe = (_curve((151, 289), (132, 144), (361, 89), (446, 242)) +
              _curve((446, 242), (394, 265), (339, 195), (300, 205)) +
              _curve((300, 205), (255, 273), (194, 239), (151, 289)))
    p.poly(fringe, fill=hair, width=4)
    p.poly(_curve((154, 268), (155, 401), (157, 543), (181, 591)) + [(183, 273)], fill=hair, width=3)
    p.poly(_curve((415, 248), (444, 361), (446, 544), (420, 610)) + [(409, 274)], fill=hair, width=3)
    p.line(_curve((186, 219), (214, 161), (285, 144), (348, 170)), fill=_shade(hair, 1.35), width=3)
    p.line(_curve((165, 306), (168, 424), (173, 492), (179, 527)), fill=_shade(hair, 1.28), width=2)
    p.rect([410, 269, 429, 278], 4, fill=_rgb(mascot.get("hairpin"), "#73A69B"), outline=None)
    for x in (212, 388):
        p.ellipse([x-19, 366, x+19, 379], fill=(*cheek[:3], 255), outline=None)
    _brows(p, emotion, hair)
    if emotion in ("neutral", "worried", "thinking", "surprised"):
        for x in (238, 362):
            h = 22 if emotion == "surprised" else 15
            p.ellipse([x-25, 330-h, x+25, 330+h], fill=detail, width=3)
            p.ellipse([x-9, 319, x+9, 342], fill=eye, outline=None)
            p.ellipse([x-4, 320, x+2, 326], fill=(255,255,255,255), outline=None)
            p.arc([x-26, 330-h-1, x+26, 330+h], 180, 355, width=4)
    else:
        _eyes(p, emotion, eye)
    p.line([(300, 363), (294, 376), (302, 379)], fill=_shade(skin, 0.77), width=2)
    _mouth(p, emotion)
    _arms(p, pose, outfit, skin)


def draw_mascot(mascot: dict, emotion: str = "neutral", pose: str = "standing", flip: bool = False) -> Image.Image:
    """투명 배경 RGBA 마스코트 (600x780)."""
    skin = _rgb(mascot.get("skin"), "#FCE0CC")
    hair = _rgb(mascot.get("hair"), "#5B3A29")
    eye = _rgb(mascot.get("eye"), "#2B2118")
    outfit = _rgb(mascot.get("outfit"), "#7FD1B9")
    detail = _rgb(mascot.get("outfit_detail"), "#FFFFFF")
    cheek = _rgb(mascot.get("cheek"), "#FF9AA2")
    style = mascot.get("hair_style", "bob")
    face = mascot.get("face", "cute")
    # 외곽선 색·굵기는 캐릭터(mascot.ink·line_scale) 또는 그림체(art_styles 의 mascot)가 정한다
    ink = _rgb(mascot["ink"], "#221C1A") if mascot.get("ink") else INK
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    p = _Pen(img, ink, float(mascot.get("line_scale", 1.0)))

    if face == "editorial":
        _editorial(p, mascot, emotion, pose, skin, hair, eye, outfit, detail, cheek)
        out = img.resize((W, H), Image.LANCZOS)
        return out.transpose(Image.FLIP_LEFT_RIGHT) if flip else out

    _hair_back(p, style, hair)
    # 몸통 (어깨 ~ 아래 끝까지, 하단은 컷 밖으로 잘린다고 가정)
    p.rect([180, 500, 420, 800], 70, fill=outfit)
    p.poly([(262, 500), (300, 560), (338, 500)], fill=detail)                      # 셔츠 깃
    p.line([(300, 560), (300, 780)], fill=_shade(outfit, 0.8), width=5)           # 가디건 앞선
    for y in (610, 670, 730):
        p.ellipse([306, y - 7, 320, y + 7], fill=_shade(outfit, 0.75), outline=None)
    p.rect([272, 450, 328, 515], 12, fill=skin)                                   # 목
    # 머리
    p.ellipse([140, 150, 460, 470], fill=skin)
    p.ellipse([128, 300, 162, 360], fill=skin)                                    # 귀
    p.ellipse([438, 300, 472, 360], fill=skin)
    _hair_front(p, style, hair)
    if style == "ponytail":
        p.ellipse([430, 150, 470, 200], fill=_rgb(mascot.get("hairpin"), "#FF6B6B"))
    # 볼 (단순한 얼굴은 생략)
    if face != "simple":
        blush = Image.new("RGBA", img.size, (0, 0, 0, 0))
        bp = _Pen(blush)
        for x in (205, 395):
            bp.ellipse([x - 30, 368, x + 30, 398], fill=(*cheek[:3], 140), outline=None)
        img.alpha_composite(blush)
    _brows(p, emotion, hair)
    _eyes(p, emotion, eye, face)
    _mouth(p, emotion)
    acc = mascot.get("accessory", "")
    if acc == "round_glasses":
        for x in (238, 362):
            p.ellipse([x - 44, 330 - 40, x + 44, 330 + 40], fill=None, width=6)
        p.line([(282, 326), (318, 326)], width=6)
    if mascot.get("hairpin") and style != "ponytail":
        c = _rgb(mascot["hairpin"], "#FFD43B")
        cx, cy, r = 390, 215, 26
        star = []
        import math
        for k in range(10):
            rr = r if k % 2 == 0 else r * 0.45
            a = -math.pi / 2 + k * math.pi / 5
            star.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        p.poly(star, fill=c, width=4)
    if emotion == "surprised":
        for k, (a, b) in enumerate((((120, 150), (90, 110)), ((150, 120), (130, 80)), ((480, 150), (510, 110)))):
            p.line([a, b], width=6)
    if emotion in ("worried", "thinking"):
        p.poly([(470, 250), (482, 280), (470, 292), (458, 280)], fill=(140, 200, 255, 255), width=3)  # 땀방울
    _arms(p, pose, outfit, skin)

    out = img.resize((W, H), Image.LANCZOS)
    return out.transpose(Image.FLIP_LEFT_RIGHT) if flip else out
