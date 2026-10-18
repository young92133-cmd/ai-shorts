"""한글 글꼴 찾기 — 쇼츠 카드·대체 이미지·비교 화면·캐러셀이 함께 쓴다."""
from __future__ import annotations

from typing import Any

from PIL import ImageFont

BOLD = ("malgunbd.ttf", "malgun.ttf", "NanumGothicBold.ttf", "AppleSDGothicNeo.ttc", "arialbd.ttf", "arial.ttf")
REGULAR = ("malgun.ttf", "NanumGothic.ttf", "AppleSDGothicNeo.ttc", "arial.ttf")
_CACHE: dict[tuple[int, bool], Any] = {}


def font(size: int, bold: bool = True):
    """크기별로 한 번만 찾아 캐시한다. 아무 글꼴도 없으면 Pillow 기본 글꼴."""
    key = (size, bold)
    if key not in _CACHE:
        for name in (BOLD if bold else REGULAR):
            try:
                _CACHE[key] = ImageFont.truetype(name, size)
                break
            except OSError:
                continue
        else:
            _CACHE[key] = ImageFont.load_default()
    return _CACHE[key]
