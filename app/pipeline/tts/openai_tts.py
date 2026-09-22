"""OpenAI TTS (gpt-4o-mini-tts). 유료. 타임스탬프 없음 → 비율 배분."""
from __future__ import annotations

from pathlib import Path

import httpx

from ...config import env
from ..models import Word
from .base import TTSProvider, fallback_words


class OpenAITTS(TTSProvider):
    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini-tts"):
        self.model = model

    async def synthesize(self, text: str, out_path: Path, voice: str) -> list[Word] | None:
        key = env("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY 가 .env 에 없습니다.")
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": self.model, "voice": voice or "nova", "input": text, "response_format": "mp3"},
            )
            r.raise_for_status()
        out_path.write_bytes(r.content)
        return await fallback_words(text, out_path)
