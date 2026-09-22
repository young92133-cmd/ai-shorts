"""fal.ai FLUX schnell - 장당 약 $0.003, 빠르고 품질 좋음."""
from __future__ import annotations

from pathlib import Path

import httpx

from ...config import env
from .base import ImageProvider, resize_cover


class FalImages(ImageProvider):
    name = "fal"

    def __init__(self, model: str = "fal-ai/flux/schnell"):
        self.model = model

    async def generate(self, prompt: str, out_path: Path, width: int, height: int) -> None:
        key = env("FAL_KEY")
        if not key:
            raise RuntimeError("FAL_KEY 가 .env 에 없습니다.")
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(
                f"https://fal.run/{self.model}",
                headers={"Authorization": f"Key {key}"},
                json={"prompt": prompt, "image_size": {"width": 768, "height": 1344},
                      "num_images": 1, "enable_safety_checker": True},
            )
            r.raise_for_status()
            img_url = r.json()["images"][0]["url"]
            img = await c.get(img_url)
            img.raise_for_status()
        out_path.write_bytes(img.content)
        resize_cover(out_path, width, height)
