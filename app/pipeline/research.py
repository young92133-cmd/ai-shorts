"""주제 리서치: 네이버 뉴스 API(선택) + DuckDuckGo 검색 + 본문 추출, Google Trends RSS."""
from __future__ import annotations

import asyncio
import html
import re
import xml.etree.ElementTree as ET

import httpx

from ..config import env
from .models import ResearchDoc

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"


def _strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


async def naver_news(query: str, n: int = 8) -> list[ResearchDoc]:
    cid, secret = env("NAVER_CLIENT_ID"), env("NAVER_CLIENT_SECRET")
    if not (cid and secret):
        return []
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            "https://openapi.naver.com/v1/search/news.json",
            params={"query": query, "display": n, "sort": "date"},
            headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret},
        )
        r.raise_for_status()
    return [
        ResearchDoc(title=_strip_tags(it["title"]), url=it.get("originallink") or it["link"],
                    text=_strip_tags(it.get("description", "")), published=it.get("pubDate", ""))
        for it in r.json().get("items", [])
    ]


def _ddg_sync(query: str, n: int) -> list[ResearchDoc]:
    from ddgs import DDGS

    docs: list[ResearchDoc] = []
    try:
        with DDGS() as d:
            for it in d.news(query, region="kr-kr", max_results=n) or []:
                docs.append(ResearchDoc(title=it.get("title", ""), url=it.get("url", ""),
                                        text=it.get("body", ""), published=it.get("date", "")))
    except Exception:
        pass
    if len(docs) < 3:
        try:
            with DDGS() as d:
                for it in d.text(query, region="kr-kr", max_results=n) or []:
                    docs.append(ResearchDoc(title=it.get("title", ""), url=it.get("href", ""), text=it.get("body", "")))
        except Exception:
            pass
    return docs


def _extract_sync(url: str) -> str:
    import trafilatura

    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        return trafilatura.extract(downloaded, include_comments=False, include_tables=False) or ""
    except Exception:
        return ""


async def research_topic(query: str, max_docs: int = 6, log=print) -> list[ResearchDoc]:
    """검색 결과를 모으고 본문을 채워 돌려준다. 실패해도 예외 대신 빈 목록."""
    docs: list[ResearchDoc] = []
    try:
        docs += await naver_news(query, max_docs)
    except Exception as e:
        log(f"네이버 뉴스 검색 실패: {e}")
    if len(docs) < max_docs:
        docs += await asyncio.to_thread(_ddg_sync, query, max_docs)

    # URL 중복 제거
    seen: set[str] = set()
    uniq = []
    for d in docs:
        if d.url and d.url not in seen:
            seen.add(d.url)
            uniq.append(d)
    uniq = uniq[:max_docs]

    # 본문 추출 (병렬)
    bodies = await asyncio.gather(*(asyncio.to_thread(_extract_sync, d.url) for d in uniq))
    for d, body in zip(uniq, bodies):
        if body and len(body) > len(d.text):
            d.text = body
    log(f"리서치 자료 {len(uniq)}건 수집")
    return uniq


async def google_trends_kr(n: int = 20) -> list[str]:
    """Google Trends 일간 급상승 검색어 (비공식 RSS)."""
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": UA}) as c:
        r = await c.get("https://trends.google.com/trending/rss", params={"geo": "KR"})
        r.raise_for_status()
    root = ET.fromstring(r.text)
    out: list[str] = []
    for item in root.iter("item"):
        title = item.findtext("title")
        if title:
            out.append(title.strip())
        if len(out) >= n:
            break
    return out


async def naver_news_headlines(n: int = 20) -> list[str]:
    """네이버 뉴스 '많이 본 뉴스' 제목 (트렌드 RSS 실패 시 대체)."""
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": UA}) as c:
        r = await c.get("https://news.naver.com/main/ranking/popularDay.naver")
        r.raise_for_status()
    titles = re.findall(r'class="list_title"[^>]*>([^<]+)<', r.text)
    return [html.unescape(t).strip() for t in titles[:n]]


async def hot_keywords(log=print) -> list[str]:
    for fn in (google_trends_kr, naver_news_headlines):
        try:
            kws = await fn()
            if kws:
                log(f"{fn.__name__}: {len(kws)}개 키워드")
                return kws
        except Exception as e:
            log(f"{fn.__name__} 실패: {e}")
    return []
