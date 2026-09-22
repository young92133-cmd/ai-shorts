"""TTS provider 공통 인터페이스."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

from ..media import probe_duration
from ..models import Word


class TTSProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def synthesize(self, text: str, out_path: Path, voice: str) -> list[Word] | None:
        """text를 out_path(mp3)에 저장. 단어 타임스탬프를 알면 반환, 모르면 None."""


def split_words(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", text.strip()) if w]


async def fallback_words(text: str, audio_path: Path) -> list[Word]:
    """타임스탬프가 없는 provider용: 글자 수 비율로 단어 시간을 배분."""
    dur = await probe_duration(audio_path)
    words = split_words(text)
    if not words:
        return []
    weights = [len(w) + 0.6 for w in words]  # 단어 사이 짧은 쉼 반영
    total = sum(weights)
    out: list[Word] = []
    t = 0.0
    for w, wt in zip(words, weights):
        d = dur * wt / total
        out.append(Word(text=w, start=round(t, 3), end=round(t + d, 3)))
        t += d
    return out
