"""자연어 요청에서 출력 형식을 알아낸다 ("이 주제로 인스타툰 만들어줘" → insta_toon).

Claude Code 가 CLAUDE.md 표로 명령을 고르지만, `make --request "…"` 로 문장을 그대로 넘겨도 같은 결과가 나오게 한다.
"""
from __future__ import annotations

import re

CARD = ("카드뉴스", "카드 뉴스", "카드형", "card news", "cardnews", "card_news", "캐러셀")
TOON = ("인스타툰", "인스타 툰", "만화", "웹툰", "툰", "insta_toon", "instatoon", "코믹", "comic")
MIX = ("섞어", "섞은", "섞인", "하이브리드", "hybrid", "혼합", "합쳐", "믹스")
SHORTS = ("쇼츠", "숏츠", "shorts", "릴스", "숏폼")
ALL = ("전부", "모두", "다 만들", "둘 다", "셋 다", "세 가지", "all", "모든 형식", "다같이", "다 같이")


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def detect_output_format(text: str) -> str:
    """shorts | card_news | insta_toon | hybrid | all. 형식 단서가 없으면 기존 기본값 shorts."""
    t = re.sub(r"\s+", " ", (text or "").lower())
    card, toon, shorts = _has(t, CARD), _has(t, TOON), _has(t, SHORTS)
    if _has(t, ALL) and not (card and toon and not shorts):
        return "all"
    if shorts and (card or toon):
        return "all"                  # 쇼츠와 카드뉴스/인스타툰을 같이 → 쇼츠 + 하이브리드
    if (card and toon) or (_has(t, MIX) and (card or toon)) or _has(t, ("하이브리드", "hybrid")):
        return "hybrid"
    if toon:
        return "insta_toon"
    if card:
        return "card_news"
    return "shorts"


def detect_topic_request(text: str) -> dict:
    """Strategy intents use the same format detector. Selection numbers need a saved list ID."""
    t = re.sub(r'\s+', ' ', text.lower()).strip()
    match = re.search(r'(\d+)\s*개', t)
    weeks = re.search(r'(\d+)\s*주', t)
    select = re.search(r'(\d+)\s*번', t)
    pages = re.search(r'(\d+)\s*장', t)
    category = 'housing' if any(w in t for w in ('부동산', '주거', '전세', '월세')) else 'finance' if '재테크' in t else 'economy' if '경제 뉴스' in t else 'all'
    action = ('calendar' if any(w in t for w in ('캘린더', '일정')) else 'create' if select and any(w in t for w in ('만들', '제작')) else
              'recommend' if any(w in t for w in ('추천', '영업')) else 'list' if any(w in t for w in ('보여', '목록')) else 'unknown')
    return {'action':action, 'category':category, 'limit':int(match[1]) if match else 3 if action=='recommend' else 10,
            'weeks':int(weeks[1]) if weeks else 1, 'select':int(select[1]) if select else None,
            'pages':int(pages[1]) if pages else 8, 'format':detect_output_format(t) if any(w in t for w in CARD+TOON+MIX+SHORTS) else 'hybrid',
            'b2b':'b2b' in t or '영업' in t}
