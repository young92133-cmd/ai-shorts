"""Clip Analyzer: 사용 가능한(권리 확인된) 영상에서 장면에 쓸 구간을 고른다.

입력 영상 → 장면 전환(샷 경계) · 무음/말 경계 · (있으면) 자막/전사 → 후보 구간 → 점수 → 추천 구간.
권리 판단은 하지 않는다. 호출하는 쪽(source_resolver)이 usable 로 판정한 파일만 넘긴다.

점수는 편집 적합도 내부 값이다:
  stability   한 샷 안에 들어가는가 (중간에 컷이 튀지 않음)
  boundary    샷 경계·말 경계에서 시작하는가
  position    앞뒤 타이틀/크레딧 구간을 피했는가
  relevance   구간 자막/전사에 장면 키워드·질문·주장 단어가 있는가 (자막이 없으면 중립)
"""
from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .media import has_audio_sync, probe_duration_sync
from .models import Word

SCENE_THRESHOLD = 0.30
SILENCE_DB = -30
SILENCE_MIN = 0.35
MAX_ANALYZE_SECONDS = 600        # 이보다 긴 영상은 앞부분만 분석한다


class ClipCandidate(BaseModel):
    start: float
    end: float
    score: int
    parts: dict[str, int] = Field(default_factory=dict)
    reason: str = ""

    @property
    def label(self) -> str:
        return f"{fmt(self.start)}-{fmt(self.end)}"


class ClipAnalysis(BaseModel):
    path: str
    duration: float
    shots: list[float] = Field(default_factory=list)          # 샷 경계 시각
    silences: list[tuple[float, float]] = Field(default_factory=list)
    has_transcript: bool = False
    candidates: list[ClipCandidate] = Field(default_factory=list)
    recommended: ClipCandidate | None = None


def fmt(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def _ff(args: list[str]) -> str:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.stderr or ""


def detect_shots(path: Path, limit: float) -> list[float]:
    """ffmpeg scene score 로 샷 경계 시각을 찾는다."""
    err = _ff(["-t", f"{limit:.1f}", "-i", str(path), "-an", "-vf",
               f"select='gt(scene,{SCENE_THRESHOLD})',showinfo", "-f", "null", "-"])
    times = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", err)]
    return sorted({round(t, 2) for t in times})


def detect_silences(path: Path, limit: float) -> list[tuple[float, float]]:
    err = _ff(["-t", f"{limit:.1f}", "-i", str(path), "-vn", "-af",
               f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", err)]
    out = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else limit
        out.append((round(s, 2), round(e, 2)))
    return out


def parse_srt(text: str) -> list[Word]:
    """NASA 등 제공 자막(.srt)을 구간 단위 Word 로 읽는다 (단어가 아니라 자막 줄 단위)."""
    words: list[Word] = []
    pat = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)\s*\n(.+?)(?:\n\s*\n|\Z)", re.S)
    for m in pat.finditer(text.replace("\r\n", "\n")):
        h1, m1, s1, ms1, h2, m2, s2, ms2, body = m.groups()
        start = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(ms1) / 1000
        end = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(ms2) / 1000
        words.append(Word(text=" ".join(body.split()), start=round(start, 3), end=round(end, 3)))
    return words


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[0-9a-zA-Z가-힣]{2,}", (text or "").lower())}


def score_windows(duration: float, need: float, shots: list[float], silences: list[tuple[float, float]],
                  transcript: list[Word] | None = None, keywords: list[str] | None = None,
                  step: float = 1.0) -> list[ClipCandidate]:
    """need 초 길이의 후보 구간을 만들고 점수를 매긴다 (순수 함수: 테스트 가능)."""
    need = max(0.5, min(need, duration))
    keys = set().union(*[_tokens(k) for k in keywords or []]) if keywords else set()
    starts = {0.0, *[s for s in shots if s + need <= duration]}
    t = 0.0
    while t + need <= duration + 1e-6:
        starts.add(round(t, 2))
        t += step
    head, tail = min(3.0, duration * 0.05), min(4.0, duration * 0.07)
    out: list[ClipCandidate] = []
    for s in sorted(starts):
        e = round(min(duration, s + need), 2)
        cuts = [c for c in shots if s + 0.15 < c < e - 0.15]
        stability = 40 if not cuts else (24 if len(cuts) == 1 else 8)
        on_shot = any(abs(s - c) < 0.25 for c in shots) or s == 0.0
        in_silence = any(a - 0.1 <= s <= b + 0.1 for a, b in silences)
        boundary = (12 if on_shot else 0) + (8 if in_silence or not silences else 0)
        position = 20 if (s >= head and e <= duration - tail) or duration < need + head + tail else 6
        relevance = 10          # 자막이 없으면 중립
        hit = 0
        if transcript and keys:
            text = " ".join(w.text for w in transcript if w.end > s and w.start < e)
            hit = len(keys & _tokens(text))
            relevance = min(20, 4 + 8 * hit)
        parts = {"stability": stability, "boundary": boundary, "position": position, "relevance": relevance}
        why = []
        why.append("한 샷 안" if not cuts else f"컷 {len(cuts)}번 포함")
        if on_shot:
            why.append("샷 경계에서 시작")
        if hit:
            why.append(f"키워드 {hit}개 일치")
        out.append(ClipCandidate(start=round(s, 2), end=e, score=sum(parts.values()), parts=parts,
                                 reason=", ".join(why)))
    out.sort(key=lambda c: (-c.score, c.start))
    return out


def _pick_spread(cands: list[ClipCandidate], n: int, gap: float) -> list[ClipCandidate]:
    """서로 겹치지 않는 상위 후보 n개."""
    picked: list[ClipCandidate] = []
    for c in cands:
        if all(c.end <= p.start - gap or c.start >= p.end + gap for p in picked):
            picked.append(c)
        if len(picked) >= n:
            break
    return picked


def analyze_sync(path: Path, need: float, *, keywords: list[str] | None = None,
                 transcript: list[Word] | None = None, top: int = 3) -> ClipAnalysis:
    duration = probe_duration_sync(path)
    limit = min(duration, MAX_ANALYZE_SECONDS)
    shots = detect_shots(path, limit)
    silences = detect_silences(path, limit) if has_audio_sync(path) else []
    cands = score_windows(limit, need, shots, silences, transcript, keywords)
    best = _pick_spread(cands, top, gap=0.5)
    return ClipAnalysis(path=str(path), duration=round(duration, 2), shots=shots, silences=silences,
                        has_transcript=bool(transcript), candidates=best, recommended=best[0] if best else None)


async def analyze(path: Path, need: float, **kw: Any) -> ClipAnalysis:
    return await asyncio.to_thread(analyze_sync, path, need, **kw)
