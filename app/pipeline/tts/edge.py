"""무료 Microsoft Edge TTS. 단어 경계 이벤트로 자막 타임스탬프까지 확보."""
from __future__ import annotations

from pathlib import Path

import edge_tts

from ..models import Word
from .base import TTSProvider, fallback_words


class EdgeTTS(TTSProvider):
    name = "edge"

    def __init__(self, rate: str = "+0%"):
        self.rate = rate

    async def synthesize(self, text: str, out_path: Path, voice: str) -> list[Word] | None:
        comm = edge_tts.Communicate(text, voice or "ko-KR-SunHiNeural", rate=self.rate)
        words: list[Word] = []
        with open(out_path, "wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7
                    end = start + chunk["duration"] / 1e7
                    words.append(Word(text=chunk["text"], start=round(start, 3), end=round(end, 3)))
        if not words:
            return await fallback_words(text, out_path)
        return words
