"""장면 배경 라이브러리 (assets/carousel_backgrounds/). 컷의 background 문구에 맞는 승인된 배경 그림을 고른다.

index.json: [{"id", "file", "tags": [한국어 장소 단어], "mood": day|night|sunset|gloomy, "approved": bool, "source"}]
맞는 배경이 없으면 None → 렌더러가 기존 방식(앱이 그리는 단순 배경)으로 그린다.
"""
from __future__ import annotations

import json
from pathlib import Path

BG_ROOT = Path(__file__).resolve().parents[2] / "assets" / "carousel_backgrounds"
INDEX = "index.json"
NIGHT_WORDS = ("밤", "야근", "새벽", "야경", "어두운")


def load_index(root: Path | None = None) -> list[dict]:
    path = (root or BG_ROOT) / INDEX
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_index(rows: list[dict], root: Path | None = None) -> None:
    folder = root or BG_ROOT
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / (INDEX + ".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(folder / INDEX)


def pick(background: str, *, root: Path | None = None, mood: str = "") -> Path | None:
    """배경 문구(예: '원룸 밤', '은행 창구')와 가장 많이 겹치는 승인된 배경. 밤 단어가 있으면 밤 배경을 우선."""
    text = (background or "").strip()
    if not text:
        return None
    want_night = mood == "night" or any(w in text for w in NIGHT_WORDS)
    best, best_score = None, 0
    for row in load_index(root):
        if not row.get("approved"):
            continue
        path = (root or BG_ROOT) / row["file"]
        if not path.is_file():
            continue
        score = sum(len(tag) for tag in row.get("tags", []) if tag and tag in text)
        if not score:
            continue
        score += 3 if want_night == (row.get("mood") in ("night",)) else 0
        if score > best_score:
            best, best_score = path, score
    return best
