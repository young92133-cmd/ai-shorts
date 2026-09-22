"""이미지 내용 파악 (Gemini Flash 비전).

첨부 파일·수집 이미지가 무엇인지 한 줄로 설명하게 한 뒤, 그 설명을 텍스트로 LLM 에 넘겨
어느 장면에 쓸지 고르게 한다. 이미지 자체를 대본 LLM 에 넘기지 않으므로
Claude 구독 경로(claude.exe)에서도 그대로 동작한다.

비용: Gemini Flash 비전은 이미지 1장당 수 원 수준. 키가 없으면 전부 건너뛰고
순서대로 배치하는 방식으로 자동 강등된다.
"""
from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from ..config import env
from .llm import ask_structured
from .models import Asset, AssetDescription, AssetPlan, Scene

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
VISION_MODEL = "gemini-3.1-flash"

DESCRIBE_PROMPT = (
    "이 이미지에 무엇이 보이는지 한국어로 한두 문장으로 설명하세요. "
    "특정 실존 인물을 지목하거나 이름을 추측하지 말고 '남성 1명', '단체 사진'처럼 일반적으로 쓰세요. "
    "그리고 이 이미지를 찾을 때 쓸 키워드 3~6개를 뽑으세요.\n"
    '반드시 JSON 만 출력: {"description": "...", "keywords": ["...", "..."]}'
)


def vision_available() -> bool:
    return bool(env("GEMINI_API_KEY"))


async def describe_image(path: Path, prompt: str = DESCRIBE_PROMPT) -> AssetDescription | None:
    """이미지 1장을 설명하게 한다. 실패하면 None (호출자가 건너뛴다)."""
    key = env("GEMINI_API_KEY")
    if not key or not path.exists():
        return None
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    if not mime.startswith("image/"):
        return None

    body: dict[str, Any] = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime,
                                 "data": base64.b64encode(path.read_bytes()).decode()}},
            ]
        }],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(ENDPOINT.format(model=VISION_MODEL),
                             headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                             json=body)
            if r.status_code >= 400:
                return None
        parts = r.json()["candidates"][0]["content"]["parts"]
        text = next((p["text"] for p in parts if "text" in p), "")
        data = json.loads(text)
        return AssetDescription(description=str(data.get("description", ""))[:300],
                                keywords=[str(k) for k in (data.get("keywords") or [])][:6])
    except Exception:  # noqa: BLE001
        return None


async def describe_all(paths: list[Path], concurrency: int = 3, log=print) -> list[AssetDescription | None]:
    """여러 이미지를 병렬로 설명. 키가 없으면 전부 None."""
    if not vision_available():
        log("GEMINI_API_KEY 없음 - 이미지 내용 분석을 건너뜁니다")
        return [None] * len(paths)
    sem = asyncio.Semaphore(concurrency)

    async def one(p: Path) -> AssetDescription | None:
        async with sem:
            return await describe_image(p)

    results = await asyncio.gather(*(one(p) for p in paths))
    ok = sum(1 for r in results if r)
    log(f"이미지 내용 분석 {ok}/{len(paths)}장")
    return results


MATCH_SYSTEM = """당신은 영상 편집자입니다. 준비된 소재(사진·영상)를 대본의 어느 장면에 넣을지 정합니다.

규칙:
- 소재의 내용이 그 장면의 나레이션과 실제로 맞아야 한다. 어울리지 않으면 scene_index 를 -1 로 두고 쓰지 않는다.
- 한 장면에는 소재 하나만 배치한다. 같은 장면에 둘을 넣지 않는다.
- fit 은 1~5 로 정직하게 매긴다. 억지로 끼워 맞추지 말 것. 3 미만이면 쓰지 않는다.
- 내용 설명이 비어 있는 소재는 fit 을 2 이하로 준다."""


async def match_assets_to_scenes(llm: dict[str, Any], assets: list[Asset], scenes: list[Scene],
                                 log=print) -> AssetPlan:
    """첨부 소재를 장면에 배치한다. 설명이 없으면 파일명만 보고 판단한다."""
    asset_lines = []
    for i, a in enumerate(assets):
        desc = a.description or "(내용 설명 없음)"
        kind = "영상" if a.kind == "video" else "사진"
        dur = f", {a.duration:.0f}초" if a.kind == "video" and a.duration else ""
        asset_lines.append(f"[소재 {i}] {kind}{dur} · 파일명 {a.name}\n  내용: {desc}")

    scene_lines = [f"[장면 {i}] {s.narration}\n  화면 키워드: {s.on_screen_text}"
                   for i, s in enumerate(scenes)]

    user = ("## 준비된 소재\n" + "\n".join(asset_lines)
            + "\n\n## 대본 장면\n" + "\n".join(scene_lines)
            + "\n\n각 소재를 어느 장면에 쓸지 정하세요.")
    plan = await ask_structured(llm, MATCH_SYSTEM, user, AssetPlan)
    used = sum(1 for m in plan.matches if m.scene_index >= 0 and m.fit >= 3)
    log(f"첨부 {len(assets)}개 중 {used}개 배치")
    return plan
