"""코드로 그리는 장면 배경 (무료). 원근감 있는 실내·거리와 장소별 소품, 시간대 하늘.

배경 그림(사용자 등록·라이브러리)이 없을 때 렌더러가 쓴다. 인물·글자는 그리지 않는다.
1점 투시: 소실점은 화면 가운데 위쪽. 뒤 벽 → 바닥·천장·옆벽 → 소품 순서로 그린다.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

LINE = (110, 84, 66)          # 따뜻한 갈색 외곽선 (햄토리치 그림체와 맞춤)
SCENES = {
    "mart": ("마트", "장보기", "계산대", "장바구니", "편의점", "시장"),
    "bank": ("은행", "창구", "대출 상담", "ATM"),
    "realestate": ("부동산", "중개", "공인중개사"),
    "office": ("회사", "사무실", "직장", "야근", "회의"),
    "cafe": ("카페", "커피"),
    "subway": ("지하철", "출근길", "버스"),
    "news": ("뉴스", "스튜디오", "발표", "브리핑"),
    "apartment": ("아파트", "단지", "분양", "청약"),
    "street": ("거리", "골목", "동네", "퇴근길", "밖", "길"),
    "living": ("거실", "소파", "집 거실"),
    "room": ("원룸", "자취방", "방", "집", "책상"),
}
SKY = {"day": ((150, 205, 250), (225, 242, 255)), "sunset": ((255, 150, 95), (255, 214, 160)),
       "night": ((24, 34, 74), (70, 80, 140)), "gloomy": ((120, 130, 150), (175, 182, 196))}


def scene_type(background: str) -> str:
    text = background or ""
    for kind, words in SCENES.items():
        if any(w in text for w in words):
            return kind
    return "room"


def time_of(background: str, mood: str = "") -> str:
    text = background or ""
    if mood in ("night", "sunset", "gloomy"):
        return mood
    if any(w in text for w in ("밤", "야근", "새벽", "야경")):
        return "night"
    if any(w in text for w in ("노을", "퇴근길", "저녁")):
        return "sunset"
    if any(w in text for w in ("비", "우울")):
        return "gloomy"
    return "day"


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def _grad(d: ImageDraw.ImageDraw, box, top, bottom):
    x0, y0, x1, y1 = [int(v) for v in box]
    for y in range(y0, y1):
        t = (y - y0) / max(1, y1 - y0)
        d.line([(x0, y), (x1, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))


class Room:
    """1점 투시 방. 뒤 벽 사각형과 화면 모서리를 이어 바닥·천장·옆벽을 만든다."""

    def __init__(self, w: int, h: int, wall, floor, *, back=(0.20, 0.10, 0.80, 0.60)):
        self.w, self.h = w, h
        self.bx0, self.by0, self.bx1, self.by1 = w * back[0], h * back[1], w * back[2], h * back[3]
        self.wall, self.floor = wall, floor
        self.img = Image.new("RGB", (w, h), wall)
        self.d = ImageDraw.Draw(self.img)

    def vp(self):
        return ((self.bx0 + self.bx1) / 2, (self.by0 + self.by1) / 2)

    def shell(self, *, floor_lines: str = "planks", ceiling=None):
        w, h, d = self.w, self.h, self.d
        side = _shade(self.wall, 0.88)
        d.polygon([(0, 0), (self.bx0, self.by0), (self.bx0, self.by1), (0, h)], fill=side)
        d.polygon([(w, 0), (self.bx1, self.by0), (self.bx1, self.by1), (w, h)], fill=side)
        d.polygon([(0, 0), (w, 0), (self.bx1, self.by0), (self.bx0, self.by0)], fill=ceiling or _shade(self.wall, 0.95))
        d.polygon([(0, h), (self.bx0, self.by1), (self.bx1, self.by1), (w, h)], fill=self.floor)
        fl = _shade(self.floor, 0.86)
        if floor_lines == "planks":
            for k in range(1, 10):
                t = k / 10
                d.line([(self.bx0 + (self.bx1 - self.bx0) * t, self.by1), (w * t, h)], fill=fl, width=3)
        elif floor_lines == "tiles":
            for k in range(1, 8):
                t = k / 8
                d.line([(self.bx0 + (self.bx1 - self.bx0) * t, self.by1), (w * t, h)], fill=fl, width=3)
            for k in range(1, 6):
                t = (k / 6) ** 1.8
                y = self.by1 + (h - self.by1) * t
                xl = self.bx0 * (1 - t)
                d.line([(xl, y), (w - xl, y)], fill=fl, width=3)
        for a, b in (((0, 0), (self.bx0, self.by0)), ((w, 0), (self.bx1, self.by0)),
                     ((0, h), (self.bx0, self.by1)), ((w, h), (self.bx1, self.by1))):
            d.line([a, b], fill=_shade(self.wall, 0.7), width=4)
        d.rectangle([self.bx0, self.by0, self.bx1, self.by1], outline=_shade(self.wall, 0.7), width=4)
        # 걸레받이
        d.line([(self.bx0, self.by1 - 6), (self.bx1, self.by1 - 6)], fill=_shade(self.wall, 0.78), width=8)

    def window(self, box, time: str, *, city=True):
        d = self.d
        x0, y0, x1, y1 = box
        top, bottom = SKY.get(time, SKY["day"])
        _grad(d, box, top, bottom)
        if city:
            rnd = random.Random(int(x0 + y0))
            bx = x0
            while bx < x1:
                bw = (x1 - x0) * rnd.uniform(0.12, 0.22)
                bh = (y1 - y0) * rnd.uniform(0.25, 0.6)
                col = (40, 48, 90) if time == "night" else (190, 205, 225) if time == "day" else (150, 110, 120)
                d.rectangle([bx, y1 - bh, min(x1, bx + bw), y1], fill=col)
                if time == "night":
                    for _ in range(4):
                        wx = rnd.uniform(bx + 4, min(x1, bx + bw) - 8)
                        wy = rnd.uniform(y1 - bh + 4, y1 - 8)
                        d.rectangle([wx, wy, wx + 6, wy + 8], fill=(255, 220, 120))
                bx += bw + 3
        d.rectangle(box, outline=(250, 250, 250), width=12)
        d.line([((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1)], fill=(250, 250, 250), width=8)
        d.rectangle([x0 - 6, y0 - 6, x1 + 6, y1 + 6], outline=LINE, width=3)

    def finish(self, time: str) -> Image.Image:
        if time == "night":
            light = Image.new("L", self.img.size, 0)
            ImageDraw.Draw(light).ellipse([self.w * 0.15, self.h * 0.2, self.w * 0.85, self.h * 1.1], fill=255)
            light = light.filter(ImageFilter.GaussianBlur(min(self.w, self.h) // 6))
            dark = Image.blend(self.img, Image.new("RGB", self.img.size, (30, 36, 70)), 0.45)
            self.img = Image.composite(self.img, dark, light)
        return self.img


def _box3d(d, x0, y0, x1, y1, depth, color):
    """정면 사각형 + 윗면 (가구)."""
    top = _shade(color, 1.12)
    d.polygon([(x0, y0), (x1, y0), (x1 - depth, y0 - depth * 0.6), (x0 + depth, y0 - depth * 0.6)], fill=top, outline=LINE)
    d.rectangle([x0, y0, x1, y1], fill=color, outline=LINE, width=3)


def _shelves(d, x0, y0, x1, y1, rows, rnd):
    d.rectangle([x0, y0, x1, y1], fill=(236, 226, 210), outline=LINE, width=3)
    palette = [(235, 90, 80), (250, 190, 60), (90, 170, 220), (120, 190, 110), (240, 150, 190), (255, 240, 200)]
    for r in range(rows):
        sy = y0 + (y1 - y0) * (r + 1) / rows
        d.line([(x0, sy), (x1, sy)], fill=LINE, width=3)
        x = x0 + 6
        while x < x1 - 20:
            kind = rnd.random()
            bh = (y1 - y0) / rows * rnd.uniform(0.35, 0.62)
            col = rnd.choice(palette)
            if kind < 0.4:                                   # 상자 (넓적)
                bw = rnd.uniform(26, 44)
                d.rectangle([x, sy - bh, min(x1 - 6, x + bw), sy - 3], fill=col, outline=_shade(LINE, 1.2))
                d.rectangle([x + 5, sy - bh * 0.7, min(x1 - 10, x + bw - 5), sy - bh * 0.45], fill=(255, 255, 255))
            elif kind < 0.75:                                # 병
                bw = rnd.uniform(14, 20)
                d.rounded_rectangle([x, sy - bh, x + bw, sy - 3], radius=6, fill=col, outline=_shade(LINE, 1.2))
                d.rectangle([x + bw * 0.3, sy - bh - 8, x + bw * 0.7, sy - bh], fill=_shade(col, 0.7))
            else:                                            # 캔 쌓기
                bw = rnd.uniform(18, 24)
                for k in range(2):
                    cy = sy - 3 - k * bw
                    d.ellipse([x, cy - bw, x + bw, cy], fill=col, outline=_shade(LINE, 1.2))
            x += bw + 6
        # 가격표 띠
        d.rectangle([x0, sy - 2, x1, sy + 6], fill=(255, 230, 90))


def draw_scene(size: tuple[int, int], background: str = "", *, mood: str = "", seed: str = "") -> Image.Image:
    w, h = size
    kind, time = scene_type(background), time_of(background, mood)
    rnd = random.Random(f"{background}{seed}")
    if kind in ("street", "apartment"):
        return _street(w, h, time, apartments=kind == "apartment", rnd=rnd)
    if kind == "subway":
        return _subway(w, h, time)
    walls = {"room": ((246, 232, 210), (214, 180, 140)), "living": ((240, 228, 214), (196, 160, 122)),
             "mart": ((248, 246, 238), (226, 226, 222)), "bank": ((232, 238, 244), (210, 214, 220)),
             "realestate": ((244, 236, 222), (200, 170, 130)), "office": ((236, 240, 244), (196, 204, 214)),
             "cafe": ((236, 220, 196), (170, 128, 92)), "news": ((40, 60, 110), (30, 40, 70))}
    wall, floor = walls.get(kind, walls["room"])
    room = Room(w, h, wall, floor)
    room.shell(floor_lines="tiles" if kind in ("mart", "bank", "office", "news") else "planks")
    d = room.d
    bx0, by0, bx1, by1 = room.bx0, room.by0, room.bx1, room.by1
    bw, bh = bx1 - bx0, by1 - by0
    if kind in ("room", "living"):
        room.window((bx0 + bw * 0.08, by0 + bh * 0.12, bx0 + bw * 0.48, by0 + bh * 0.62), time)
        if kind == "room":
            _box3d(d, bx0 + bw * 0.55, by1 - bh * 0.30, bx1 - bw * 0.02, by1 + 4, 14, (180, 140, 100))     # 책상
            d.rectangle([bx0 + bw * 0.62, by1 - bh * 0.55, bx0 + bw * 0.86, by1 - bh * 0.34], fill=(60, 70, 90), outline=LINE, width=3)
            _box3d(d, -10, h * 0.74, w * 0.26, h * 0.92, 22, (170, 200, 230))                                  # 침대
            d.rectangle([0, h * 0.70, w * 0.10, h * 0.74], fill=(250, 250, 250), outline=LINE, width=3)      # 베개
            lx = bx1 - bw * 0.08
            d.line([(lx, by1 - bh * 0.30), (lx, by1 - bh * 0.62)], fill=LINE, width=4)
            d.polygon([(lx - 22, by1 - bh * 0.62), (lx + 22, by1 - bh * 0.62), (lx + 12, by1 - bh * 0.76), (lx - 12, by1 - bh * 0.76)],
                      fill=(255, 220, 140), outline=LINE)
        else:
            _box3d(d, bx0 + bw * 0.52, by1 - bh * 0.24, bx1 + w * 0.05, by1 + h * 0.05, 18, (120, 150, 190))    # 소파
            d.rectangle([bx0 + bw * 0.58, by0 + bh * 0.25, bx0 + bw * 0.95, by0 + bh * 0.55], fill=(50, 55, 70), outline=LINE, width=3)
        px = w * 0.86 if kind == "room" else w * 0.05
        d.ellipse([px, h * 0.60, px + w * 0.12, h * 0.68], fill=(110, 170, 110), outline=LINE, width=3)           # 화분
        d.rectangle([px + w * 0.03, h * 0.67, px + w * 0.09, h * 0.76], fill=(200, 130, 90), outline=LINE, width=3)
    elif kind == "mart":
        for k in range(3):
            sx0 = bx0 + bw * (0.02 + k * 0.33)
            _shelves(d, sx0, by0 + bh * 0.08, sx0 + bw * 0.30, by1 - 4, 4, rnd)
        _shelves(d, 0, h * 0.08, w * 0.17, h * 0.72, 5, rnd)
        _shelves(d, w * 0.83, h * 0.08, w, h * 0.72, 5, rnd)
        _box3d(d, w * 0.06, h * 0.80, w * 0.58, h * 1.02, 26, (190, 196, 205))                                    # 계산대
        d.rectangle([w * 0.10, h * 0.83, w * 0.54, h * 0.86], fill=(60, 60, 70))
    elif kind == "bank":
        for k in range(3):
            cx0 = bx0 + bw * (0.04 + k * 0.32)
            d.rectangle([cx0, by0 + bh * 0.15, cx0 + bw * 0.28, by0 + bh * 0.42], fill=(210, 230, 245), outline=LINE, width=3)  # 창구 칸막이
            d.rectangle([cx0 + bw * 0.08, by0 + bh * 0.02, cx0 + bw * 0.20, by0 + bh * 0.12], fill=(30, 40, 60), outline=LINE)   # 번호 표시
            d.rectangle([cx0 + bw * 0.10, by0 + bh * 0.04, cx0 + bw * 0.18, by0 + bh * 0.10], fill=(230, 60, 60))
        _box3d(d, bx0 - w * 0.05, by1 - bh * 0.42, bx1 + w * 0.05, by1 + h * 0.10, 22, (150, 120, 95))
    elif kind == "realestate":
        for r in range(2):
            for c in range(4):
                x = bx0 + bw * (0.06 + c * 0.23)
                y = by0 + bh * (0.08 + r * 0.30)
                d.rectangle([x, y, x + bw * 0.19, y + bh * 0.24], fill=(255, 255, 250), outline=LINE, width=3)
                hx, hy, s = x + bw * 0.095, y + bh * 0.14, bw * 0.05      # 집 그림 카드
                d.polygon([(hx - s, hy), (hx, hy - s * 0.9), (hx + s, hy)], fill=(230, 110, 90), outline=LINE)
                d.rectangle([hx - s * 0.7, hy, hx + s * 0.7, hy + s * 0.9], fill=(250, 220, 170), outline=LINE)
        _box3d(d, bx0, by1 - bh * 0.24, bx1, by1 + h * 0.08, 20, (170, 130, 95))
    elif kind == "office":
        room.window((bx0 + bw * 0.05, by0 + bh * 0.08, bx1 - bw * 0.05, by0 + bh * 0.45), time)
        for k in range(3):
            x = bx0 + bw * (0.02 + k * 0.33)
            _box3d(d, x, by1 - bh * 0.22, x + bw * 0.30, by1 + 4, 10, (200, 205, 212))
            d.rectangle([x + bw * 0.07, by1 - bh * 0.48, x + bw * 0.23, by1 - bh * 0.24], fill=(50, 60, 80), outline=LINE, width=3)
            if time == "night" and k == 1:
                d.rectangle([x + bw * 0.08, by1 - bh * 0.46, x + bw * 0.22, by1 - bh * 0.26], fill=(150, 200, 255))
        _box3d(d, w * 0.70, h * 0.74, w * 1.05, h * 1.02, 24, (205, 210, 216))
    elif kind == "cafe":
        room.window((bx0 + bw * 0.05, by0 + bh * 0.10, bx1 - bw * 0.05, by0 + bh * 0.60), time, city=False)
        for k in range(3):
            lx = bx0 + bw * (0.2 + k * 0.3)
            d.line([(lx, 0), (lx, h * 0.18)], fill=LINE, width=3)
            d.pieslice([lx - 30, h * 0.16, lx + 30, h * 0.24], 180, 360, fill=(250, 200, 100), outline=LINE)
        for x in (w * 0.08, w * 0.62):
            d.ellipse([x, h * 0.76, x + w * 0.30, h * 0.84], fill=(170, 120, 80), outline=LINE, width=3)
            d.ellipse([x + w * 0.12, h * 0.72, x + w * 0.17, h * 0.77], fill=(255, 255, 255), outline=LINE, width=2)
    elif kind == "news":
        for k in range(2):
            x = bx0 + bw * (0.05 + k * 0.48)
            d.rectangle([x, by0 + bh * 0.08, x + bw * 0.42, by0 + bh * 0.62], fill=(70, 120, 200), outline=(180, 210, 255), width=5)
            pts = [(x + bw * (0.04 + i * 0.07), by0 + bh * (0.50 - 0.05 * ((i * 7) % 5))) for i in range(6)]
            d.line(pts, fill=(255, 220, 80), width=6)
        _box3d(d, w * 0.10, h * 0.76, w * 0.90, h * 1.02, 26, (230, 235, 245))
    return room.finish(time)


def _street(w: int, h: int, time: str, *, apartments: bool, rnd: random.Random) -> Image.Image:
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    top, bottom = SKY.get(time, SKY["day"])
    horizon = h * 0.52
    _grad(d, (0, 0, w, horizon + 2), top, bottom)
    vx = w * 0.5
    # 길 (원근)
    road = (150, 150, 158) if time != "night" else (60, 62, 80)
    walk = (210, 200, 185) if time != "night" else (90, 88, 100)
    d.rectangle([0, horizon, w, h], fill=walk)          # 보도·땅 (건물 아래가 비지 않게)
    d.polygon([(0, h), (vx - w * 0.04, horizon), (vx + w * 0.04, horizon), (w, h)], fill=_shade(walk, 1.05))
    d.polygon([(w * 0.18, h), (vx - w * 0.02, horizon), (vx + w * 0.02, horizon), (w * 0.82, h)], fill=road)
    for k in range(6):                                    # 중앙선 점선
        t0, t1 = (k / 6) ** 1.6, ((k + 0.5) / 6) ** 1.6
        d.line([(vx, horizon + (h - horizon) * t0), (vx, horizon + (h - horizon) * t1)], fill=(250, 220, 90), width=int(3 + 8 * t1))
    # 양쪽 건물 (원근 크기)
    for side in (-1, 1):
        x_edge = 0 if side < 0 else w
        for k in range(5):
            t = k / 5
            near_h = h * (0.75 if apartments else 0.55) * (1 - t * 0.7)
            x_far = vx + side * w * (0.06 + 0.44 * (1 - t))
            x_near = vx + side * w * (0.06 + 0.44 * (1 - t - 0.2))
            xa, xb = sorted((x_far, x_near))
            base = horizon + (h - horizon) * (0.25 * (1 - t))
            col = rnd.choice([(236, 214, 190), (214, 196, 214), (200, 214, 230), (230, 200, 170)])
            if time == "night":
                col = _shade(col, 0.45)
            d.rectangle([xa, base - near_h, xb, base], fill=col, outline=LINE, width=3)
            for wy in range(int(base - near_h + 14), int(base - 20), 34):
                for wx in range(int(xa + 10), int(xb - 16), 30):
                    lit = time == "night" and rnd.random() < 0.6
                    d.rectangle([wx, wy, wx + 14, wy + 18], fill=(255, 214, 110) if lit else _shade(col, 0.8))
    # 가로등
    for side in (-1, 1):
        px = vx + side * w * 0.36
        d.line([(px, h * 0.95), (px, h * 0.40)], fill=(70, 70, 80), width=7)
        d.ellipse([px - 16, h * 0.38, px + 16, h * 0.43], fill=(255, 230, 150) if time in ("night", "sunset") else (240, 240, 240),
                  outline=LINE, width=3)
    return img


def _subway(w: int, h: int, time: str) -> Image.Image:
    room = Room(w, h, (226, 232, 236), (150, 156, 166), back=(0.30, 0.18, 0.70, 0.58))
    room.shell(floor_lines="tiles", ceiling=(240, 244, 246))
    d = room.d
    for side in (-1, 1):                                    # 창문 띠와 좌석
        for k in range(3):
            t0, t1 = k / 3, (k + 0.8) / 3
            def pt(t, y):
                x_edge = 0 if side < 0 else w
                xb = room.bx0 if side < 0 else room.bx1
                return (x_edge + (xb - x_edge) * t, y * (1 - t) + (room.by0 + (room.by1 - room.by0) * (y / h)) * t)
            a, b = pt(t0, h * 0.18), pt(t1, h * 0.18)
            c, e = pt(t1, h * 0.45), pt(t0, h * 0.45)
            d.polygon([a, b, c, e], fill=(110, 170, 220) if time != "night" else (40, 50, 90), outline=LINE)
        seat = [(0 if side < 0 else w, h * 0.80), (room.bx0 if side < 0 else room.bx1, room.by1 - 20),
                (room.bx0 if side < 0 else room.bx1, room.by1 - 4), (0 if side < 0 else w, h * 0.92)]
        d.polygon(seat, fill=(90, 130, 200), outline=LINE)
    for k in range(3):                                       # 손잡이 봉
        x = w * (0.25 + k * 0.25)
        d.line([(x, 0), (x, h)], fill=(200, 200, 210), width=10)
    return room.finish(time)
