"""렌더 재료(timeline.json).

첫 렌더 직전에 장면·음성·자막 줄·댓글을 한 파일에 저장해 둔다. 완성 후 자막·댓글만 고쳐
다시 렌더하거나(LLM·TTS 재호출 없음), CapCut 프로젝트·재료 묶음으로 내보낼 때 이 파일만 읽는다.

경로는 잡 폴더 안이면 상대 경로(posix), 밖이면(BGM 등) 절대 경로로 저장한다.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .render import render_broll, render_slideshow
from .subtitles import build_ass

VERSION = 1
FILE = "timeline.json"
MAX_LINE_CHARS = 60
MAX_COMMENT_CHARS = 200


# ---------- 저장 ----------

def rel(path: str | Path | None, job_dir: Path) -> str:
    if not path:
        return ""
    p = Path(path)
    try:
        return p.resolve().relative_to(job_dir.resolve()).as_posix()
    except ValueError:
        return str(p)


def resolve(path: str, job_dir: Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else job_dir / p


def exists(job_dir: Path) -> bool:
    return (job_dir / FILE).is_file()


def load(job_dir: Path) -> dict[str, Any]:
    return json.loads((job_dir / FILE).read_text(encoding="utf-8"))


def save(job_dir: Path, tl: dict[str, Any]) -> None:
    tmp = job_dir / (FILE + ".tmp")
    tmp.write_text(json.dumps(tl, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(job_dir / FILE)


def total_duration(tl: dict[str, Any]) -> float:
    return round(sum(float(s["duration"]) for s in tl["scenes"]), 3)


def build_timeline(
    job_dir: Path,
    *,
    width: int, height: int, fps: int,
    mode: str,
    narration: Path,
    bgm: Path | None,
    bgm_volume: float,
    source_volume: float,
    transition: float,
    scenes: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    subtitle_style: dict[str, Any],
    subtitles_enabled: bool = True,
    titles_enabled: bool = True,
    comments: list[dict[str, Any]] | None = None,
    comment_slots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """comment_slots: 스타일이 참고 영상에서 찾은 댓글 자리 (⑦ 에서 캡처를 올리면 이 자리부터 채운다).

    scenes 항목: {"duration", "title", "credit", "visual": {"kind": image|video, "path", "src_start", "has_audio"}}"""
    out_scenes = []
    t = 0.0
    for i, s in enumerate(scenes):
        v = s["visual"]
        out_scenes.append({
            "index": i, "start": round(t, 3), "duration": round(float(s["duration"]), 3),
            "title": s.get("title", ""), "credit": s.get("credit", ""),
            "visual": {"kind": v["kind"], "path": rel(v["path"], job_dir),
                       "src_start": round(float(v.get("src_start", 0.0)), 3),
                       "has_audio": bool(v.get("has_audio", False)),
                       "source_url": v.get("source_url", "")},
        })
        t += float(s["duration"])
    return {
        "version": VERSION, "width": width, "height": height, "fps": fps, "mode": mode,
        "narration": rel(narration, job_dir), "bgm": rel(bgm, job_dir) if bgm else "",
        "bgm_volume": bgm_volume, "source_volume": source_volume, "transition": transition,
        "scenes": out_scenes,
        "subtitles": {"enabled": subtitles_enabled, "titles_enabled": titles_enabled,
                      "style": subtitle_style, "lines": lines},
        "comments": comments or [],
        "comment_slots": comment_slots or [],
    }


def text_comment(cid: str, text: str, start: float, end: float, source_url: str = "") -> dict[str, Any]:
    return {"id": cid, "kind": "text", "text": text, "start": round(start, 3), "end": round(end, 3),
            "x": 0.5, "y": 0.42, "width": 0.8, "source_url": source_url}


def image_comment(path: str, start: float, end: float, name: str = "") -> dict[str, Any]:
    return {"id": f"img-{uuid.uuid4().hex[:8]}", "kind": "image", "path": path, "name": name,
            "start": round(start, 3), "end": round(end, 3), "x": 0.5, "y": 0.42, "width": 0.8}


# ---------- 사용자 수정 반영 ----------

def respread(text: str, start: float, end: float) -> list[dict[str, Any]]:
    """고친 문구의 단어 시간을 글자 수 비율로 다시 나눈다 (tts.base.fallback_words 와 같은 방식)."""
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if not words:
        return []
    weights = [len(w) + 0.6 for w in words]
    total, span = sum(weights), max(0.1, end - start)
    out, t = [], start
    for w, wt in zip(words, weights):
        d = span * wt / total
        out.append({"text": w, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return out


def _num(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, x))


def _clean_line(line: dict[str, Any], total: float) -> dict[str, Any] | None:
    text = " ".join(str(line.get("text", "")).split())[:MAX_LINE_CHARS]
    if not text:
        return None
    start = _num(line.get("start"), 0.0, total, 0.0)
    end = _num(line.get("end"), 0.0, total, start + 1.0)
    if end < start + 0.1:
        end = min(total, start + 0.5)
    words = line.get("words") or []
    try:
        # 문구·시간을 그대로 두었으면 원래 단어 타이밍(노래방식 강조)을 유지한다
        ok = (isinstance(words, list) and bool(words)
              and " ".join(str(w.get("text", "")) for w in words) == text
              and all(start - 0.01 <= float(w.get("start", -1)) <= float(w.get("end", -1)) <= end + 0.01
                      for w in words))
    except (AttributeError, TypeError, ValueError):
        ok = False
    if ok:
        words = [{"text": str(w["text"]), "start": float(w["start"]), "end": float(w["end"])} for w in words]
    else:
        words = respread(text, start, end)
    return {"start": round(start, 3), "end": round(end, 3), "text": text, "words": words}


def apply_edit(tl: dict[str, Any], body: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """⑦ 화면에서 보낸 수정분을 반영한다. 반환: (새 timeline, 목록에서 빠진 이미지 댓글 경로)

    클라이언트는 새 이미지 댓글을 여기서 만들 수 없다(업로드 API 로만 추가). 경로도 바꿀 수 없다.
    """
    total = total_duration(tl)
    sub = body.get("subtitles")
    if isinstance(sub, dict):
        cur = tl["subtitles"]
        if "enabled" in sub:
            cur["enabled"] = bool(sub["enabled"])
        if "titles_enabled" in sub:
            cur["titles_enabled"] = bool(sub["titles_enabled"])
        if isinstance(sub.get("lines"), list):
            lines = [ln for ln in (_clean_line(x, total) for x in sub["lines"] if isinstance(x, dict)) if ln]
            cur["lines"] = sorted(lines, key=lambda ln: ln["start"])

    titles = body.get("titles")
    if isinstance(titles, list):
        for s, title in zip(tl["scenes"], titles):
            s["title"] = " ".join(str(title or "").split())[:MAX_LINE_CHARS]

    removed: list[str] = []
    comments = body.get("comments")
    if isinstance(comments, list):
        old = {c["id"]: c for c in tl.get("comments", [])}
        kept: list[dict[str, Any]] = []
        for c in comments:
            if not isinstance(c, dict) or c.get("id") not in old:
                continue
            base = dict(old[c["id"]])
            base["start"] = round(_num(c.get("start"), 0.0, total, base["start"]), 3)
            base["end"] = round(_num(c.get("end"), 0.0, total, base["end"]), 3)
            if base["end"] < base["start"] + 0.3:
                base["end"] = round(min(total, base["start"] + 3.5), 3)
            base["x"] = round(_num(c.get("x"), 0.05, 0.95, base.get("x", 0.5)), 4)
            base["y"] = round(_num(c.get("y"), 0.05, 0.95, base.get("y", 0.42)), 4)
            base["width"] = round(_num(c.get("width"), 0.2, 1.0, base.get("width", 0.8)), 4)
            if base["kind"] == "text" and "text" in c:
                base["text"] = " ".join(str(c["text"]).split())[:MAX_COMMENT_CHARS] or base["text"]
            kept.append(base)
        kept_ids = {c["id"] for c in kept}
        removed = [c["path"] for cid, c in old.items() if cid not in kept_ids and c["kind"] == "image"]
        tl["comments"] = kept
    return tl, removed


# ---------- 렌더 ----------

def ass_inputs(tl: dict[str, Any]) -> dict[str, Any]:
    """build_ass 에 넘길 titles / credits / comments / lines."""
    sub = tl["subtitles"]
    scenes = tl["scenes"]
    return {
        "titles": [(s["start"], s["start"] + s["duration"], s["title"]) for s in scenes]
        if sub.get("titles_enabled", True) else [],
        "credits": [(s["start"], s["start"] + s["duration"], s["credit"]) for s in scenes if s.get("credit")],
        "comments": [(c["start"], c["end"], c["text"]) for c in tl.get("comments", []) if c["kind"] == "text"],
        "lines": sub["lines"] if sub.get("enabled", True) else [],
    }


async def render_timeline(tl: dict[str, Any], job_dir: Path, out_path: Path,
                          fonts_dir: Path | None = None) -> Path:
    """timeline.json 하나로 subs.ass 를 만들고 최종 영상을 렌더한다. 첫 렌더와 다시 만들기가 같은 코드를 쓴다."""
    w, h, fps = int(tl["width"]), int(tl["height"]), int(tl["fps"])
    st = tl["subtitles"]["style"]
    ass = build_ass([], job_dir / "subs.ass", w, h, font=st.get("font", "Malgun Gothic"),
                    size=int(st.get("size", 64)), highlight=st.get("highlight", "#FFD400"),
                    outline=st.get("outline", "#000000"), **ass_inputs(tl))

    overlays = []
    for c in tl.get("comments", []):
        if c["kind"] == "image":
            p = resolve(c["path"], job_dir)
            if p.is_file():
                overlays.append({**c, "path": p})

    narration = resolve(tl["narration"], job_dir)
    bgm = resolve(tl["bgm"], job_dir) if tl.get("bgm") else None
    common = dict(ass_path=ass, bgm=bgm, width=w, height=h, fps=fps,
                  bgm_volume=float(tl["bgm_volume"]), fonts_dir=fonts_dir, overlays=overlays)
    if tl["mode"] == "broll":
        clips = []
        for s in tl["scenes"]:
            v = s["visual"]
            clip = {"kind": v["kind"], "path": resolve(v["path"], job_dir), "duration": s["duration"]}
            if v["kind"] == "video":
                clip.update(start=v["src_start"], has_audio=v["has_audio"])
            clips.append(clip)
        return await render_broll(clips, narration, out_path,
                                  source_volume=float(tl["source_volume"]), **common)
    images = [resolve(s["visual"]["path"], job_dir) for s in tl["scenes"]]
    durations = [float(s["duration"]) for s in tl["scenes"]]
    return await render_slideshow(images, durations, narration, out_path,
                                  transition=float(tl["transition"]), **common)
