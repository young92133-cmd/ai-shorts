"""Source Resolver: 장면마다 쓸 실제 영상·이미지를 찾고, 권리를 판정하고, 고른다.

흐름: 장면 정의(대본·beat_role) → 검색어 계획(AI) → discover(공개 API) → 권리 판정(license 메타데이터)
     → 적합도 평가(AI) + 품질·최신성·권리 확실성·편집 용이성 점수 → 장면별 선택 → ingest(다운로드)
     → 영상이면 Clip Analyzer 로 구간 선택 → Scene Planner 로 넘김.

권리 원칙
- 검색·분석은 적극적으로 한다. 최종 화면에 직접 쓰는 것은 사용 근거가 확인된 자료뿐이다.
- 자동 usable: CC0 · Public Domain Mark · CC BY(출처 표기) · NASA 제작 자료 · Pexels/Pixabay 라이선스(키가 있을 때).
- 자동 reference_only: CC BY-SA(영상 전체에 동일 조건이 걸림) · NC(비상업) · ND(변경 금지) · 표기 없음.
- YouTube: 공개돼 있다는 이유로 usable 이 아니다. 라이선스 표기는 기록하되, YouTube 약관상 자동 다운로드를
  지원하지 않으므로 화면 소스로 승격하지 않는다(사용자가 원본 파일을 직접 제공하면 기존 업로드 경로).
- 다운로드는 discover → inspect → classify → usable 일 때만 ingest 순서로 한다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import html
import json
import re
from pathlib import Path
from typing import Any, Callable, Literal

import httpx
from pydantic import BaseModel, Field

from ..config import env
from . import clip_analyzer
from .llm import ask_structured, safe_error

PLAN_FILE = "source_plan.json"
DEFAULTS = {"providers": ["openverse", "wikimedia_commons", "nasa", "pexels", "pixabay"],
            "contact": "", "max_file_mb": 80, "min_score": 60, "min_visual_fit": 7, "per_query": 4,
            "max_candidates_per_scene": 6}
WEIGHTS = {"visual_fit": 30, "evidence_fit": 15, "quality": 15, "freshness": 5, "rights_confidence": 20,
           "editability": 15}
Progress = Callable[[str, int, str], None]


# ---------- 모델 ----------

class Rights(BaseModel):
    status: Literal["usable", "reference_only", "unknown"]
    basis: str
    confidence: float = 0.0           # 0~1
    license_key: str = ""             # sources.py PROVEN_LICENSES 의 키 (usable 일 때)
    license_url: str = ""
    label: str = ""                   # 화면 표기용 (예: CC BY 2.0)


class VisualCandidate(BaseModel):
    id: str
    provider: str
    media_type: Literal["image", "video"]
    title: str = ""
    description: str = ""
    page_url: str = ""
    file_url: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0.0
    date: str = ""
    creator: str = ""
    rights: Rights
    query: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)   # 제공처별 부가 정보 (nasa_id 등)

    def credit(self) -> str:
        who = self.creator.strip()[:30] or self.provider
        label = self.rights.label or self.rights.license_key
        src = {"openverse": "Openverse", "wikimedia_commons": "Wikimedia Commons", "nasa": "NASA",
               "pexels": "Pexels", "pixabay": "Pixabay"}.get(self.provider, self.provider)
        return f"{'영상' if self.media_type == 'video' else '사진'}: {who} / {label} / {src}"[:80]


class SceneQuery(BaseModel):
    scene_index: int = Field(description="장면 번호 (0부터)")
    query_en: str = Field(description="공개 이미지·영상 아카이브에서 찾을 영어 검색어 2~4단어. 구체적인 사물·장소·현상")
    alt_query_en: str = Field(default="", description="첫 검색어로 못 찾을 때 쓸 더 일반적인 영어 검색어")
    prefer: Literal["video", "image", "card"] = Field(description="이 장면에 가장 맞는 화면 종류. 글자·질문 중심이면 card")
    must_show: str = Field(description="화면에 보여야 하는 것 한 문장 (한국어)")
    keywords_en: list[str] = Field(default_factory=list, description="영상 자막에서 찾을 영어 키워드 2~5개")


class QueryPlan(BaseModel):
    scenes: list[SceneQuery]


class FitScore(BaseModel):
    candidate_id: str
    visual_fit: int = Field(description="장면 나레이션·must_show 와 화면이 맞는 정도 0~10")
    evidence_fit: int = Field(description="장면의 주장·사실을 실제로 보여 주는 정도 0~10")
    reason: str = Field(description="한 문장")


class FitPlan(BaseModel):
    scores: list[FitScore]


# ---------- 권리 판정 ----------

def _cc(code: str, version: str = "") -> tuple[str, str]:
    code = (code or "").lower().strip().replace("_", "-")
    code = re.sub(r"^cc[- ]", "", code)
    label = f"CC {code.upper()} {version}".strip() if code not in ("cc0", "pdm", "pd") else (
        "CC0" if code == "cc0" else "Public Domain")
    return code, label


def classify_license(code: str, *, version: str = "", license_url: str = "", provider: str = "",
                     restrictions: str = "", copyright_marker: bool = False) -> Rights:
    """라이선스 표기로 최종 화면 사용 가능 여부를 판정한다. 표기가 애매하면 usable 로 올리지 않는다."""
    if restrictions.strip():
        return Rights(status="reference_only", basis=f"사용 제한 표기({restrictions.strip()[:40]})가 있어 화면 사용 제외",
                      confidence=0.0, license_url=license_url)
    if provider == "nasa":
        if copyright_marker:
            return Rights(status="reference_only", basis="NASA 자료지만 제3자 저작권 표기가 있어 화면 사용 제외",
                          license_url=license_url)
        return Rights(status="usable", basis="NASA 미디어 이용 지침: NASA 제작 자료는 일반적으로 저작권이 없음 "
                      "(NASA 로고·인물의 보증 표현 금지)", confidence=0.8, license_key="nasa_media",
                      license_url=license_url or "https://www.nasa.gov/nasa-brand-center/images-and-media/",
                      label="NASA")
    if provider in ("pexels", "pixabay"):
        url = {"pexels": "https://www.pexels.com/license/",
               "pixabay": "https://pixabay.com/service/license-summary/"}[provider]
        return Rights(status="usable", basis=f"{provider.title()} 라이선스: 상업 이용·변형 허용, 출처 표기 권장",
                      confidence=0.9, license_key=provider, license_url=url, label=provider.title())
    norm, label = _cc(code, version)
    if not norm:
        return Rights(status="unknown", basis="라이선스 표기를 확인할 수 없음", license_url=license_url)
    if norm in ("cc0", "zero"):
        return Rights(status="usable", basis="CC0: 권리 포기, 상업 이용·변형 허용", confidence=1.0,
                      license_key="cc0", license_url=license_url or "https://creativecommons.org/publicdomain/zero/1.0/",
                      label="CC0")
    if norm in ("pdm", "pd", "public domain", "publicdomain") or "public domain" in norm:
        return Rights(status="usable", basis="퍼블릭 도메인 표기: 상업 이용·변형 허용", confidence=0.95,
                      license_key="public_domain",
                      license_url=license_url or "https://creativecommons.org/publicdomain/mark/1.0/",
                      label="Public Domain")
    parts = {p for p in re.split(r"[- ]+", norm) if p and not re.fullmatch(r"[0-9.]+", p)}
    if "nc" in parts:
        return Rights(status="reference_only", basis=f"{label}: 비상업 조건이라 화면 사용 제외", license_url=license_url,
                      label=label)
    if "nd" in parts:
        return Rights(status="reference_only", basis=f"{label}: 변경 금지 조건(자르기·자막 불가)이라 화면 사용 제외",
                      license_url=license_url, label=label)
    if "sa" in parts:
        return Rights(status="reference_only", basis=f"{label}: 동일조건변경허락이 영상 전체에 걸릴 수 있어 자동 사용 제외",
                      license_url=license_url, label=label)
    if parts == {"by"}:
        return Rights(status="usable", basis=f"{label}: 출처 표기 조건으로 상업 이용·변형 허용", confidence=0.85,
                      license_key="cc_by", license_url=license_url or "https://creativecommons.org/licenses/by/4.0/",
                      label=label)
    return Rights(status="unknown", basis=f"알 수 없는 라이선스 표기({code})", license_url=license_url)


def classify_youtube(info: dict[str, Any] | None) -> dict[str, str]:
    """YouTube 링크의 권리 상태. 공개 영상이라는 이유만으로 usable 이 아니다."""
    if not info:
        return {"rights_status": "unknown", "usage": "reference_only",
                "rights_basis": "영상 정보를 확인하지 못해 권리 상태를 알 수 없음 — 내용 참고만"}
    lic = str(info.get("license") or "")
    if "creative commons" in lic.lower():
        return {"rights_status": "reference_only", "usage": "reference_only", "license_label": "CC BY (YouTube)",
                "rights_basis": "YouTube 표기상 CC BY(재사용 허용)지만 YouTube 약관상 자동 다운로드를 지원하지 않아 "
                                "화면 소스로 쓰지 않음. 쓰려면 원본 파일을 직접 제공"}
    if lic:
        return {"rights_status": "reference_only", "usage": "reference_only",
                "rights_basis": f"YouTube 표준 라이선스({lic[:40]}) — 내용·구조 분석만, 화면에 쓰지 않음"}
    return {"rights_status": "reference_only", "usage": "reference_only",
            "rights_basis": "재사용 라이선스 표기가 없는 YouTube 영상 — 내용·구조 분석만, 화면에 쓰지 않음"}


# ---------- discover (공개 API) ----------

def _strip(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


class Discoverer:
    """제공처 검색. 각 검색은 실패해도 빈 목록이다 (다음 제공처로 넘어간다)."""

    def __init__(self, client: httpx.AsyncClient, cfg: dict[str, Any], log: Callable[[str], None]):
        self.client, self.cfg, self.log = client, cfg, log
        self.cache: dict[tuple, list[VisualCandidate]] = {}
        self.errors: list[str] = []

    def enabled(self) -> list[str]:
        out = []
        for p in self.cfg["providers"]:
            if p == "pexels" and not env("PEXELS_API_KEY"):
                continue
            if p == "pixabay" and not env("PIXABAY_API_KEY"):
                continue
            out.append(p)
        return out

    async def search(self, provider: str, media: str, query: str) -> list[VisualCandidate]:
        key = (provider, media, query.lower())
        if key in self.cache:
            return self.cache[key]
        fn = getattr(self, f"_{provider}", None)
        found: list[VisualCandidate] = []
        if fn and query.strip():
            try:
                found = await fn(media, query.strip(), int(self.cfg["per_query"]))
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"{provider}/{media}: {safe_error(e)[:120]}")
        for c in found:
            c.query = query
        self.cache[key] = found
        return found

    async def _openverse(self, media: str, q: str, n: int) -> list[VisualCandidate]:
        if media != "image":
            return []
        r = await self.client.get("https://api.openverse.org/v1/images/",
                                  params={"q": q, "license": "cc0,pdm,by", "page_size": n, "mature": "false"})
        r.raise_for_status()
        out = []
        for x in r.json().get("results", []):
            rights = classify_license(x.get("license", ""), version=x.get("license_version") or "",
                                      license_url=x.get("license_url") or "")
            out.append(VisualCandidate(
                id=f"ov:{x['id']}", provider="openverse", media_type="image", title=x.get("title") or "",
                description=", ".join(t.get("name", "") for t in (x.get("tags") or [])[:8]),
                page_url=x.get("foreign_landing_url") or "", file_url=x.get("url") or "",
                width=int(x.get("width") or 0), height=int(x.get("height") or 0), creator=x.get("creator") or "",
                rights=rights, extra={"source": x.get("source", "")}))
        return out

    async def _wikimedia_commons(self, media: str, q: str, n: int) -> list[VisualCandidate]:
        ftype = "bitmap" if media == "image" else "video"
        params = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                  "gsrsearch": f"{q} filetype:{ftype}", "gsrlimit": n}
        if media == "image":
            params.update(prop="imageinfo", iiprop="url|size|mime|extmetadata", iiurlwidth=1280)
        else:
            params.update(prop="videoinfo", viprop="url|size|mime|extmetadata|derivatives")
        r = await self.client.get("https://commons.wikimedia.org/w/api.php", params=params)
        r.raise_for_status()
        out = []
        for p in (r.json().get("query") or {}).get("pages", {}).values():
            info = (p.get("imageinfo") or p.get("videoinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            val = lambda k: str((meta.get(k) or {}).get("value") or "")  # noqa: E731
            if val("NonFree").lower() in ("true", "1"):
                continue
            rights = classify_license(val("License") or val("LicenseShortName"),
                                      license_url=val("LicenseUrl"), restrictions=_strip(val("Restrictions")))
            file_url = info.get("thumburl") or info.get("url") or ""
            size = int(info.get("size") or 0)
            if media == "video":
                derivs = sorted((d for d in info.get("derivatives") or [] if str(d.get("type", "")).startswith("video/")
                                 and 360 <= int(d.get("height") or 0) <= 1080),
                                key=lambda d: abs(int(d.get("height") or 0) - 720))
                if derivs:
                    file_url = derivs[0].get("src") or file_url
                    size = 0
            out.append(VisualCandidate(
                id=f"wc:{p.get('pageid')}", provider="wikimedia_commons", media_type=media,
                title=p.get("title", "").removeprefix("File:"), description=_strip(val("ImageDescription"))[:300],
                page_url=info.get("descriptionurl") or "", file_url=file_url,
                width=int(info.get("thumbwidth") or info.get("width") or 0),
                height=int(info.get("thumbheight") or info.get("height") or 0),
                duration=float(info.get("duration") or 0), date=_strip(val("DateTimeOriginal"))[:20],
                creator=_strip(val("Artist"))[:60], rights=rights, extra={"size": size}))
        return out

    async def _nasa(self, media: str, q: str, n: int) -> list[VisualCandidate]:
        r = await self.client.get("https://images-api.nasa.gov/search",
                                  params={"q": q, "media_type": media, "page_size": max(n, 4)})
        r.raise_for_status()
        out = []
        for it in r.json().get("collection", {}).get("items", [])[:n]:
            d = (it.get("data") or [{}])[0]
            desc = d.get("description") or ""
            marker = bool(re.search(r"©|\(c\)\s|copyright", f"{desc} {d.get('secondary_creator', '')}", re.I))
            preview = next((link.get("href", "") for link in it.get("links") or [] if link.get("render") == "image"), "")
            out.append(VisualCandidate(
                id=f"nasa:{d.get('nasa_id')}", provider="nasa", media_type=media, title=d.get("title", ""),
                description=_strip(desc)[:300],
                page_url=f"https://images.nasa.gov/details/{d.get('nasa_id')}", file_url=preview,
                date=(d.get("date_created") or "")[:10], creator=d.get("center") or "NASA",
                rights=classify_license("", provider="nasa", copyright_marker=marker),
                extra={"nasa_id": d.get("nasa_id"), "manifest": it.get("href", "")}))
        return out

    async def _pexels(self, media: str, q: str, n: int) -> list[VisualCandidate]:
        url = "https://api.pexels.com/v1/search" if media == "image" else "https://api.pexels.com/videos/search"
        r = await self.client.get(url, params={"query": q, "per_page": n, "orientation": "portrait"},
                                  headers={"Authorization": env("PEXELS_API_KEY")})
        r.raise_for_status()
        out = []
        rights = classify_license("", provider="pexels")
        for x in r.json().get("photos" if media == "image" else "videos", []):
            if media == "image":
                file_url, w, h, who = x["src"].get("large2x") or x["src"]["original"], x["width"], x["height"], x.get("photographer", "")
                dur = 0.0
            else:
                files = sorted((f for f in x.get("video_files", []) if f.get("file_type") == "video/mp4"
                                and 720 <= int(f.get("height") or 0) <= 1920), key=lambda f: int(f.get("height") or 0))
                if not files:
                    continue
                file_url, w, h, who = files[0]["link"], files[0]["width"], files[0]["height"], (x.get("user") or {}).get("name", "")
                dur = float(x.get("duration") or 0)
            out.append(VisualCandidate(id=f"px:{media}:{x['id']}", provider="pexels", media_type=media,
                                       title=x.get("alt") or q, page_url=x.get("url", ""), file_url=file_url,
                                       width=int(w), height=int(h), duration=dur, creator=who, rights=rights))
        return out

    async def _pixabay(self, media: str, q: str, n: int) -> list[VisualCandidate]:
        url = "https://pixabay.com/api/" if media == "image" else "https://pixabay.com/api/videos/"
        r = await self.client.get(url, params={"key": env("PIXABAY_API_KEY"), "q": q, "per_page": max(3, n),
                                               "safesearch": "true"})
        r.raise_for_status()
        out = []
        rights = classify_license("", provider="pixabay")
        for x in r.json().get("hits", []):
            if media == "image":
                file_url, w, h, dur = x.get("largeImageURL", ""), x.get("imageWidth", 0), x.get("imageHeight", 0), 0.0
            else:
                v = (x.get("videos") or {}).get("medium") or {}
                file_url, w, h, dur = v.get("url", ""), v.get("width", 0), v.get("height", 0), float(x.get("duration") or 0)
            if not file_url:
                continue
            out.append(VisualCandidate(id=f"pb:{media}:{x['id']}", provider="pixabay", media_type=media,
                                       title=x.get("tags", q), page_url=x.get("pageURL", ""), file_url=file_url,
                                       width=int(w), height=int(h), duration=dur, creator=x.get("user", ""),
                                       rights=rights))
        return out


# ---------- 검색어 계획 / 적합도 (AI) ----------

QUERY_SYSTEM = """당신은 쇼츠 영상의 자료 조사 담당입니다. 장면마다 화면에 쓸 실제 사진·영상을 공개 아카이브
(Openverse, Wikimedia Commons, NASA 등)에서 찾을 영어 검색어를 정합니다.
- 검색어는 그 아카이브에 실제로 있을 법한 구체적인 사물·장소·현상 2~4단어 (예: 'Titanic ship 1912', 'robot arm factory').
- 실존 인물의 얼굴을 찾는 검색어는 피한다. 브랜드 로고·제품 광고 이미지도 피한다.
- 질문·결론처럼 글자로 보여 주는 게 나은 장면은 prefer=card.
- 장면이 비유·은유(예: '책상 옆 서가', '고속도로')로 설명하면 비유 대상을 찾지 말고 prefer=card.
  화면은 나레이션이 실제로 말하는 대상(사물·장소·현상)을 그대로 보여 줄 때만 찾는다.
- 모든 장면을 빠짐없이 다룬다."""

FIT_SYSTEM = """당신은 쇼츠 편집자입니다. 장면마다 찾은 공개 자료 후보가 그 장면에 맞는지 평가합니다.
- visual_fit: 나레이션·must_show 와 화면 내용이 맞는 정도 (0~10). 제목·설명으로 판단할 수 없으면 낮게.
- evidence_fit: 장면이 말하는 사실을 화면이 실제로 보여 주는 정도 (0~10). 분위기만 맞으면 3~5.
- 관련 없는 동명이인·다른 사건·다른 사물이면 0~2.
- 나레이션이 실제로 말하는 대상을 기준으로 판단한다. 비유 대상만 보여 주는 자료는 4 이하.
- 시대가 다른 자료(현대 기술 이야기에 옛날 판화·문서 스캔 등)와 글자가 많은 문서 스캔은 4 이하.
- 모든 후보를 평가한다."""


def _rule_queries(script: Any, topic: str) -> QueryPlan:
    out = []
    for i, s in enumerate(script.scenes):
        words = re.findall(r"[A-Za-z][A-Za-z-]{2,}", s.image_prompt or "")
        stop = {"style", "photo", "realistic", "illustration", "cinematic", "text", "with", "and", "the", "no",
                "high", "quality", "detailed", "vertical", "shot", "lighting", "background"}
        q = " ".join([w for w in words if w.lower() not in stop][:3])
        out.append(SceneQuery(scene_index=i, query_en=q or topic, prefer="image", must_show=s.narration[:60]))
    return QueryPlan(scenes=out)


async def plan_queries(llm: dict[str, Any], script: Any, topic: str, spec: dict[str, Any] | None,
                       skip: set[int]) -> tuple[QueryPlan, str]:
    roles = [getattr(s, "beat_role", "") for s in script.scenes]
    listing = "\n".join(f"{i}. [{roles[i] or '-'}] {s.narration} (화면 키워드: {s.on_screen_text})"
                        for i, s in enumerate(script.scenes) if i not in skip)
    hint = f"[구조 화면 지침] {spec.get('visual_hint', '')} / 우선 자료: {', '.join(spec.get('visual_priority', []))}" if spec else ""
    user = f"[주제] {topic}\n{hint}\n[장면]\n{listing}"
    try:
        plan = await ask_structured(llm, QUERY_SYSTEM, user, QueryPlan)
        got = {q.scene_index for q in plan.scenes}
        rule = _rule_queries(script, topic)
        plan.scenes += [q for q in rule.scenes if q.scene_index not in got]
        return plan, "ai"
    except Exception:  # noqa: BLE001 - 검색어만 규칙으로 만들고 계속한다
        return _rule_queries(script, topic), "rules"


async def rate_fit(llm: dict[str, Any], script: Any, queries: dict[int, SceneQuery],
                   by_scene: dict[int, list[VisualCandidate]]) -> tuple[dict[str, FitScore], str]:
    blocks = []
    for i, cands in by_scene.items():
        if not cands:
            continue
        q = queries.get(i)
        rows = "\n".join(f"  - id={c.id} [{c.media_type}] {c.title[:80]} | {c.description[:140]} | {c.date}"
                         for c in cands)
        blocks.append(f"장면 {i}: {script.scenes[i].narration}\n  must_show: {q.must_show if q else ''}\n{rows}")
    if not blocks:
        return {}, "none"
    try:
        plan = await ask_structured(llm, FIT_SYSTEM, "\n\n".join(blocks), FitPlan)
        return {f.candidate_id: f for f in plan.scores}, "ai"
    except Exception:  # noqa: BLE001 - AI 가 없으면 제목·설명과 검색어가 겹치는 정도로 대신한다
        out = {}
        for i, cands in by_scene.items():
            q = queries.get(i)
            keys = set(re.findall(r"[a-z]{3,}", f"{q.query_en if q else ''}".lower()))
            for c in cands:
                text = f"{c.title} {c.description}".lower()
                hit = sum(1 for k in keys if k in text)
                score = min(10, 3 + 2 * hit) if keys else 4
                out[c.id] = FitScore(candidate_id=c.id, visual_fit=score, evidence_fit=max(0, score - 3),
                                     reason="AI 평가 없이 검색어 일치로 추정")
        return out, "rules"


# ---------- 점수 ----------

def score_candidate(c: VisualCandidate, fit: FitScore | None, need: float, *, fresh_matters: bool = False,
                    today: dt.date | None = None) -> dict[str, Any]:
    """0~100 내부 점수. 조회수 예측이 아니라 이 장면에 쓸 화면으로서의 적합도다."""
    today = today or dt.date.today()
    visual = max(0, min(10, fit.visual_fit if fit else 0)) / 10
    evidence = max(0, min(10, fit.evidence_fit if fit else 0)) / 10
    w, h = c.width, c.height
    if w and h:
        # 9:16 으로 꽉 채우려면 세로 1920 근처가 필요하다. 가로 영상은 흐린 배경 위에 원본 전체를 놓으므로 가로 1080 기준.
        pixels = h / 1920 if h >= w else w / 1080
        quality = max(0.2, min(1.0, pixels))
    else:
        quality = 0.5
    fresh = 0.6
    if fresh_matters and c.date[:4].isdigit():
        age = today.year - int(c.date[:4])
        fresh = 1.0 if age <= 1 else 0.7 if age <= 3 else 0.4
    rights = c.rights.confidence if c.rights.status == "usable" else 0.0
    if c.media_type == "video":
        if c.duration and c.duration < need * 0.6:
            edit = 0.3
        elif c.duration and c.duration > 900:
            edit = 0.5
        else:
            edit = 0.9 if not w or h >= w * 0.9 else 0.75
    else:
        edit = 0.9 if (not w or h >= w) else 0.75
    parts = {"visual_fit": visual, "evidence_fit": evidence, "quality": quality, "freshness": fresh,
             "rights_confidence": rights, "editability": edit}
    total = round(sum(WEIGHTS[k] * v for k, v in parts.items()))
    return {"total": total, "parts": {k: round(v * WEIGHTS[k]) for k, v in parts.items()},
            "reason": fit.reason if fit else ""}


def choose(by_scene: dict[int, list[VisualCandidate]], scores: dict[str, dict[str, Any]],
           fits: dict[str, FitScore], queries: dict[int, SceneQuery], priority: list[str], *,
           min_score: int, min_visual_fit: int) -> dict[int, VisualCandidate]:
    """장면마다 권리 usable + 점수 기준을 넘는 최고 후보. 같은 자료를 두 장면에 쓰지 않는다."""
    bonus = {kind: (8 if i == 0 else 3) for i, kind in enumerate(priority)}
    ranked: list[tuple[float, int, VisualCandidate]] = []
    for i, cands in by_scene.items():
        q = queries.get(i)
        for c in cands:
            if c.rights.status != "usable":
                continue
            fit = fits.get(c.id)
            if not fit or fit.visual_fit < min_visual_fit:
                continue
            total = scores[c.id]["total"]
            if total < min_score:
                continue
            pref = 4 if q and q.prefer == c.media_type else 0
            ranked.append((total + bonus.get(c.media_type, 0) + pref, i, c))
    ranked.sort(key=lambda r: -r[0])
    picked: dict[int, VisualCandidate] = {}
    used: set[str] = set()
    for _, i, c in ranked:
        if i in picked or c.id in used:
            continue
        picked[i] = c
        used.add(c.id)
    return picked


# ---------- ingest ----------

async def _nasa_files(client: httpx.AsyncClient, c: VisualCandidate) -> tuple[str, str]:
    """NASA 자산 목록에서 알맞은 파일과 자막(.srt) 주소."""
    r = await client.get(c.extra.get("manifest") or f"https://images-api.nasa.gov/asset/{c.extra['nasa_id']}")
    r.raise_for_status()
    data = r.json()
    hrefs = [x if isinstance(x, str) else x.get("href", "") for x in
             (data if isinstance(data, list) else data.get("collection", {}).get("items", []))]
    order = ("~mobile.mp4", "~medium.mp4", "~small.mp4") if c.media_type == "video" else ("~large.jpg", "~medium.jpg", "~orig.jpg")
    file_url = next((h for suffix in order for h in hrefs if h.endswith(suffix)), "")
    srt = next((h for h in hrefs if h.endswith(".srt")), "")
    return file_url.replace("http://", "https://"), srt.replace("http://", "https://")


async def ingest(client: httpx.AsyncClient, c: VisualCandidate, dest_dir: Path, max_mb: int) -> tuple[Path, str]:
    """usable 로 판정된 후보만 내려받는다. (파일, 자막 텍스트)"""
    if c.rights.status != "usable":
        raise ValueError("usable 이 아닌 자료는 내려받지 않습니다")
    srt_text = ""
    url = c.file_url
    if c.provider == "nasa":
        url, srt = await _nasa_files(client, c)
        if srt:
            try:
                srt_text = (await client.get(srt)).text
            except Exception:  # noqa: BLE001
                srt_text = ""
    if not url.startswith("https://"):
        raise ValueError("내려받을 주소가 없습니다")
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(url.split("?")[0]).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm", ".ogv", ".mov"):
        ext = ".mp4" if c.media_type == "video" else ".jpg"
    safe = re.sub(r"[^A-Za-z0-9]+", "_", c.id)[:60]
    out = dest_dir / f"{safe}{ext}"
    limit = max_mb * 1024 * 1024
    async with client.stream("GET", url) as r:
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if not (ctype.startswith("image/") or ctype.startswith("video/") or ctype.startswith("application/octet")):
            raise ValueError(f"미디어 파일이 아닙니다 ({ctype})")
        if int(r.headers.get("content-length") or 0) > limit:
            raise ValueError(f"파일이 너무 큽니다 (>{max_mb}MB)")
        size = 0
        with out.open("wb") as f:
            async for chunk in r.aiter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ValueError(f"파일이 너무 큽니다 (>{max_mb}MB)")
                f.write(chunk)
    if out.stat().st_size < 1024:
        out.unlink(missing_ok=True)
        raise ValueError("내려받은 파일이 비어 있습니다")
    return out, srt_text


def _check_media(path: Path, media: str) -> None:
    if media == "image":
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
    else:
        from .media import probe_duration_sync
        if probe_duration_sync(path) <= 0.5:
            raise ValueError("영상 길이가 너무 짧습니다")


# ---------- 전체 ----------

def settings(cfg: dict[str, Any]) -> dict[str, Any]:
    return {**DEFAULTS, **(cfg.get("sources") or {})}


def user_agent(cfg: dict[str, Any]) -> str:
    contact = settings(cfg).get("contact") or ""
    return f"AIShortsFactory/1.0 ({contact + '; ' if contact else ''}personal shorts tool; python-httpx)"


async def resolve(*, llm: dict[str, Any], script: Any, topic: str, durations: list[float], job_dir: Path,
                  registry: Any, cfg: dict[str, Any], profile_spec: dict[str, Any] | None = None,
                  fresh_matters: bool = False, skip: set[int] | None = None,
                  progress: Progress = lambda *a: None) -> dict[str, Any]:
    """장면 → 실제 자료. 반환: {"scenes": {i: {...}}, "report": {...}} (report 는 source_plan.json 에도 저장)."""
    st = settings(cfg)
    skip = set(skip or set())
    card_roles = set((profile_spec or {}).get("card_roles", ["ending_question"]))
    for i, s in enumerate(script.scenes):
        if getattr(s, "beat_role", "") in card_roles:
            skip.add(i)
    priority = list((profile_spec or {}).get("visual_priority", ["image", "video"]))
    report: dict[str, Any] = {"providers": [], "query_method": "", "fit_method": "", "scenes": [], "errors": [],
                              "skipped_scenes": sorted(skip), "note": "점수는 장면 화면 적합도 내부 값이며 조회수 예측이 아님"}
    log = lambda m: progress("images", 40, m)  # noqa: E731
    async with httpx.AsyncClient(headers={"User-Agent": user_agent(cfg)}, timeout=30, follow_redirects=True) as client:
        disc = Discoverer(client, st, log)
        providers = disc.enabled()
        report["providers"] = providers
        if not providers:
            return {"scenes": {}, "report": {**report, "errors": ["사용 가능한 자료 제공처가 없습니다"]}}
        progress("images", 32, "장면별 자료 검색어 정하는 중")
        qplan, report["query_method"] = await plan_queries(llm, script, topic, profile_spec, skip)
        queries = {q.scene_index: q for q in qplan.scenes if 0 <= q.scene_index < len(script.scenes)
                   and q.scene_index not in skip}
        for i, q in queries.items():
            if q.prefer == "card":
                skip.add(i)
        queries = {i: q for i, q in queries.items() if i not in skip}
        sem = asyncio.Semaphore(4)

        async def one(provider: str, media: str, query: str) -> list[VisualCandidate]:
            async with sem:
                return await disc.search(provider, media, query)

        progress("images", 36, f"공개 자료 검색 중 ({', '.join(providers)})")
        by_scene: dict[int, list[VisualCandidate]] = {}
        for i, q in queries.items():
            medias = [m for m in priority if m in ("video", "image")] or ["image"]
            jobs = [one(p, m, q.query_en) for p in providers for m in medias]
            results = await asyncio.gather(*jobs)
            cands = [c for group in results for c in group]
            if len([c for c in cands if c.rights.status == "usable"]) < 2 and q.alt_query_en:
                results = await asyncio.gather(*[one(p, m, q.alt_query_en) for p in providers for m in medias])
                cands += [c for group in results for c in group]
            seen: set[str] = set()
            uniq = [c for c in cands if not (c.id in seen or seen.add(c.id))]
            # usable 을 앞에, 제공처를 섞어서 평가 대상 수를 제한한다
            uniq.sort(key=lambda c: (c.rights.status != "usable", -c.rights.confidence))
            by_scene[i] = uniq[: int(st["max_candidates_per_scene"])]
            report["scenes"].append({"scene": i + 1, "query": q.query_en, "alt_query": q.alt_query_en,
                                     "prefer": q.prefer, "must_show": q.must_show,
                                     "found": len(uniq), "usable": sum(c.rights.status == "usable" for c in uniq),
                                     "reference_only_or_unknown": [
                                         {"title": c.title[:60], "provider": c.provider, "rights_status": c.rights.status,
                                          "basis": c.rights.basis, "url": c.page_url}
                                         for c in uniq if c.rights.status != "usable"][:4]})
        report["errors"] = disc.errors
        usable_by_scene = {i: [c for c in cs if c.rights.status == "usable"] for i, cs in by_scene.items()}
        progress("images", 44, "자료 후보가 장면과 맞는지 평가하는 중")
        fits, report["fit_method"] = await rate_fit(llm, script, queries, usable_by_scene)
        scores = {c.id: score_candidate(c, fits.get(c.id), durations[i] if i < len(durations) else 4.0,
                                        fresh_matters=fresh_matters)
                  for i, cs in usable_by_scene.items() for c in cs}
        for entry in report["scenes"]:
            i = entry["scene"] - 1
            entry["candidates"] = sorted(
                [{"id": c.id, "provider": c.provider, "type": c.media_type, "title": c.title[:80], "url": c.page_url,
                  "rights_status": c.rights.status, "rights_basis": c.rights.basis,
                  "visual_fit": fits[c.id].visual_fit if c.id in fits else None,
                  "evidence_fit": fits[c.id].evidence_fit if c.id in fits else None,
                  **scores.get(c.id, {})} for c in usable_by_scene.get(i, [])],
                key=lambda x: -(x.get("total") or 0))
        picked = choose(usable_by_scene, scores, fits, queries, priority,
                        min_score=int(st["min_score"]), min_visual_fit=int(st["min_visual_fit"]))
        out: dict[int, dict[str, Any]] = {}
        for i, c in sorted(picked.items()):
            need = durations[i] if i < len(durations) else 4.0
            try:
                progress("images", 48, f"장면 {i + 1} 자료 내려받는 중: {c.title[:40]} ({c.rights.label or c.rights.license_key})")
                path, srt = await ingest(client, c, job_dir / "sources", int(st["max_file_mb"]))
                await asyncio.to_thread(_check_media, path, c.media_type)
            except Exception as e:  # noqa: BLE001 - 이 자료를 못 쓰면 카드로 대체된다
                report["errors"].append(f"장면 {i + 1} ingest 실패 ({c.id}): {safe_error(e)[:120]}")
                continue
            registry.add(kind=c.media_type, origin="resolved", path=str(path), url=c.page_url, title=c.title[:120],
                         used_for=f"scene_{i:02d}", source_type=c.provider,
                         rights={"license": c.rights.license_key, "license_url": c.rights.license_url,
                                 "rights_confirmed": True, "commercial_allowed": True, "adaptation_allowed": True,
                                 "third_party_rights_checked": True, "credit": c.credit(),
                                 "license_note": f"자동 판정: {c.rights.basis}",
                                 "rights_basis": c.rights.basis})
            item = registry.by_path(path)
            if not item or not item.usable_in_video:
                report["errors"].append(f"장면 {i + 1}: 소스 대장이 사용 불가로 판정 ({c.id})")
                continue
            entry: dict[str, Any] = {"kind": c.media_type, "path": str(path), "credit": c.credit(),
                                     "candidate_id": c.id, "page_url": c.page_url, "score": scores[c.id]["total"],
                                     "reason": f"{c.provider} {c.rights.label or c.rights.license_key} · "
                                               f"점수 {scores[c.id]['total']} · {scores[c.id]['reason']}"}
            if c.media_type == "video":
                q = queries.get(i)
                words = clip_analyzer.parse_srt(srt) if srt else None
                try:
                    analysis = await clip_analyzer.analyze(path, need, keywords=(q.keywords_en if q else []) + ([q.query_en] if q else []),
                                                           transcript=words)
                except Exception as e:  # noqa: BLE001
                    report["errors"].append(f"장면 {i + 1} 클립 분석 실패: {safe_error(e)[:120]}")
                    continue
                rec = analysis.recommended
                if not rec:
                    continue
                entry.update(start=rec.start, end=rec.end, clip_range=rec.label,
                             clip_candidates=[{"range": c2.label, "score": c2.score, "reason": c2.reason}
                                              for c2 in analysis.candidates],
                             shots=len(analysis.shots), has_transcript=analysis.has_transcript)
                entry["reason"] += f" · 구간 {rec.label} ({rec.reason})"
            out[i] = entry
        report["selected"] = {str(i + 1): {k: v for k, v in e.items() if k != "path"} for i, e in out.items()}
    (job_dir / PLAN_FILE).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"scenes": out, "report": report}
