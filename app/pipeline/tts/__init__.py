from __future__ import annotations

from typing import Any

from .base import TTSProvider


def get_tts(cfg: dict[str, Any]) -> TTSProvider:
    name = cfg["tts"]["provider"]
    if name == "edge":
        from .edge import EdgeTTS
        return EdgeTTS(rate=cfg["tts"].get("rate", "+0%"))
    if name == "openai":
        from .openai_tts import OpenAITTS
        return OpenAITTS()
    if name == "elevenlabs":
        from .elevenlabs import ElevenLabsTTS
        return ElevenLabsTTS()
    if name == "typecast":
        from .typecast import TypecastTTS
        return TypecastTTS()
    raise ValueError(f"알 수 없는 TTS provider: {name}")
