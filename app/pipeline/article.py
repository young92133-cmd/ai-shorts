"""기사·커뮤니티 글 링크 분석: 본문 추출 + 이미지 수집.

유튜브가 아닌 URL 을 받으면 여기로 온다. 본문은 리서치 자료로, 이미지는 장면 비주얼로 쓴다.
기사 이미지는 저작권이 있으므로 항상 출처를 함께 기록한다.
"""
from __future__ import annotations

import asyncio
import html
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from .models import ResearchDoc, SourcedImage

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
                 "music.youtube.com", "www.youtube-nocookie.com"}

# 로고·아이콘·추적 픽셀 등 본문과 무관한 이미지
SKIP_PATTERNS = re.compile(
    r"(logo|icon|favicon|sprite|banner|badge|avatar|profile|btn_|button|blank|"
    r"spacer|pixel|1x1|ad[_-]|advert|share|sns|emoticon)", re.I)

MIN_BYTES = 15_000        # 이 미만이면 썸네일·아이콘일 가능성이 큼
MAX_BYTES = 12_000_000


def is_youtube(url: str) -> bool:
    try:
        return urlparse(url).netloc.lower().lstrip("www.") in {h.lstrip("www.") for h in YOUTUBE_HOSTS}
    except Exception:  # noqa: BLE001
        return False


def is_url(text: str) -> bool:
    try:
        p = urlparse(text.strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:  # noqa: BLE001
        return False


def split_urls(text: str) -> list[str]:
    """줄바꿈/공백으로 구분된 여러 URL 을 나눈다."""
    return [t.strip() for t in re.split(r"[\s\n]+", text or "") if is_url(t)]


def site_name(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = re.sub(r"^(www|m|news|n)\.", "", host)
    return host


def _strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


# ---------- 본문 ----------

def _fetch_sync(url: str) -> tuple[str, str]:
    """(html, 최종 url) - 리다이렉트 반영."""
    with httpx.Client(timeout=25, follow_redirects=True, headers={"User-Agent": UA}) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text, str(r.url)


def _extract_body(raw_html: str, url: str) -> tuple[str, str]:
    """trafilatura 로 (제목, 본문). 실패하면 og:title + 태그 제거 텍스트."""
    try:
        import trafilatura

        text = trafilatura.extract(raw_html, url=url, include_comments=False, include_tables=False) or ""
        meta = trafilatura.extract_metadata(raw_html, default_url=url)
        title = (getattr(meta, "title", "") or "") if meta else ""
    except Exception:  # noqa: BLE001
        text, title = "", ""

    if not title:
        m = (re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', raw_html, re.I)
             or re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.I | re.S))
        title = _strip_tags(m.group(1)) if m else url
    return title, text


# ---------- 이미지 ----------

def _meta_images(raw_html: str, base_url: str) -> list[str]:
    urls: list[str] = []
    for prop in ("og:image", "og:image:url", "twitter:image", "twitter:image:src"):
        for m in re.finditer(
                rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]*content=["\']([^"\']+)["\']',
                raw_html, re.I):
            urls.append(urljoin(base_url, html.unescape(m.group(1))))
    return urls


def _body_images(raw_html: str, base_url: str) -> list[tuple[str, str]]:
    """(이미지 url, 캡션) 목록. data-src(지연로딩)도 본다."""
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"<img\b[^>]*>", raw_html, re.I):
        tag = m.group(0)
        src = ""
        for attr in ("data-src", "data-original", "data-lazy-src", "src"):
            a = re.search(rf'{attr}=["\']([^"\']+)["\']', tag, re.I)
            if a and not a.group(1).startswith("data:"):
                src = html.unescape(a.group(1))
                break
        if not src or SKIP_PATTERNS.search(src):
            continue
        # width/height 속성이 있고 작으면 버린다
        wm = re.search(r'\bwidth=["\']?(\d+)', tag, re.I)
        hm = re.search(r'\bheight=["\']?(\d+)', tag, re.I)
        if (wm and int(wm.group(1)) < 200) or (hm and int(hm.group(1)) < 200):
            continue
        alt = re.search(r'alt=["\']([^"\']*)["\']', tag, re.I)
        out.append((urljoin(base_url, src), html.unescape(alt.group(1)) if alt else ""))
    return out


def _check_image(path: Path) -> tuple[int, int] | None:
    """내려받은 파일이 쓸 만한 이미지인지. (width, height) 또는 None."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            w, h = im.size
            im.verify()
        if w < 300 or h < 300:
            return None
        if w / h > 4 or h / w > 4:   # 배너처럼 지나치게 긴 것
            return None
        return w, h
    except Exception:  # noqa: BLE001
        return None


async def _download_image(client: httpx.AsyncClient, src: str, out_dir: Path, idx: int,
                          page_url: str, caption: str) -> SourcedImage | None:
    try:
        r = await client.get(src, headers={"Referer": page_url})
        r.raise_for_status()
    except Exception:  # noqa: BLE001
        return None
    if not r.headers.get("content-type", "").startswith("image/"):
        return None
    if not (MIN_BYTES <= len(r.content) <= MAX_BYTES):
        return None

    ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(
        r.headers["content-type"].split(";")[0].strip(), ".jpg")
    path = out_dir / f"src_{idx:02d}{ext}"
    path.write_bytes(r.content)

    size = _check_image(path)
    if not size:
        path.unlink(missing_ok=True)
        return None
    return SourcedImage(path=str(path), src_url=src, page_url=page_url,
                        site=site_name(page_url), caption=caption[:120],
                        width=size[0], height=size[1])


async def collect_images(raw_html: str, page_url: str, out_dir: Path, limit: int = 12) -> list[SourcedImage]:
    """기사에서 이미지를 내려받는다. og:image 를 먼저, 그 다음 본문 순서대로."""
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[tuple[str, str]] = [(u, "") for u in _meta_images(raw_html, page_url)]
    candidates += _body_images(raw_html, page_url)

    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for src, cap in candidates:
        if src in seen or SKIP_PATTERNS.search(src):
            continue
        seen.add(src)
        uniq.append((src, cap))
        if len(uniq) >= limit * 2:   # 실패를 감안해 넉넉히
            break

    results: list[SourcedImage] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": UA}) as c:
        sem = asyncio.Semaphore(4)

        async def one(i: int, src: str, cap: str) -> SourcedImage | None:
            async with sem:
                return await _download_image(c, src, out_dir, i, page_url, cap)

        got = await asyncio.gather(*(one(i, s, cap) for i, (s, cap) in enumerate(uniq)))
    for g in got:
        if g:
            results.append(g)
        if len(results) >= limit:
            break
    return results


# ---------- 진입점 ----------

async def fetch_article(url: str, out_dir: Path, with_images: bool = True,
                        image_limit: int = 12) -> tuple[ResearchDoc, list[SourcedImage]]:
    """기사 1건을 읽어 (본문 문서, 이미지 목록) 반환."""
    raw, final_url = await asyncio.to_thread(_fetch_sync, url)
    title, text = await asyncio.to_thread(_extract_body, raw, final_url)
    doc = ResearchDoc(title=title or final_url, url=final_url, text=text)
    images: list[SourcedImage] = []
    if with_images:
        try:
            images = await collect_images(raw, final_url, out_dir, image_limit)
        except Exception:  # noqa: BLE001 - 이미지는 없어도 진행
            images = []
    return doc, images


async def fetch_articles(urls: list[str], out_dir: Path, with_images: bool = True,
                         log=print) -> tuple[list[ResearchDoc], list[SourcedImage]]:
    """여러 링크를 순서대로 읽는다. 하나가 실패해도 나머지는 계속."""
    docs: list[ResearchDoc] = []
    images: list[SourcedImage] = []
    per_article = max(3, 12 // max(1, len(urls)))
    for i, u in enumerate(urls, 1):
        log(f"링크 {i}/{len(urls)} 분석 중: {site_name(u)}")
        try:
            doc, imgs = await fetch_article(u, out_dir / f"link{i}", with_images, per_article)
        except Exception as e:  # noqa: BLE001
            log(f"링크 {i} 실패: {e}")
            continue
        if doc.text or doc.title:
            docs.append(doc)
        images.extend(imgs)
        log(f"  본문 {len(doc.text)}자, 이미지 {len(imgs)}장")
    return docs, images


def credit_line(images: list[SourcedImage]) -> str:
    """영상에 넣을 출처 문구. 여러 매체면 묶어서."""
    sites = sorted({i.site for i in images if i.site})
    if not sites:
        return ""
    if len(sites) <= 2:
        return "출처: " + ", ".join(sites)
    return f"출처: {sites[0]} 외 {len(sites) - 1}곳"
