"""ElevenLabs TTS (유료). with-timestamps 엔드포인트로 글자 단위 타임스탬프를 받아 단어로 묶는다."""
from __future__ import annotations

import base64
from pathlib import Path

import httpx

from ...config import env
from ..models import Word
from .base import TTSProvider, fallback_words


class ElevenLabsTTS(TTSProvider):
    name = "elevenlabs"

    def __init__(self, model_id: str = "eleven_multilingual_v2"):
        self.model_id = model_id

    async def synthesize(self, text: str, out_path: Path, voice: str) -> list[Word] | None:
        key = env("ELEVENLABS_API_KEY")
        if not key:
            raise RuntimeError("ELEVENLABS_API_KEY 가 .env 에 없습니다.")
        if not voice:
            raise RuntimeError("ElevenLabs voice_id 를 config.yaml(tts.voices.elevenlabs)에 넣어주세요.")
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
                headers={"xi-api-key": key},
                params={"output_format": "mp3_44100_128"},
                json={"text": text, "model_id": self.model_id},
            )
            r.raise_for_status()
        data = r.json()
        out_path.write_bytes(base64.b64decode(data["audio_base64"]))

        align = data.get("alignment") or {}
        chars = align.get("characters") or []
        starts = align.get("character_start_times_seconds") or []
        ends = align.get("character_end_times_seconds") or []
        if not chars:
            return await fallback_words(text, out_path)

        words: list[Word] = []
        buf, w_start, w_end = "", None, None
        for ch, s, e in zip(chars, starts, ends):
            if ch.isspace():
                if buf:
                    words.append(Word(text=buf, start=w_start, end=w_end))
                buf, w_start = "", None
                continue
            if w_start is None:
                w_start = s
            buf += ch
            w_end = e
        if buf:
            words.append(Word(text=buf, start=w_start, end=w_end))
        return words
