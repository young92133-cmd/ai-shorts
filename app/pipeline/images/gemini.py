"""Google Gemini 이미지 생성 (Nano Banana 2 계열).

9:16 세로를 네이티브로 지원해 쇼츠에 그대로 맞는다. 무료 티어는 없고 장당 과금된다.
키 발급: https://aistudio.google.com/apikey

| 클래스             | 모델 ID                        | 1K 장당 (환율 1450원) |
|--------------------|--------------------------------|----------------------|
| GeminiImagesLite   | gemini-3.1-flash-lite-image    | 약 49원              |
| GeminiImages       | gemini-3.1-flash-image         | 약 97원              |
| GeminiImagesPro    | gemini-3-pro-image             | 약 194원             |
"""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any

import httpx

from ...config import env
from .base import ImageProvider, resize_cover

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"

# 재시도해도 소용없는 응답 (안전 필터, 잘못된 요청, 권한/결제 문제)
FATAL_STATUS = {400, 401, 403, 404}


def _find_image_b64(data: Any) -> str | None:
    """응답에서 base64 이미지를 찾는다.

    문서 기준 경로는 output_image.data 지만, 복잡한 출력은 steps 안에 들어온다.
    구조가 바뀌어도 견디도록 재귀로 훑는다.
    """
    if isinstance(data, dict):
        out = data.get("output_image")
        if isinstance(out, dict) and out.get("data"):
            return out["data"]
        # {"type": "image", "data": "..."} 형태
        if data.get("type") == "image" and isinstance(data.get("data"), str):
            return data["data"]
        if isinstance(data.get("inline_data"), dict) and data["inline_data"].get("data"):
            return data["inline_data"]["data"]
        for v in data.values():
            if (found := _find_image_b64(v)) is not None:
                return found
    elif isinstance(data, list):
        for v in data:
            if (found := _find_image_b64(v)) is not None:
                return found
    return None


class GeminiImages(ImageProvider):
    name = "gemini"
    concurrency = 3

    def __init__(self, model: str = "gemini-3.1-flash-image", image_size: str = "1K"):
        self.model = model
        self.image_size = image_size

    async def generate(self, prompt: str, out_path: Path, width: int, height: int) -> None:
        key = env("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY 가 .env 에 없습니다. https://aistudio.google.com/apikey 에서 발급하세요.")

        body = {
            "model": self.model,
            "input": [{"type": "text", "text": prompt[:4000]}],
            "response_format": {
                "type": "image",
                "mime_type": "image/jpeg",
                "aspect_ratio": "9:16",   # 쇼츠 비율 그대로
                "image_size": self.image_size,
            },
        }
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}

        last_err = ""
        async with httpx.AsyncClient(timeout=240) as c:
            for attempt in range(3):
                r = await c.post(ENDPOINT, headers=headers, json=body)
                if r.status_code in FATAL_STATUS:
                    # 안전 필터·잘못된 키 등은 재시도해도 같다 → 바로 fallback 으로
                    raise RuntimeError(f"Gemini 거부 {r.status_code}: {r.text[:200]}")
                if r.status_code >= 500 or r.status_code == 429:
                    last_err = f"{r.status_code}: {r.text[:150]}"
                    if attempt < 2:
                        await asyncio.sleep(4 * (attempt + 1))
                        continue
                    raise RuntimeError(f"Gemini 요청 실패 {last_err}")
                r.raise_for_status()
                break

        b64 = _find_image_b64(r.json())
        if not b64:
            raise RuntimeError(f"Gemini 응답에 이미지가 없습니다: {r.text[:200]}")
        out_path.write_bytes(base64.b64decode(b64))
        resize_cover(out_path, width, height)


class GeminiImagesLite(GeminiImages):
    """가장 저렴. 대부분의 쇼츠에 충분하다."""
    name = "gemini-lite"

    def __init__(self, image_size: str = "1K"):
        super().__init__("gemini-3.1-flash-lite-image", image_size)


class GeminiImagesPro(GeminiImages):
    """복잡한 구도·정확한 텍스트가 필요할 때."""
    name = "gemini-pro"
    concurrency = 2

    def __init__(self, image_size: str = "1K"):
        super().__init__("gemini-3-pro-image", image_size)


if __name__ == "__main__":
    # 스모크 테스트 (이미지 1장 = 약 50~100원 과금됨)
    #   python -m app.pipeline.images.gemini "프롬프트" [lite|flash|pro]
    import sys

    prompt = sys.argv[1] if len(sys.argv) > 1 else (
        "clean technical illustration, isometric cutaway of a reinforced concrete beam, blueprint accents, no text")
    tier = sys.argv[2] if len(sys.argv) > 2 else "lite"
    cls = {"lite": GeminiImagesLite, "flash": GeminiImages, "pro": GeminiImagesPro}[tier]
    out = Path("output/_gemini_test.jpg")
    out.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(cls().generate(prompt, out, 1080, 1920))
    print(f"저장됨: {out.resolve()} ({out.stat().st_size // 1024} KB)")
