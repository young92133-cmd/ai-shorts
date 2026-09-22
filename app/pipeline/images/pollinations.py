"""Pollinations.ai - 키 없이 쓰는 무료 이미지 생성.

주의: 인증 없는 무료 티어는 저화질 + 워터마크가 붙는다. 품질이 필요하면 huggingface(무료 토큰) 나 fal 사용.
"""
from __future__ import annotations

import asyncio
import random
from pathlib import Path
from urllib.parse import quote

import httpx

from .base import ImageProvider, resize_cover


class PollinationsImages(ImageProvider):
    name = "pollinations"
    concurrency = 1

    def __init__(self, model: str = "flux"):
        self.model = model

    async def generate(self, prompt: str, out_path: Path, width: int, height: int) -> None:
        url = f"https://image.pollinations.ai/prompt/{quote(prompt[:800])}"
        params = {"width": width, "height": height, "nologo": "true", "model": self.model,
                  "seed": random.randint(1, 10**8), "enhance": "false"}
        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as c:
            for attempt in range(4):
                r = await c.get(url, params=params)
                if r.status_code == 429:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                break
            else:
                raise RuntimeError("Pollinations 요청 제한(429)")
        if not r.headers.get("content-type", "").startswith("image/"):
            raise RuntimeError(f"이미지가 아닌 응답: {r.headers.get('content-type')}")
        out_path.write_bytes(r.content)
        resize_cover(out_path, width, height)
