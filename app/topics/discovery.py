"""Reuse news search and article extraction. Configured feeds use public, robots-aware access."""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from ..pipeline import research, article
from ..pipeline.sources import SourceRegistry
from ..pipeline.llm import safe_error
from .schema import Evidence, Topic, now, timestamp, CATEGORIES
from .store import Store, identifier

OFFICIAL = ('bok.or.kr', 'molit.go.kr', 'fsc.go.kr', 'fss.or.kr', 'kostat.go.kr', 'mods.go.kr', 'kosis.kr', 'reb.or.kr')
WORDS = {'housing': ('전세', '월세', '주거', '주택', '청약', '부동산', '보증금', '임대', '아파트', '집값', '매입자금'),
         'finance': ('월급', '저축', 'ETF', '연금', '재테크', '투자', '예금', '적금', '금융상품', '가계부', 'ISA', 'IRP',
                     '세액공제', '신용점수', '중금리', '신용대출')}
# 분야별 뉴스 검색어. 한 검색어당 결과가 5건 안팎이라 여러 각도로 나눠 찾는다 (config topic_strategy.queries 로 교체 가능).
QUERIES = {'housing': ('직장인 전세 월세 주거비', '전세 월세 시세 임대차', '청약 주택 공급 대책', '주택담보대출 전세대출 규제'),
           'finance': ('직장인 월급 관리 재테크 기초', '예금 적금 금리 비교', '연금 ISA 세제 혜택', '신용점수 대출 금리 직장인'),
           'economy': ('한국 경제 금리 물가 고용 발표', '한국은행 기준금리 결정', '소비자물가 상승률 통계청', '고용동향 취업자 통계청')}
# 기사·보도자료가 아닌 페이지 판별 (실데이터 수집 2026-10-08: 메뉴 제목·오류 페이지·파일·빈 본문이 후보로 들어왔다)
GENERIC_TITLE = re.compile(r'^(?:주요사이트 바로가기|알림마당|홈으로 가기|본문 바로가기|주메뉴 바로가기|MSN|KOSIS|'
                           r'KOSIS 국가통계포털|금융위원회|금융감독원|국토교통부|한국은행|한국부동산원|부동산통계정보시스템|'
                           r'통계청|보도자료|공지사항|새소식|https?://\S+)$', re.I)
FILE_URL = re.compile(r'(?:fileDownload|FileDownload|getFile|displayFile|download\.do|/api/|\.(?:pdf|hwp|hwpx|xlsx?|zip|docx?)(?:$|\?))', re.I)
ERROR_PAGE = re.compile(r'error_kor|/error|서비스\s*(?:중단|점검)|접근이\s*거부|페이지를\s*찾을\s*수\s*없', re.I)
NOT_ARTICLE_TITLE = re.compile(r'^전체\s*[\d,]+\s*건|질문과\s*답변|문의하시기|이용\s*안내|누리집입니다|시스템\s*\|')
MIN_BODY = 300


def decode(raw: bytes, header_charset: str | None) -> str:
    """헤더에 charset 이 없으면 HTML meta charset 을 본다 (EUC-KR 공공기관 페이지가 깨져 저장되던 문제)."""
    charset = header_charset
    if not charset:
        m = re.search(rb'<meta[^>]+charset=["\']?([A-Za-z0-9_-]+)', raw[:4096], re.I)
        charset = m.group(1).decode('ascii') if m else 'utf-8'
    try:
        return raw.decode(charset, errors='replace')
    except LookupError:
        return raw.decode('utf-8', errors='replace')


def headline(title: str, text: str) -> str:
    """메뉴 이름이 제목으로 잡힌 페이지는 본문의 첫 제목다운 줄을 제목으로 쓴다. 없으면 빈 문자열."""
    title = ' '.join((title or '').split())
    if title and not GENERIC_TITLE.match(title) and len(title) >= 6:
        return title
    for line in (text or '').splitlines():
        line = ' '.join(line.split()).strip(' -·|')
        if len(line) > 80:
            break           # 본문 문단이 먼저 나오면 그 아래 줄(각주·참석자 명단)은 제목이 아니다
        if (8 <= len(line) <= 80 and not line.startswith(('*', '※', '(', '[')) and
                not re.search(r'바로가기|메뉴|검색|로그인|담당부서|작성자|등록일|조회|첨부|참석자', line)):
            return line
    # 제목다운 줄이 없으면 첫 문장을 줄여 쓴다 (보도자료 본문이 바로 시작하는 기관 페이지)
    first = re.split(r'(?<=[.다])\s', ' '.join((text or '').split()), maxsplit=1)[0]
    return (first[:58] + '…') if len(first) > 60 else first


def reject_reason(e: 'Evidence') -> str:
    """기사·보도자료로 쓸 수 없는 페이지면 이유, 쓸 수 있으면 빈 문자열."""
    if FILE_URL.search(e.url) or FILE_URL.search(e.original_url or ''):
        return '파일 내려받기 주소(본문 없음)'
    if ERROR_PAGE.search(e.url) or ERROR_PAGE.search(e.title or '') or ERROR_PAGE.search((e.text or '')[:200]):
        return '오류·점검 안내 페이지'
    if len(e.text or '') < MIN_BODY:
        return f'본문 {len(e.text or "")}자 — 목록·스크립트 페이지로 기사 본문을 읽지 못함'
    lines = [ln.strip() for ln in e.text.splitlines() if ln.strip()]
    if len(lines) >= 20 and sum(len(ln) < 15 for ln in lines) / len(lines) > 0.6:
        return '메뉴·목록 페이지(짧은 링크 줄이 대부분)'
    if not e.title:
        return '제목을 확인할 수 없는 페이지'
    if NOT_ARTICLE_TITLE.search(e.title):
        return '게시판 목록·안내 페이지'
    return ''


def official(url: str, domains=OFFICIAL) -> bool:
    host = (urlsplit(url).hostname or '').lower()
    return any(host == d or host.endswith('.' + d) for d in domains)


def canonical(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), p.query, ''))


def category(title: str) -> str:
    for cat, words in WORDS.items():
        if any(w.lower() in title.lower() for w in words):
            return cat
    return 'economy'


def freshness(title: str, cat: str) -> str:
    stable = re.search(r'기초|개념|월급\s*관리|가계부|비상금', title)
    changing = re.search(r'오늘|최근|발표|개정|정책|세금|세율|금리|지원금|20\d{2}', title)
    return 'evergreen' if cat != 'economy' and stable and not changing else 'current'


def publisher(url: str) -> str:
    host = (urlsplit(url).hostname or '').lower().removeprefix('www.')
    parts = host.split('.')
    return '.'.join(parts[-3:]) if len(parts) >= 3 and parts[-2] in ('co', 'or', 'go', 'ac') else '.'.join(parts[-2:])


async def public_url(url: str) -> None:
    p = urlsplit(url)
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
        raise ValueError('공개 HTTP(S) 주소만 지원합니다')
    addresses = await asyncio.to_thread(socket.getaddrinfo, p.hostname, p.port or (443 if p.scheme == 'https' else 80))
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('비공개 네트워크 주소는 수집하지 않습니다')


async def _get(client: httpx.AsyncClient, url: str, max_bytes=2_000_000, allowed=None):
    for _ in range(5):
        if allowed is not None and not allowed(url):
            raise ValueError('이동한 경로의 robots/공개 접근 제한')
        await public_url(url)
        async with client.stream('GET', url) as response:
            if response.is_redirect:
                url = str(response.url.join(response.headers['location']))
                continue
            response.raise_for_status()
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError('자료 크기 제한 초과')
                chunks.append(chunk)
            return decode(b''.join(chunks), response.charset_encoding), str(response.url)
    raise ValueError('리다이렉트 제한 초과')


async def fetch_public(url: str) -> tuple[str, str]:
    await public_url(url)
    p = urlsplit(url)
    async with httpx.AsyncClient(timeout=20, headers={'User-Agent': 'TopicStrategyBot/1.0'}) as client:
        robots_url = urlunsplit((p.scheme, p.netloc, '/robots.txt', '', ''))
        try:
            robots, _ = await _get(client, robots_url, 256_000)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise
            robots = ''
        rp = RobotFileParser()
        rp.parse(robots.splitlines())
        if not rp.can_fetch('TopicStrategyBot', url):
            raise ValueError('robots.txt 수집 제한')
        raw, final = await _get(client, url, allowed=lambda target:
            urlsplit(target).netloc == p.netloc and rp.can_fetch('TopicStrategyBot', target))
        if urlsplit(final).netloc != p.netloc:
            # Destination needs its own robots check; no silent cross-site scraping.
            raise ValueError('다른 사이트로 이동하는 주소는 최종 URL을 직접 등록해 주세요')
        return raw, final


async def fetch_evidence(url: str) -> Evidence:
    raw, final = await fetch_public(url)
    title, text = article._extract_body(raw, final)
    import trafilatura
    meta = trafilatura.extract_metadata(raw, default_url=final)
    published = str(getattr(meta, 'date', '') or '')
    title = headline(title, text)
    return Evidence(evidence_id=identifier('ev', canonical(final)), url=final, title=title, text=text,
                    published_at=timestamp(published).isoformat() if timestamp(published) else '',
                    source_kind='official' if official(final) else 'news', publisher_group=publisher(final), original_url=url)


async def search(query: str, limit: int) -> list:
    docs = []
    try:
        docs = await research.naver_news(query, limit)
    except Exception:
        pass
    if len(docs) < limit:
        docs += await asyncio.to_thread(research._ddg_sync, query, limit)
    return docs[:limit]


def parse_feed(raw: str, limit: int = 15) -> list[dict]:
    if '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():
        raise ValueError('RSS 외부 엔티티는 지원하지 않습니다')
    root = ET.fromstring(raw)
    rows = []
    for item in [*root.findall('.//item'), *root.findall('{http://www.w3.org/2005/Atom}entry')][:limit]:
        def val(key):
            return item.findtext(key) or item.findtext('{http://www.w3.org/2005/Atom}' + key) or ''
        link = val('link')
        if not link:
            node = item.find('{http://www.w3.org/2005/Atom}link')
            link = node.get('href', '') if node is not None else ''
        date = timestamp(val('pubDate') or val('published') or val('updated'))
        rows.append({'url': link, 'title': article._strip_tags(val('title')),
                     'text': article._strip_tags(val('description') or val('summary')),
                     'published_at': date.isoformat() if date else ''})
    return rows


def ingest(store: Store, rows: list[dict], category_filter='all') -> list[str]:
    ids = []
    registry = SourceRegistry(store.root)
    for raw in rows:
        title = str(raw.get('title') or raw.get('topic') or '').strip()
        if not title:
            continue
        cat = raw.get('category') or category(title)
        if cat not in CATEGORIES or category_filter not in ('all', cat):
            continue
        evidence_rows = [Evidence.model_validate(e) for e in raw.get('evidence', [])]
        evidences = list({e.evidence_id: e for e in evidence_rows}.values())
        for e in evidences:
            store.save_evidence(e)
            registry.add(kind='article', origin='url', url=e.url, title=e.title, used_for='script_research',
                         usage='research', rights_status='reference_only', rights_basis='주제 분석 근거; 이미지 사용 권리 아님')
        urls = [e.url for e in evidences]
        key = raw.get('topic_id') or identifier('topic', canonical(urls[0]) if urls else title)
        existing = store.path('topics', key)
        if existing.exists():
            t = store.get(key)
            t.evidence_ids = list(dict.fromkeys([*t.evidence_ids, *[e.evidence_id for e in evidences]]))
            t.source_urls = list(dict.fromkeys([*t.source_urls, *urls]))
            # A refresh never retains an earlier verification/approval without rechecking.
            if evidences:
                t.verification, t.status, t.approval_fingerprint = 'needs_review', 'discovered', ''
        else:
            allowed = set(Topic.model_fields) - {'topic_id', 'title', 'category', 'source_urls', 'evidence_ids',
                'verification', 'verified_at', 'valid_until', 'status', 'approved_at', 'approval_fingerprint', 'projects', 'current_projects'}
            t = Topic(topic_id=key, title=title, category=cat, source_urls=urls,
                      evidence_ids=[e.evidence_id for e in evidences], **{k: v for k, v in raw.items() if k in allowed})
            if evidences and not t.published_at:
                t.published_at = evidences[0].published_at
            if t.freshness == 'unknown':
                t.freshness = freshness(title, cat)
            if evidences and not t.event_date and evidences[0].event_date:
                t.event_date = evidences[0].event_date
            if not t.core_claim and t.summary:
                t.core_claim = re.split(r'(?<=[.!?])\s+|\n', t.summary)[0]
            if not t.keywords:
                t.keywords = re.findall(r'[가-힣A-Za-z]{2,}', title)[:10]
        store.save_topic(t, 'collect')
        ids.append(key)
    return list(dict.fromkeys(ids))


async def collect(store: Store, cfg: dict, *, category_filter='all', topics=None, urls=None, feeds=None,
                  imported=None, limit=10, log=print) -> dict:
    rows, errors = list(imported or []), []
    links = list(urls or [])
    strategy = cfg.get('topic_strategy', {})
    for title in topics or []:
        proof = []
        for query in (f'{title} site:molit.go.kr' if category(title) == 'housing' else f'{title} site:bok.or.kr', title):
            try:
                for doc in await search(query, min(limit, 4)):
                    if not doc.url or any(e.url == doc.url for e in proof):
                        continue
                    try:
                        fresh = await fetch_evidence(doc.url)
                        if reject_reason(fresh):
                            errors.append({'source': doc.url, 'error': '기사 아님: ' + reject_reason(fresh)})
                            continue
                        if not any(e.evidence_id == fresh.evidence_id for e in proof):
                            proof.append(fresh)
                    except Exception as exc:
                        errors.append({'source': doc.url, 'error': safe_error(exc)})
            except Exception as exc:
                errors.append({'source': query, 'error': safe_error(exc)})
        rows.append({'title': title, 'summary': proof[0].text[:300] if proof else '',
                     'evidence': [e.model_dump() for e in proof]})
    for feed in [*(strategy.get('rss_sources') or []), *(feeds or [])]:
        try:
            raw, _ = await fetch_public(feed)
            for row in parse_feed(raw, limit):
                # RSS is discovery metadata, never proof by itself.
                links.append(row['url'])
        except Exception as e:
            errors.append({'source': feed, 'error': safe_error(e)})
    if not topics and not urls and not imported:
        cats = CATEGORIES if category_filter == 'all' else (category_filter,)
        # Configured institution RSS replaces search where available. No invented feed endpoints.
        news = {**QUERIES, **(strategy.get('queries') or {})}
        # 뉴스 검색어를 먼저 둔다. 기관 사이트 검색은 포털·목록 페이지가 많아 링크 한도를 먼저 차지하지 않게.
        queries = [q for c in cats for q in news[c]]
        queries += ([] if strategy.get('rss_sources') else
                    [f'site:{d} {news[c][0]}' for c in cats for d in strategy.get('official_domains', OFFICIAL)])
        for q in queries:
            try:
                for doc in await search(q, min(limit, 5)):
                    if doc.url:
                        links.append(doc.url)
            except Exception as e:
                errors.append({'source': q, 'error': safe_error(e)})
    # Limit per run; configured public feeds and news failures do not wipe saved candidates.
    for url in list(dict.fromkeys(links))[:max(limit * 3, len(urls or []))]:
        try:
            e = await fetch_evidence(url)
            reason = reject_reason(e)
            if reason:
                errors.append({'source': url, 'error': '기사 아님: ' + reason})
                log(f'후보 제외: {url} ({reason})')
                continue
            rows.append({'title': e.title, 'summary': e.text[:300], 'evidence': [e.model_dump()]})
        except Exception as exc:
            errors.append({'source': url, 'error': safe_error(exc)})
            log(f'자료 수집 보류: {url}')
    ids = ingest(store, rows, category_filter)
    for key in ids:
        topic = store.get(key)
        topic.target_audience = strategy.get('audience', topic.target_audience)
        topic.character_id = strategy.get('character', topic.character_id)
        topic.character_rights = strategy.get('character_rights', topic.character_rights)
        store.save_topic(topic, 'channel_strategy')
    return {'status': 'ok', 'topic_ids': ids, 'count': len(ids), 'errors': errors,
            'provenance': {'model': 'none', 'created_at': now(), 'config_version': 'topic-strategy-v1'}}
