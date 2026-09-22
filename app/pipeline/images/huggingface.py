"""Hugging Face Inference API - FLUX.1-schnell. 무료 토큰으로 사용 가능(일일 한도 있음).

토큰: https://huggingface.co/settings/tokens (Read 권한이면 충분)
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from ...config import env
from .base import ImageProvider, resize_cover


class HuggingFaceImages(ImageProvider):
    name = "huggingface"
    concurrency = 1

    def __init__(self, model: str = "black-forest-labs/FLUX.1-schnell"):
        self.model = model

    async def generate(self, prompt: str, out_path: Path, width: int, height: int) -> None:
        key = env("HF_TOKEN")
        if not key:
            raise RuntimeError("HF_TOKEN 이 .env 에 없습니다.")
        # FLUX 는 16의 배수 해상도. 세로 9:16 에 가까운 768x1344 로 만들고 나중에 맞춤.
        body = {"inputs": prompt, "parameters": {"width": 768, "height": 1344, "num_inference_steps": 4}}
        async with httpx.AsyncClient(timeout=240) as c:
            for attempt in range(4):
                r = await c.post(
                    f"https://router.huggingface.co/hf-inference/models/{self.model}",
                    headers={"Authorization": f"Bearer {key}", "Accept": "image/png"},
                    json=body,
                )
                if r.status_code == 503:  # 모델 로딩 중
                    await asyncio.sleep(10)
                    continue
                r.raise_for_status()
                break
            else:
                raise RuntimeError("Hugging Face 모델이 준비되지 않았습니다. 잠시 후 다시 시도하세요.")
        if not r.headers.get("content-type", "").startswith("image/"):
            raise RuntimeError(f"이미지가 아닌 응답: {r.text[:200]}")
        out_path.write_bytes(r.content)
        resize_cover(out_path, width, height)
