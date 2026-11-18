"""참고 스크린샷으로 '나만의 그림체'를 만든다 (무료, 내 PC 에서 계산).

그림을 베끼지 않는다: 참고 이미지에서 **색 구성·밝기·채도·선이 차지하는 정도**만 재서 기존 그림체 틀(art_styles)에 숫자로 옮긴다.
캐릭터 얼굴·포즈·구도 같은 그림 자체는 쓰지 않으므로 결과는 독자적인 스타일이다. 참고 이미지는 복사하지 않고 파일 이름만 기록한다.
"""
from __future__ import annotations

import colorsys
import re
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageFilter, ImageStat

from .templates import USER_STYLE_DIR, _load_styles, art_styles

ID_RE = re.compile(r"^[a-z0-9_]{2,40}$")


def _hex(c) -> str:
    return "#%02X%02X%02X" % tuple(int(v) for v in c[:3])


def _lum(c) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _sat(c) -> float:
    return colorsys.rgb_to_hsv(*(v / 255 for v in c[:3]))[1]


def analyze(images: list[Path]) -> dict[str, Any]:
    """여러 장의 대표 색(빈도순)과 전체 밝기·채도·선 비율."""
    counts: dict[tuple, int] = {}
    lum, sat, edge = [], [], []
    for path in images:
        im = Image.open(path).convert("RGB")
        im.thumbnail((480, 480))
        q = im.quantize(colors=10, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()
        for n, idx in q.getcolors():
            c = tuple(pal[idx * 3: idx * 3 + 3])
            counts[c] = counts.get(c, 0) + n
        hsv = im.convert("HSV")
        lum.append(ImageStat.Stat(im.convert("L")).mean[0] / 255)
        sat.append(ImageStat.Stat(hsv.getchannel("S")).mean[0] / 255)
        e = im.convert("L").filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 40 else 0)
        edge.append(ImageStat.Stat(e).mean[0] / 255)
    total = sum(counts.values()) or 1
    colors = sorted(counts.items(), key=lambda kv: -kv[1])
    return {"colors": [(c, n / total) for c, n in colors], "brightness": sum(lum) / len(lum),
            "saturation": sum(sat) / len(sat), "edges": sum(edge) / len(edge)}


def derive(stats: dict[str, Any]) -> dict[str, Any]:
    """측정값 → 그림체 설정. 색 역할: 바탕(가장 많은 밝은색) · 글자(가장 많은 어두운색) · 강조(가장 선명한 색)."""
    colors = [c for c, share in stats["colors"] if share >= 0.01] or [c for c, _ in stats["colors"]]
    light = [c for c in colors if _lum(c) >= 200] or sorted(colors, key=_lum, reverse=True)[:1]
    dark = [c for c in colors if _lum(c) <= 90] or sorted(colors, key=_lum)[:1]
    vivid = sorted((c for c in colors if 70 <= _lum(c) <= 220), key=_sat, reverse=True) or colors
    bg, ink, accent = light[0], dark[0], vivid[0]
    soft = next((c for c in vivid[1:] if _lum(c) > 150), tuple(int(v + (255 - v) * 0.6) for v in accent))
    b, s, e = stats["brightness"], stats["saturation"], stats["edges"]
    if b > 0.8 and e > 0.06:
        scene, effects = "lineart", "light"          # 밝은 바탕에 선이 많은 그림
    elif s < 0.22 and b > 0.7:
        scene, effects = "pastel", "light"           # 밝고 채도가 낮은 그림
    elif sum(share for _, share in stats["colors"][:4]) > 0.8:
        scene, effects = "flat", "none"              # 적은 색 면으로 된 그림
    else:
        scene, effects = "detailed", "full"
    line_scale = round(min(1.3, max(0.6, 0.6 + e * 6)), 2)
    return {"palette": {"bg": _hex(bg), "bg2": _hex(bg), "panel": "#FFFFFF", "ink": _hex(ink), "sub": _hex(ink),
                        "line": _hex(ink), "bubble_line": _hex(ink), "accent": _hex(accent), "highlight": _hex(soft),
                        "cover_bg": _hex(bg), "cover_bg2": _hex(soft), "cover_ink": _hex(ink), "band": _hex(soft)},
            "style": {"panel_border": max(2, round(5 * line_scale))},
            "art": {"scene": scene, "effects": effects, "bubble": "round", "bubble_line": round(line_scale * 0.8, 2),
                    "panel_radius": 16, "sticker": 8 if scene != "flat" else 0,
                    "mascot": {"ink": _hex(ink), "line_scale": line_scale}},
            "measured": {"brightness": round(b, 3), "saturation": round(s, 3), "edges": round(e, 3)}}


def create_from_references(style_id: str, name: str, images: list[str | Path], *, root: Path | None = None) -> Path:
    """참고 이미지 1장 이상 → assets/art_styles/<id>.yaml. 기본 그림체 id 와 겹치면 거절."""
    if not ID_RE.match(style_id):
        raise ValueError("그림체 id 는 영문 소문자·숫자·밑줄 2~40자입니다 (예: my_clean)")
    if style_id in _load_styles(str(Path(__file__).parent / "art_styles")):
        raise ValueError(f"기본 그림체와 같은 id 입니다: {style_id}")
    paths = [Path(p) for p in images]
    missing = [str(p) for p in paths if not p.is_file()]
    if not paths or missing:
        raise ValueError(f"참고 이미지를 찾을 수 없습니다: {missing or '없음'}")
    data = {"id": style_id, "name": name,
            "description": f"참고 이미지 {len(paths)}장에서 색·밝기·채도·선 비율만 측정해 만든 사용자 그림체 (그림 복제 아님)",
            **derive(analyze(paths)), "references": [p.name for p in paths]}
    dest_dir = root or USER_STYLE_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{style_id}.yaml"
    dest.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    _load_styles.cache_clear()
    assert style_id in art_styles() or root is not None
    return dest
