from __future__ import annotations

from typing import Any

from .base import ImageProvider


def get_images(cfg: dict[str, Any]) -> ImageProvider | None:
    """None 이면 AI 생성을 하지 않는다 (첨부·기사 이미지만 사용)."""
    name = cfg["images"]["provider"]
    size = cfg["images"].get("image_size", "1K")
    if not name or name == "none":
        return None
    if name in ("gemini", "gemini-lite", "gemini-pro"):
        from .gemini import GeminiImages, GeminiImagesLite, GeminiImagesPro
        cls = {"gemini": GeminiImages, "gemini-lite": GeminiImagesLite, "gemini-pro": GeminiImagesPro}[name]
        return cls(image_size=size)
    if name == "pollinations":
        from .pollinations import PollinationsImages
        return PollinationsImages()
    if name == "huggingface":
        from .huggingface import HuggingFaceImages
        return HuggingFaceImages()
    if name == "fal":
        from .fal import FalImages
        return FalImages()
    if name == "openai":
        from .openai_img import OpenAIImages
        return OpenAIImages()
    raise ValueError(f"알 수 없는 이미지 provider: {name}")
