"""클립 모드: 선택된 구간을 정리하고 자막 단어를 새 타임라인으로 옮긴다."""
from __future__ import annotations

from .models import ClipSegment, Word


def normalize_segments(segments: list[ClipSegment], video_duration: float, max_total: float = 60.0) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    total = 0.0
    for seg in sorted(segments, key=lambda s: s.start):
        s = max(0.0, seg.start)
        e = min(video_duration or seg.end, seg.end)
        if e - s < 1.0:
            continue
        if out and s < out[-1][1]:  # 겹치면 이어붙임
            s = out[-1][1]
            if e - s < 1.0:
                continue
        if total + (e - s) > max_total:
            e = s + (max_total - total)
            if e - s < 1.0:
                break
        out.append((round(s, 3), round(e, 3)))
        total += e - s
        if total >= max_total:
            break
    if not out:
        raise RuntimeError("사용할 수 있는 구간이 없습니다.")
    return out


def retime_words(words: list[Word], segments: list[tuple[float, float]]) -> list[Word]:
    """원본 타임라인의 단어를, 구간을 이어붙인 새 타임라인 기준으로 변환."""
    out: list[Word] = []
    offset = 0.0
    for s, e in segments:
        for w in words:
            if w.start >= s and w.start < e:
                out.append(Word(text=w.text, start=round(w.start - s + offset, 3),
                                end=round(min(w.end, e) - s + offset, 3)))
        offset += e - s
    return out
