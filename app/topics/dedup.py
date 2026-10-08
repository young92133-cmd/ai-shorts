"""Merge same events/claims; flag publication overlap without discarding new angles or updates."""
from __future__ import annotations

import datetime as dt
import re
from difflib import SequenceMatcher

from .schema import Topic, timestamp, now
from .store import Store, write


def tokens(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r'[가-힣A-Za-z0-9]{2,}', text)}


def similarity(a: str, b: str) -> float:
    aa, bb = tokens(a), tokens(b)
    jaccard = len(aa & bb) / max(1, len(aa | bb))
    return max(jaccard, SequenceMatcher(None, a.lower(), b.lower()).ratio())


def same_claim(a, b) -> bool:
    x, y = a.core_claim or a.summary, b.core_claim or b.summary
    return bool(x and y and similarity(x, y) >= .93)


TITLE_STOP = {'속보', '종합', '단독', '그래픽', '기자', '뉴스', '오늘', '이번', '전망', '한국'}
NUMBER_TOKEN = re.compile(r'\d+(?:\.\d+)?\s*(?:%p|%|월|년|만명|명|조원|억원|만원|개월)')


def bare_title(title: str) -> str:
    """제목 끝의 매체 이름(' - 투데이즈.kr', ' | 연합뉴스')과 머리표([속보] 등)를 뗀다."""
    title = re.sub(r'\s+[-|]\s+[^-|]{1,24}$', '', title or '')
    return re.sub(r'^\s*\[[^\]]{1,8}\]\s*', '', title)


def same_event_reports(a: Topic, b: Topic) -> bool:
    """같은 사건을 여러 언론이 보도한 경우 (2026-10-08 실수집: '9월 소비자물가 2.9%' 4개 매체, 기준금리 인상 3개 매체).

    첫 문장은 매체마다 달라 핵심 주장 유사도로는 묶이지 않는다. 발행일이 하루 이내이고, 제목이 어느 정도 비슷하며,
    제목 핵심어(3자 이상) 또는 같은 수치를 공유하면 같은 보도로 본다. 날짜가 다르면 후속 보도로 남긴다.
    """
    da, db = timestamp(a.published_at), timestamp(b.published_at)
    if not da or not db or abs((da - db).total_seconds()) > 86400 * 1.5:
        return False
    ta, tb = bare_title(a.title), bare_title(b.title)
    if similarity(ta, tb) < .25:
        return False
    shared = {w for w in tokens(ta) & tokens(tb) if len(w) >= 3 and w not in TITLE_STOP}
    numbers = {n.replace(' ', '') for n in NUMBER_TOKEN.findall(ta)} & {n.replace(' ', '') for n in NUMBER_TOKEN.findall(tb)}
    return bool(shared or numbers)


def duplicate_reason(a: Topic, b: Topic) -> str:
    if a.followup_requested or a.update_of or a.series_parent_id:
        return ''
    if a.angle and b.angle and a.angle != b.angle:
        return ''
    if a.event_date and b.event_date and a.event_date != b.event_date:
        return ''
    if a.category != b.category:
        return ''
    if a.event_key and a.event_key == b.event_key and same_claim(a, b):
        return '동일 사건·동일 핵심 주장'
    if same_claim(a, b) and similarity(a.title, b.title) >= .55 and (a.event_date == b.event_date) and (
            a.published_at[:10] and a.published_at[:10] == b.published_at[:10]):
        return '같은 날짜 보도·핵심 주장·제목 의미 중복'
    if similarity(a.title, b.title) >= .93 and (same_claim(a, b) or a.title == b.title):
        return '제목·핵심 주장 중복'
    if same_event_reports(a, b):
        return '같은 사건 여러 언론 보도(발행일·제목 핵심어 일치)'
    return ''


def deduplicate(store: Store, at=None) -> list[dict]:
    current = timestamp(at or now())
    clusters = []
    topics = sorted(store.topics(), key=lambda t: (t.created_at, t.topic_id))
    for i, topic in enumerate(topics):
        if topic.status in ('excluded', 'published') or topic.duplicate_of:
            continue
        for earlier in topics[:i]:
            if earlier.duplicate_of or earlier.status == 'excluded':
                continue
            reason = duplicate_reason(topic, earlier)
            if not reason:
                continue
            earlier.source_urls = list(dict.fromkeys([*earlier.source_urls, *topic.source_urls]))
            earlier.evidence_ids = list(dict.fromkeys([*earlier.evidence_ids, *topic.evidence_ids]))
            # A new conflicting source cannot inherit the earlier approval.
            for fact in topic.facts:
                existing = next((f for f in earlier.facts if f.claim == fact.claim), None)
                if existing:
                    existing.citations += [c for c in fact.citations if c not in existing.citations]
                else:
                    fact = fact.model_copy(update={'fact_id': f'f{len(earlier.facts)+1}'})
                    earlier.facts.append(fact)
            earlier.verification, earlier.approval_fingerprint = 'needs_review', ''
            if earlier.status in ('approved', 'planned', 'reviewed'):
                earlier.status = 'held'
            topic.duplicate_of = earlier.topic_id
            topic.duplicate_reasons.append(reason)
            store.save_topic(earlier, 'merge_sources')
            store.save_topic(topic, 'duplicate')
            clusters.append({'canonical': earlier.topic_id, 'members': [earlier.topic_id, topic.topic_id], 'reason': reason})
            break
        if topic.duplicate_of or topic.followup_requested or topic.update_of or topic.series_parent_id:
            continue
        for history in store.history():
            date = timestamp(history.get('published_at', ''))
            if not date or not 0 <= (current - date).total_seconds() <= 90 * 86400:
                continue
            older = Topic(topic_id=history['topic_id'], title=history['title'], category=history['category'],
                          core_claim=history.get('core_claim', ''), event_key=history.get('event_key', ''),
                          target_audience=history.get('target_audience', []), keywords=history.get('keywords', []))
            reason = duplicate_reason(topic, older)
            # semantic overlap using both claim and keywords, not just a shared '전세'.
            overlap = similarity(topic.core_claim, older.core_claim) if topic.core_claim and older.core_claim else 0
            key_overlap = bool(set(topic.keywords) & set(older.keywords))
            audience_overlap = bool(set(topic.target_audience) & set(older.target_audience))
            if reason or (overlap >= .93 and key_overlap and audience_overlap):
                window = 30 if (current - date).days <= 30 else 90
                topic.duplicate_of = older.topic_id
                topic.duplicate_reasons.append(f'최근 {window}일 발행 이력: {reason or "주장·키워드·독자 의미 중복"}')
                store.save_topic(topic, 'history_duplicate')
                break
    write(store.root / 'duplicate_clusters.json', {'created_at': current.isoformat(), 'clusters': clusters})
    return clusters
