"""Typecast TTS (유료, 한국어 특화). 타임스탬프 없음 → 비율 배분.

API 스펙은 https://docs.typecast.ai 를 기준으로 작성. 필드명이 바뀌면 이 파일만 수정.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from ...config import env
from ..models import Word
from .base import TTSProvider, fallback_words


class TypecastTTS(TTSProvider):
    name = "typecast"

    def __init__(self, model: str = "ssfm-v21"):
        self.model = model

    async def synthesize(self, text: str, out_path: Path, voice: str) -> list[Word] | None:
        key = env("TYPECAST_API_KEY")
        if not key:
            raise RuntimeError("TYPECAST_API_KEY 가 .env 에 없습니다.")
        if not voice:
            raise RuntimeError("Typecast voice_id 를 config.yaml(tts.voices.typecast)에 넣어주세요.")
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(
                "https://api.typecast.ai/v1/text-to-speech",
                headers={"X-API-KEY": key},
                json={"text": text, "model": self.model, "voice_id": voice, "language": "kor",
                      "output": {"audio_format": "mp3"}},
            )
            r.raise_for_status()
        out_path.write_bytes(r.content)
        return await fallback_words(text, out_path)
