"""Conservative evidence gate. A URL/domain or LLM's 'verified' label alone never verifies a claim."""
from __future__ import annotations

import datetime as dt
import re

from .discovery import official, publisher, canonical
from .schema import Topic, Fact, Citation, Evidence, timestamp, now
from .store import Store

NUMBERS = re.compile(r'\d[\d,.]*\s*(?:%p|%|bp|퍼센트|조원|억원|만원|원|명|가구|건|배|개월|년|세|점)?')
UNITS = re.compile(r'(?:%p|%|bp|퍼센트|조원|억원|만원|원|명|가구|건|배|개월|년|세|점)')
SENSITIVE = re.compile(r'대출|세금|세율|공제|자격|제도|지원금|보험|전환율|가입|투자|수익')
FORECAST = re.compile(r'전망|예상|추정|가능성|할 것으로')
OPINION = re.compile(r'의견|생각|바람직|추천한다')
STATISTICS = re.compile(r'통계|지수|증가율|상승률|평균|중위|설문|조사 결과')
DEFAULT_TRUSTED = ('yna.co.kr', 'hani.co.kr', 'khan.co.kr', 'kbs.co.kr', 'mbc.co.kr', 'sbs.co.kr')


def normalized(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def extract_facts(topic: Topic, evidence: list[Evidence]) -> list[Fact]:
    """Extract verbatim sentences; missing scope/date is left blank and goes to review.

    This is intentionally conservative. Human-edited facts can link original statistics and scopes.
    It is not a general factual entailment model.
    """
    rows = []
    for e in evidence:
        sentences = re.split(r'(?<=[.!?。])\s+|\n+', e.text)
        for sentence in sentences:
            text = normalized(sentence)
            if len(text) < 12 or len(text) > 350:
                continue
            kind = 'forecast' if FORECAST.search(text) else 'opinion' if OPINION.search(text) else 'fact'
            if any(f.claim == text for f in rows):
                old = next(f for f in rows if f.claim == text)
                old.citations.append(Citation(evidence_id=e.evidence_id, excerpt=text))
                continue
            unit = UNITS.search(text)
            # Date must appear in the evidence, not be invented from retrieval time.
            dates = re.findall(r'(20\d{2})[년./-]\s*(\d{1,2})[월./-]\s*(\d{1,2})(?:일)?', text)
            as_of = '-'.join([dates[0][0], dates[0][1].zfill(2), dates[0][2].zfill(2)]) if dates else ''
            rows.append(Fact(fact_id=f'f{len(rows)+1}', claim=text, kind=kind,
                             citations=[Citation(evidence_id=e.evidence_id, excerpt=text)], as_of=as_of,
                             unit=unit.group() if unit else ''))
            if len(rows) >= 8:
                return rows
    return rows


def compliance(topic: Topic) -> list[str]:
    text = ' '.join([topic.title, topic.summary, topic.core_claim, *[f.claim for f in topic.facts]])
    derived = {'금융 보장·단정 표현 검토 필요', '광고: 사업자 서비스·자격·표시·주장 검증 필요',
               '캐릭터 사용 권한 미확인', '제목이 확인된 핵심 주장보다 과장됨: 제목 수정 필요',
               '제목의 주요 수치에 검증된 근거 없음'}
    flags = [f for f in topic.compliance_flags if f not in derived]
    if re.search(r'수익\s*보장|원금\s*보장.*투자|무조건\s*(?:오른|상승|수익)|확정\s*수익', text):
        flags.append('금융 보장·단정 표현 검토 필요')
    if re.search(r'광고|협찬|홍보|제휴', text):
        flags.append('광고: 사업자 서비스·자격·표시·주장 검증 필요')
    if topic.character_rights not in ('owned', 'licensed'):
        flags.append('캐릭터 사용 권한 미확인')
    return list(dict.fromkeys(flags))


def verify(store: Store, topic: Topic, cfg: dict | None = None, at: str | None = None) -> Topic:
    options = (cfg or {}).get('topic_strategy', {})
    current = timestamp(at or now())
    docs = store.evidence(topic)
    lookup = {e.evidence_id: e for e in docs}
    if not topic.facts:
        topic.facts = extract_facts(topic, docs)
    official_domains = options.get('official_domains') or None
    trusted = options.get('trusted_news_domains', DEFAULT_TRUSTED)
    max_age = int(options.get('news_max_age_days', 7))
    topic.verification_reasons = []
    groups = {}
    for f in topic.facts:
        f.checks = []
        # Detect differing numbers even without a human-supplied metric key.
        numeric_text = re.sub(r'20\d{2}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2}(?:일)?', '', f.claim)
        values = [m.group().strip() for m in NUMBERS.finditer(numeric_text)]
        metric = f.conflict_key or (NUMBERS.sub('#', numeric_text).strip() if values else '')
        if metric and f.kind == 'fact':
            key = (metric, f.as_of, f.applies_to, f.unit)
            groups.setdefault(key, []).append(f)
    def numeric_value(f):
        text = re.sub(r'20\d{2}[-./년]\s*\d{1,2}[-./월]\s*\d{1,2}(?:일)?', '', f.claim)
        return f.value or '|'.join(m.group().strip() for m in NUMBERS.finditer(text))
    conflicts = {f.fact_id for vals in groups.values() if len({numeric_value(f) for f in vals if numeric_value(f)}) > 1 for f in vals}
    for f in topic.facts:
        sources, exact = [], []
        for cite in f.citations:
            e = lookup.get(cite.evidence_id)
            if not e or not e.url or e.access != 'public':
                f.checks.append('출처 접근 실패 또는 미등록')
                continue
            excerpt = normalized(cite.excerpt)
            if not excerpt or excerpt not in normalized(e.text):
                f.checks.append('근거 문장과 주장 일치 확인 실패')
                continue
            if cite.result == 'contradicts':
                f.checks.append('출처가 주장과 충돌')
                continue
            if cite.result != 'supports' or normalized(f.claim) not in excerpt:
                f.checks.append('근거 문장과 주장 일치 확인 실패')
                continue
            exact.append(e)
            sources.append(e.url)
        primary = [e for e in exact if official(e.url, official_domains)] if official_domains else [e for e in exact if official(e.url)]
        credible = [e for e in exact if official(e.url, trusted)]
        independent = {publisher(e.url) for e in credible}
        independent_text = {normalized(e.text) for e in credible}
        # Republished/syndicated originals count once, even on multiple domains.
        origins = {canonical(e.original_url or e.url) for e in credible}
        sufficient = bool(primary) or (len(independent) >= 2 and len(independent_text) >= 2 and len(origins) >= 2)
        checks = []
        numerical = bool(NUMBERS.search(f.claim))
        if numerical and (not timestamp(f.as_of) or not f.unit or f.unit not in f.claim):
            checks.append('수치의 기준일·단위 미확인')
        if numerical and (f.as_of and not any(f.as_of in e.text or
                f.as_of.replace('-', '.') in e.text or _korean_date(f.as_of) in e.text for e in exact)):
            checks.append('기준일이 원문에 없음')
        if SENSITIVE.search(f.claim) and (not f.applies_to or not any(f.applies_to in e.text for e in exact)):
            checks.append('적용 대상 미확인')
        if STATISTICS.search(f.claim) and not any(canonical(e.url) == canonical(f.statistic_original_url) for e in primary):
            checks.append('통계 원자료 미확인')
        # A recent republished article does not renew the date of the underlying fact/event.
        dates = [timestamp(f.as_of), timestamp(topic.event_date), *[timestamp(e.event_date) for e in exact],
                 *[timestamp(e.published_at) for e in exact]]
        dates = [d for d in dates if d]
        stale = topic.freshness != 'evergreen' and dates and any((current - d).total_seconds() > max_age * 86400 for d in dates)
        future = any(d > current for d in dates)
        if f.fact_id in conflicts or '출처가 주장과 충돌' in f.checks:
            f.verification = 'conflicting'
        elif stale:
            f.verification = 'outdated'
        elif future or checks or (topic.freshness != 'evergreen' and not dates):
            f.verification = 'needs_review'
        elif sufficient and not f.checks:
            f.verification = 'verified'
        elif exact:
            f.verification = 'needs_review'
        else:
            f.verification = 'unverified'
        f.checks += checks
        if not sufficient:
            f.checks.append('공식 1차 자료 또는 독립 출처 교차 확인 필요')
        if f.kind != 'fact':
            f.checks.append(f'{f.kind}: 확정 사실과 분리하여 표시')
    important = [f.verification for f in topic.facts if f.important]
    topic.compliance_flags = compliance(topic)
    if re.search(r'충격|경악|무조건|반드시|역대\s*(?:최고|최저)|폭등|폭락', topic.title) and not any(topic.title in f.claim for f in topic.facts):
        topic.compliance_flags.append('제목이 확인된 핵심 주장보다 과장됨: 제목 수정 필요')
    title_text = re.sub(r'\d+\s*(?:가지|장|단계|편|개|분|초)', '', topic.title)
    title_numbers = {m.group().replace(' ', '') for m in NUMBERS.finditer(title_text)}
    factual_numbers = {m.group().replace(' ', '') for f in topic.facts if f.verification == 'verified'
                       for m in NUMBERS.finditer(f.claim)}
    if title_numbers - factual_numbers:
        topic.compliance_flags.append('제목의 주요 수치에 검증된 근거 없음')
    topic.verification = next((s for s in ('conflicting', 'outdated', 'unverified', 'needs_review') if s in important), 'verified') if important else 'unverified'
    topic.verification_reasons = list(dict.fromkeys(c for f in topic.facts if f.important and f.verification != 'verified' for c in f.checks))
    if not important:
        topic.verification_reasons.append('검증할 핵심 주장 없음')
    if topic.compliance_flags and topic.verification == 'verified':
        topic.verification = 'needs_review'
        topic.verification_reasons += topic.compliance_flags
    topic.source_confidence = sum(f.verification == 'verified' for f in topic.facts) / max(1, len(topic.facts))
    topic.verified_at = current.isoformat()
    ttl = int(options.get('evergreen_recheck_days', 30) if topic.freshness == 'evergreen' else options.get('news_recheck_hours', 24) / 24)
    valid_for = dt.timedelta(days=ttl) if topic.freshness == 'evergreen' else dt.timedelta(hours=options.get('news_recheck_hours', 24))
    retrieval_dates = [timestamp(e.retrieved_at) for e in docs if timestamp(e.retrieved_at)]
    deadline = min([current + valid_for, *[d + valid_for for d in retrieval_dates]])
    topic.valid_until = deadline.isoformat() if topic.verification == 'verified' else ''
    if topic.verification == 'outdated':
        topic.freshness = 'expired'
    if topic.verification != 'verified':
        topic.approval_fingerprint = ''
        if topic.status in ('approved', 'planned', 'reviewed'):
            topic.status = 'held'
    elif topic.status == 'discovered':
        topic.status = 'verified'
    store.save_topic(topic, 'verify')
    return topic


def _korean_date(value: str) -> str:
    d = timestamp(value)
    return f'{d.year}년 {d.month}월 {d.day}일' if d else ''


def eligible(topic: Topic, at: str | None = None) -> bool:
    deadline = timestamp(topic.valid_until)
    return (topic.verification == 'verified' and bool(deadline) and deadline >= timestamp(at or now())
            and not topic.compliance_flags and not topic.duplicate_of and topic.status not in ('excluded', 'held', 'published'))
