"""이미지 provider 공통 인터페이스 + 실패 시 대체 카드 생성."""
from __future__ import annotations

import colorsys
import hashlib
import textwrap
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


class ImageProvider(ABC):
    name: str = "base"
    concurrency: int = 3  # 동시에 보낼 요청 수 (무료 API 는 1)

    @abstractmethod
    async def generate(self, prompt: str, out_path: Path, width: int, height: int) -> None:
        """prompt로 이미지를 만들어 out_path에 저장. 실패 시 예외."""


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("malgunbd.ttf", "malgun.ttf", "NanumGothicBold.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_fallback_card(text: str, out_path: Path, width: int, height: int, seed: str = "") -> None:
    """이미지 생성이 실패했을 때 쓰는 그라데이션 + 키워드 카드."""
    h = int(hashlib.md5((seed or text).encode()).hexdigest()[:4], 16) / 65535
    r1, g1, b1 = (int(c * 255) for c in colorsys.hsv_to_rgb(h, 0.55, 0.45))
    r2, g2, b2 = (int(c * 255) for c in colorsys.hsv_to_rgb((h + 0.08) % 1, 0.65, 0.20))
    img = Image.new("RGB", (width, height))
    px = img.load()
    for y in range(height):
        t = y / height
        row = (int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t))
        for x in range(width):
            px[x, y] = row
    if text:
        draw = ImageDraw.Draw(img)
        font = _font(int(width * 0.085))
        lines = textwrap.wrap(text, width=10) or [text]
        line_h = int(font.size * 1.3)
        y = height // 2 - line_h * len(lines) // 2
        for line in lines:
            w = draw.textlength(line, font=font)
            draw.text(((width - w) / 2, y), line, font=font, fill="white", stroke_width=4, stroke_fill="black")
            y += line_h
    img.save(out_path, quality=92)


def resize_cover(path: Path, width: int, height: int) -> None:
    """생성된 이미지를 정확히 width x height 로 맞춘다 (중앙 크롭)."""
    img = Image.open(path).convert("RGB")
    scale = max(width / img.width, height / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - width) // 2, (img.height - height) // 2
    img.crop((left, top, left + width, top + height)).save(path, quality=92)
