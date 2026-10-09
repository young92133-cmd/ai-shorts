"""Offline, synthetic end-to-end demo. No public sources, LLM, media APIs or PNG rendering."""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import uuid
from pathlib import Path

from app.topics.schema import Evidence, Fact, Citation, now, timestamp
from app.topics.store import Store, identifier, write
from app.topics.discovery import ingest
from app.topics.engine import Engine
from app.topics.calendar import make_calendar

NOTICE = '테스트용 가상 근거를 사용한 오프라인 예시입니다. 실제 수집·검증한 뉴스나 투자 조언이 아닙니다.'
IDEAS = [
    ('housing', '전세와 월세 중 어떤 선택이 더 유리할까?', '주거 계약을 비교할 때 비용 항목을 구분해 확인합니다.'),
    ('housing', '전세계약 전 확인할 체크리스트', '계약을 검토할 때 관련 원자료의 기준 시점을 확인합니다.'),
    ('finance', '직장인 월급 관리, 저축부터 어떻게 나눌까?', '월급 관리 계획은 지출 항목을 구분하는 과정입니다.'),
    ('finance', 'ETF 기초, 가입 전 비교해야 할 조건', '금융 교육 자료에는 상품의 구조와 비용 항목을 구분합니다.'),
    ('housing', '신혼부부 주거비 비교, 보증금만 보면 될까?', '주거 예산의 여러 비용을 함께 살펴보는 관점입니다.'),
    ('finance', '사회초년생 비상금, 어떤 기준으로 관리할까?', '비상자금 교육은 목적과 사용 계획을 먼저 구분합니다.'),
    ('housing', '월세 관리비, 계약서에서 무엇을 확인할까?', '관리비를 검토할 때 계약 문서의 항목을 확인합니다.'),
    ('finance', '연금 기초, 상품 조건을 비교하는 방법', '연금 교육 자료는 여러 상품의 조건을 구분합니다.'),
    ('economy', '물가 뉴스, 직장인의 생활비와 어떻게 연결될까?', '경제 뉴스의 수집 시점과 사건 발생 시점은 다릅니다.'),
    ('economy', '금리 발표, 대출 뉴스에서 무엇을 확인할까?', '발표 자료를 읽을 때 원자료와 기사 설명을 구분합니다.'),
    ('housing', '주거 선택, 이사 비용까지 비교했나요?', '주거 선택을 설명할 때 의사결정 항목을 구분합니다.'),
    ('finance', '예금 기초, 조건 비교에서 놓치기 쉬운 것', '예금 교육은 상품 설명서의 여러 항목을 구분합니다.'),
    ('economy', '고용 뉴스, 사회초년생이 확인할 질문', '고용 관련 뉴스는 확정된 사실과 전망을 구분해 읽습니다.'),
    ('housing', '청약 기초, 나에게 적용되는 조건 확인하기', '주택 관련 정보를 볼 때 적용 대상과 기준 시점을 구분합니다.'),
    ('finance', '가계부 관리, 소비 항목을 비교하는 방법', '가계부를 살펴볼 때 지출의 목적별 항목을 구분합니다.'),
]


def fixture_rows(at):
    rows = []
    for i,(category,title,text) in enumerate(IDEAS,1):
        claims = [text] if i != 1 else [text, '보증금과 매달 지출은 서로 다른 현금 흐름 항목입니다.',
                                         '같은 기간과 같은 범위의 비용을 함께 비교하는 관점입니다.']
        url = f'https://official.example/fixture/{i}'
        e = Evidence(evidence_id=identifier('ev',url), url=url, title='가상 교육 근거', text=' '.join(claims),
                     published_at=at, retrieved_at=at, source_kind='fixture')
        facts = [Fact(fact_id=f'f{n}', claim=claim, applies_to='여러 상품' if '상품' in claim else '적용 대상' if '적용 대상' in claim else '',
                      citations=[Citation(evidence_id=e.evidence_id,excerpt=claim)]) for n,claim in enumerate(claims,1)]
        rows.append({'title':title, 'category':category, 'summary':text, 'freshness':'evergreen',
                     'facts':[f.model_dump() for f in facts], 'evidence':[e.model_dump()], 'keywords':[title]})
    return rows


async def run(out: Path) -> dict:
    at = now()
    if (out / 'demo_store').exists():
        # A rerun preserves the earlier reviewable demo instead of reusing its reserved slots.
        out = out / ('run_' + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=True)
    cfg = {'topic_strategy': {'official_domains':['official.example']}}
    store = Store(out / 'demo_store')
    ingest(store, fixture_rows(at))
    engine = Engine(store, cfg)
    result = await engine.rank(limit=10, at=at)
    write(out / 'recommendations.json', {**result, 'notice':NOTICE})
    weekly = make_calendar(store, cfg, weeks=1, at=at)
    write(out / 'calendar_1week.json', {**weekly, 'notice':NOTICE})
    # Continue the same calendar rather than reusing reserved topics.
    start = (dt.date.fromisoformat(weekly['entries'][0]['scheduled_date']) + dt.timedelta(days=7)).isoformat()
    monthly = make_calendar(store, cfg, weeks=4, start=start, at=at)
    write(out / 'calendar_4weeks.json', {**monthly, 'notice':NOTICE})
    selected = next(t for t in store.topics() if t.title == IDEAS[0][1])
    # Simulated user approval only in the isolated fixture store, never production.
    await engine.approve(selected.topic_id, at=at)
    packet = await engine.create(selected.topic_id, fmt='hybrid', dry_run=True, at=at)
    write(out / 'engine_delivery.json', {**packet, 'notice':NOTICE})
    plan = packet['delivery'][0]['story_plan']
    write(out / 'story_plan.json', {**plan, 'notice':NOTICE})
    lines = ['# Topic Strategy V1 오프라인 검증 예시', '', NOTICE, '', '모델 호출 0회 · 유료 API 0원 · PNG 렌더링 없음.', '',
             '## 추천 후보 10개', '', '|번호|카테고리|주제|점수|검증|', '|---|---|---|---:|---|']
    labels = {'housing':'부동산·주거','finance':'재테크·투자 기초','economy':'경제 뉴스 해설'}
    for r in result['topics']:
        lines.append(f"|{r['number']}|{labels[r['category']]}|{r['title']}|{r['score']['total_score']}|가상 근거 {r['verification']}|")
    lines += ['', '## 상위 추천 3개', '', *[f"- {r['title']} — {r['score']['total_score']}점" for r in result['top3']]]
    for title, cal in (('1주 캘린더',weekly),('4주 캘린더',monthly)):
        lines += ['', '## '+title, '', '|발행 예정일|분야|주제|포맷|', '|---|---|---|---|']
        for r in cal['entries']:
            lines.append(f"|{r['scheduled_date']}|{labels[r['category']]}|{r['topic']}|{r['format']}|")
        lines += ['', f"채울 수 없는 슬롯 {len(cal['unfilled_dates'])}개; 강제 선정하지 않음."]
    lines += ['', '## 전세·월세 8장 스토리', '', '|장|역할|타입|문구|', '|---|---|---|---|']
    for i,r in enumerate(plan['pages'],1):
        lines.append(f"|{i}|{r['role']}|{r['page_type']}|{(r['dialogue'] or r['body'] or r['headline']).replace(chr(10),' / ')}|")
    opp = store.get(selected.topic_id).opportunity
    lines += ['', '캐릭터: tory_01 토리. 상황과 대사는 이해를 위한 창작 예시.', '', '## B2B 활용', '',
              ', '.join(opp.target_industries), '', ', '.join(opp.client_use_cases), '', opp.recommended_package,
              '', '실제 광고 전환 시 사업자·서비스·자격·광고 표시·주장 검증 필요.', '',
              '실제 수집은 `topics collect`, 실제 승인·제작은 별도 운영 저장소의 `topics approve/create`로 실행한다.']
    (out / 'REPORT.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return {'status':'ok', 'dir':str(out.resolve()), 'candidates':len(result['topics']), 'top3':len(result['top3']),
            'week_slots':len(weekly['entries']), 'four_week_slots':len(monthly['entries']), 'story_pages':len(plan['pages']),
            'cost':0, 'notice':NOTICE}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=Path('output') / ('topic_strategy_demo_' + uuid.uuid4().hex[:8]))
    print(json.dumps(asyncio.run(run(ap.parse_args().out)), ensure_ascii=False, indent=2))
