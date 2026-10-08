from __future__ import annotations

import datetime as dt
import uuid
from collections import Counter

from .schema import CalendarEntry, timestamp, now, CATEGORIES
from .store import Store, write
from .verification import eligible

QUOTA = {'housing': 9, 'finance': 7, 'economy': 4}


def quota_state(history: list[dict], quota=None) -> dict:
    target = quota or QUOTA
    if set(target) != set(CATEGORIES) or sum(target.values()) != 20 or any(not isinstance(v, int) or v < 0 for v in target.values()):
        raise ValueError('최근 20슬롯 목표는 housing/finance/economy 합계 20이어야 합니다')
    recent = sorted(history, key=lambda h: h.get('published_at', h.get('scheduled_date', '')))[-20:]
    counts = Counter(h['category'] for h in recent)
    return {'window': 20, 'count': len(recent), 'counts': {k: counts[k] for k in CATEGORIES},
            'target': target, 'deficits': {k: max(0, v-counts[k]) for k,v in target.items()}}


def fresh_on(topic, day: dt.date, max_age_days: int) -> bool:
    """뉴스 주제는 게시일에도 뉴스 유효기간(기본 7일) 안이어야 한다. 상시 주제(evergreen)는 날짜 제한 없음.

    2026-10-08 실운영 검증: 10/02 발표 뉴스가 다음 주 월요일(10/12)에 배치됐지만 10/09 이후 '오래된 정보'로 막힌다.
    """
    if topic.freshness == 'evergreen':
        return True
    dates = [d for d in (timestamp(topic.event_date), timestamp(topic.published_at)) if d]
    return bool(dates) and day <= (max(dates) + dt.timedelta(days=max_age_days)).date()


def make_calendar(store: Store, cfg: dict, *, weeks=1, count=None, start=None, at=None) -> dict:
    options = cfg.get('topic_strategy', {})
    count = count if count is not None else options.get('weekly_count', 3)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 7 or weeks not in (1, 2, 3, 4):
        raise ValueError('기간은 1~4주, 주당 편수는 1~7편입니다')
    today = timestamp(at or now()).date()
    first = dt.date.fromisoformat(start) if start else today + dt.timedelta(days=(-today.weekday()) % 7)
    if first < today:
        raise ValueError('과거 날짜로 새 캘린더를 만들 수 없습니다')
    target = options.get('quota', QUOTA)
    quota_state([], target)
    history = store.history()
    existing = []
    for path in (store.root / 'calendars').glob('*.json'):
        for entry in store.read(path)['entries']:
            t = store.get(entry['topic_id'])
            if t.status not in ('published', 'excluded', 'held'):
                existing.append(entry)
    used = {h['topic_id'] for h in history} | {e['topic_id'] for e in existing}
    pool = [t for t in store.topics() if t.topic_id not in used and eligible(t, at) and t.score
            and t.score.total_score >= options.get('review_threshold', 65)]
    simulated = [*sorted(history, key=lambda h: h['published_at']),
                 *[{'category': e['category'], 'published_at': e['scheduled_date']} for e in sorted(existing, key=lambda e:e['scheduled_date'])]]
    entries, shortages = [], []
    offsets = [0] if count == 1 else [round(i * (4 if count <= 3 else 6) / (count-1)) for i in range(count)]
    for week in range(weeks):
        for offset in offsets:
            day = first + dt.timedelta(days=7 * week + offset)
            candidates = [t for t in pool if fresh_on(t, day, int(options.get('news_max_age_days', 7)))]
            if not candidates:
                shortages.append(day.isoformat())
                continue
            prior = sorted([h for h in simulated if h['published_at'][:10] <= day.isoformat()], key=lambda h:h['published_at'])[-19:]
            counts = Counter(h['category'] for h in prior)
            projected = min(20, len(prior)+1)
            def order(t):
                pressure = target[t.category] / 20 * projected - counts[t.category]
                return (pressure, t.score.total_score, t.topic_id)
            selected = max(candidates, key=order)
            pool.remove(selected)
            needs_recheck = selected.freshness != 'evergreen' or day >= timestamp(selected.valid_until).date()
            entry = CalendarEntry(entry_id='slot_' + uuid.uuid4().hex[:12], topic_id=selected.topic_id,
                scheduled_date=day.isoformat(), category=selected.category, topic=selected.title,
                recommended_title=selected.title, audience=selected.target_audience, topic_score=selected.score.total_score,
                format=selected.score.recommended_format, purpose={'housing':'공감·저장', 'finance':'학습·공유', 'economy':'화제성·유입'}[selected.category],
                character=selected.character_id, verification=selected.verification,
                b2b=selected.opportunity.target_industries if selected.opportunity else [], production_status=selected.status,
                publication_gate='reverify_on_publication_date' if needs_recheck else 'human_approval_required')
            entries.append(entry.model_dump())
            simulated.append({'category': selected.category, 'published_at': day.isoformat()})
            selected.scheduled_date = day.isoformat()
            store.save_topic(selected, 'schedule')
    sample = max((t for t in store.topics() if eligible(t, at) and t.score and t.score.total_score >= options.get('review_threshold', 65)
                  and t.opportunity and t.opportunity.b2b_fit_score >= 65), key=lambda t:t.opportunity.b2b_fit_score, default=None)
    data = {'calendar_id': 'calendar_' + uuid.uuid4().hex[:12], 'created_at': at or now(), 'config_version': 'topic-strategy-v1',
            'model': 'none', 'weeks': weeks, 'weekly_count': count, 'entries': entries, 'unfilled_dates': shortages,
            'quota_before': quota_state(history, target), 'quota_after': quota_state(simulated, target),
            'b2b_sample_topic_id': sample.topic_id if sample else None,
            'note': '미검증·낮은 점수로 비중을 억지로 채우지 않음. 뉴스는 발행일 재검증 필수.'}
    data['weekly_b2b_samples'] = []
    for week in range(weeks):
        first_day, last_day = first + dt.timedelta(days=7*week), first + dt.timedelta(days=7*week+6)
        selected = [store.get(e['topic_id']) for e in entries if first_day.isoformat() <= e['scheduled_date'] <= last_day.isoformat()]
        weekly_sample = max((t for t in selected if t.opportunity and t.opportunity.b2b_fit_score >= 65),
                            key=lambda t:t.opportunity.b2b_fit_score, default=None)
        data['weekly_b2b_samples'].append({'week':week+1, 'topic_id':weekly_sample.topic_id if weekly_sample else None})
    write(store.path('calendars', data['calendar_id']), data)
    return data


def reschedule(store: Store, topic_id: str, date: str, at=None):
    if dt.date.fromisoformat(date) < timestamp(at or now()).date():
        raise ValueError('과거 날짜로 예약할 수 없습니다')
    t = store.get(topic_id)
    t.scheduled_date = date
    store.save_topic(t, 'reschedule')
    for path in (store.root / 'calendars').glob('*.json'):
        data = store.read(path)
        for entry in data['entries']:
            if entry['topic_id'] == topic_id:
                entry['scheduled_date'], entry['publication_gate'] = date, 'reverify_on_publication_date'
        write(path, data)
    return t
