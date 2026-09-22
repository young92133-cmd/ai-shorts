"""OpenAI gpt-image (유료, 장당 수십~수백 원). quality=low 로 비용 절감."""
from __future__ import annotations

import base64
from pathlib import Path

import httpx

from ...config import env
from .base import ImageProvider, resize_cover


class OpenAIImages(ImageProvider):
    name = "openai"

    def __init__(self, model: str = "gpt-image-1", quality: str = "low"):
        self.model = model
        self.quality = quality

    async def generate(self, prompt: str, out_path: Path, width: int, height: int) -> None:
        key = env("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY 가 .env 에 없습니다.")
        async with httpx.AsyncClient(timeout=240) as c:
            r = await c.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": self.model, "prompt": prompt, "size": "1024x1536", "quality": self.quality, "n": 1},
            )
            r.raise_for_status()
        b64 = r.json()["data"][0]["b64_json"]
        out_path.write_bytes(base64.b64decode(b64))
        resize_cover(out_path, width, height)
