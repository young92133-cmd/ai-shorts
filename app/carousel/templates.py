"""캐러셀 템플릿. app/carousel/templates/*.yaml 하나가 템플릿 하나다.

좌표는 캔버스 대비 비율(0~1) [x0, y0, x1, y1], 글자 크기는 캔버스 너비 대비 비율로 적는다.
페이지 타입별 영역은 `pages.<type>` 에서 기본 `boxes` 를 덮어쓴다. 새 템플릿은 YAML 만 추가하면 된다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

TEMPLATE_DIR = Path(__file__).parent / "templates"
ART_STYLE_DIR = Path(__file__).parent / "art_styles"                         # 기본 그림체
USER_STYLE_DIR = Path(__file__).resolve().parents[2] / "assets" / "art_styles"  # 참고 이미지로 만든 사용자 그림체
DEFAULT_TEMPLATE = "clean_info"
DEFAULT_BY_FORMAT = {"card_news": "clean_info", "insta_toon": "comic_hybrid", "hybrid": "comic_hybrid"}


def _hex(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


class Template:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.id: str = data["id"]
        self.name: str = data.get("name", self.id)
        canvas = data.get("canvas") or {}
        self.width = int(canvas.get("width", 1080))
        self.height = int(canvas.get("height", 1350))
        self.palette = {k: _hex(v) for k, v in (data.get("palette") or {}).items()}
        self.fonts = {k: float(v) for k, v in (data.get("fonts") or {}).items()}
        self.style: dict[str, Any] = data.get("style") or {}
        self.character: dict[str, Any] = data.get("character") or {}
        self.art: dict[str, Any] = data.get("art") or {}            # 그림체(art_styles)가 정하는 렌더 방식
        self.art_style: str = data.get("art_style", "default")
        self._boxes: dict[str, list[float]] = data.get("boxes") or {}
        self._pages: dict[str, dict[str, Any]] = data.get("pages") or {}

    def color(self, name: str, default: str = "#000000") -> tuple[int, int, int]:
        return self.palette.get(name) or _hex(default)

    def font_px(self, name: str, default: float = 0.04) -> int:
        return max(8, int(self.width * self.fonts.get(name, default)))

    def page_option(self, page_type: str, key: str, default: Any = None) -> Any:
        return (self._pages.get(page_type) or {}).get(key, default)

    def has_box(self, page_type: str, name: str) -> bool:
        return name in (self._pages.get(page_type) or {}) or name in self._boxes

    def box(self, page_type: str, name: str) -> tuple[int, int, int, int]:
        rel = (self._pages.get(page_type) or {}).get(name) or self._boxes.get(name)
        if not rel:
            raise KeyError(f"템플릿 {self.id}: '{page_type}.{name}' 영역이 없습니다")
        x0, y0, x1, y1 = rel
        return int(x0 * self.width), int(y0 * self.height), int(x1 * self.width), int(y1 * self.height)


def _validate(data: dict[str, Any], path: Path) -> None:
    for key in ("id", "palette", "fonts", "boxes"):
        if key not in data:
            raise ValueError(f"템플릿 {path.name}: '{key}' 가 없습니다")
    for name, rel in {**data["boxes"], **{f"{p}.{k}": v for p, o in (data.get("pages") or {}).items()
                                            for k, v in o.items() if isinstance(v, list)}}.items():
        if len(rel) != 4 or not all(0 <= float(v) <= 1 for v in rel) or rel[0] >= rel[2] or rel[1] >= rel[3]:
            raise ValueError(f"템플릿 {path.name}: 영역 '{name}' 좌표가 잘못됐습니다 {rel}")


@lru_cache(maxsize=None)
def _load_all(folder: str) -> dict[str, dict[str, Any]]:
    out = {}
    for path in sorted(Path(folder).glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        _validate(data, path)
        out[data["id"]] = data
    return out


def list_templates() -> list[dict[str, str]]:
    return [{"id": k, "name": v.get("name", k), "description": v.get("description", "")}
            for k, v in _load_all(str(TEMPLATE_DIR)).items()]


@lru_cache(maxsize=None)
def _load_styles(folder: str) -> dict[str, dict[str, Any]]:
    out = {}
    for path in sorted(Path(folder).glob("*.yaml")) if Path(folder).is_dir() else []:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not data.get("id"):
            raise ValueError(f"그림체 {path.name}: 'id' 가 없습니다")
        out[data["id"]] = data
    return out


def art_styles() -> dict[str, dict[str, Any]]:
    """기본 그림체 + 사용자 그림체 (같은 id 면 기본이 우선)."""
    return {**_load_styles(str(USER_STYLE_DIR)), **_load_styles(str(ART_STYLE_DIR))}


def list_art_styles() -> list[dict[str, str]]:
    return [{"id": k, "name": v.get("name", k), "description": v.get("description", "")} for k, v in art_styles().items()]


def load_template(template_id: str | None, fmt: str = "card_news", art_style: str | None = None) -> Template:
    """템플릿(배치·글꼴) 위에 그림체(색·선·배경·말풍선·효과)를 덮어 쓴다. 그림체를 안 고르면 템플릿 그대로."""
    all_ = _load_all(str(TEMPLATE_DIR))
    tid = template_id or DEFAULT_BY_FORMAT.get(fmt, DEFAULT_TEMPLATE)
    if tid not in all_:
        raise ValueError(f"알 수 없는 템플릿: {tid} (가능: {', '.join(all_)})")
    data = all_[tid]
    if art_style and art_style != "default":
        styles = art_styles()
        if art_style not in styles:
            raise ValueError(f"알 수 없는 그림체: {art_style} (가능: {', '.join(styles)})")
        st = styles[art_style]
        data = {**data, "palette": {**data.get("palette", {}), **(st.get("palette") or {})},
                "style": {**(data.get("style") or {}), **(st.get("style") or {})}, "art": st.get("art") or {},
                "art_style": art_style}
    return Template(data)
