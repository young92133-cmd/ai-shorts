"""Chat-facing CLI for Topic Strategy; existing make/trends/batch are unchanged."""
from __future__ import annotations

import argparse
import json

from . import core, batch
from .intent import detect_topic_request
from ..topics import discovery, calendar
from ..topics.config import DEFAULTS
from ..topics.engine import Engine
from ..topics.store import Store
from ..topics.schema import CATEGORIES


def add_parser(sub):
    p = sub.add_parser('topics', help='주제 수집·검증·추천·승인·스토리·콘텐츠 캘린더')
    commands = p.add_subparsers(dest='topics_cmd', required=True)
    collect = commands.add_parser('collect', help='공개 뉴스·공식 자료·RSS·기존 discovery 수집')
    collect.add_argument('--category', choices=('all', *CATEGORIES), default='all')
    collect.add_argument('--topic', action='append', default=[])
    collect.add_argument('--url', action='append', default=[])
    collect.add_argument('--rss', action='append', default=[])
    collect.add_argument('--input', help='후보/근거 JSON 또는 기존 research/docs/trends 결과')
    collect.add_argument('--candidates', help='기존 trends 후보 ID')
    collect.add_argument('--limit', type=int, default=10)
    for name in ('rank', 'recommend', 'list'):
        command = commands.add_parser(name)
        command.add_argument('--limit', type=int, default=3 if name == 'recommend' else 10)
        command.add_argument('--category', choices=('all', *CATEGORIES), default='all')
        command.add_argument('--b2b', action='store_true')
        if name == 'rank':
            command.add_argument('--ai', action='store_true', help='명시적으로 기존 구독 LLM 평가 사용 (기본 규칙 평가)')
    cal = commands.add_parser('calendar')
    cal.add_argument('--weeks', type=int, choices=(1,2,3,4), default=1)
    cal.add_argument('--count', type=int)
    cal.add_argument('--start', help='시작 날짜 YYYY-MM-DD (기본 다음 월요일)')
    for name in ('inspect', 'verify', 'approve', 'exclude', 'hold', 'release', 'review', 'published', 'edit', 'schedule', 'plan', 'create'):
        command = commands.add_parser(name)
        group = command.add_mutually_exclusive_group(required=True)
        group.add_argument('--id', dest='topic_id')
        group.add_argument('--select', type=int, help='사용자가 확인한 목록의 번호')
        command.add_argument('--selection', help='번호가 속한 selection_id (최근 목록 자동 선택 없음)')
        if name == 'approve':
            command.add_argument('--followup', action='store_true')
        if name == 'published':
            command.add_argument('--url', default='', help='사용자가 이미 게시한 결과 URL; 이 명령은 게시하지 않음')
        if name == 'edit':
            command.add_argument('--title')
            command.add_argument('--direction')
            command.add_argument('--character')
            command.add_argument('--facts', help='근거·기준일·단위·적용대상 포함 Fact 배열 JSON')
            command.add_argument('--followup', action='store_true', default=None)
            command.add_argument('--series-parent')
            command.add_argument('--update-of')
        if name == 'schedule':
            command.add_argument('--date', required=True)
        if name in ('plan', 'create'):
            command.add_argument('--format', choices=('hybrid','insta_toon','card_news', *(['shorts','all'] if name=='create' else [])), default='hybrid')
            command.add_argument('--pages', type=int, choices=(8,), default=8)
        if name == 'plan':
            command.add_argument('--preview', action='store_true')
        if name == 'create':
            command.add_argument('--dry-run', action='store_true', help='제작 엔진 전달 JSON만 출력, 렌더/API 호출 없음')
            command.add_argument('--also', action='append', choices=('shorts','card_news','insta_toon','hybrid'), default=[])
    request = commands.add_parser('request', help='기존 intent 모듈로 자연어 전략 명령 처리')
    request.add_argument('text')
    request.add_argument('--selection')
    request.add_argument('--dry-run', action='store_true')
    return p


def engine() -> Engine:
    cfg = core._cfg()
    cfg['topic_strategy'] = {**DEFAULTS, **cfg.get('topic_strategy', {})}
    cfg['llm'] = {**cfg['llm'], 'allow_paid_openai': False, 'allow_paid_anthropic': False}
    return Engine(Store(core.output_root() / '_factory' / 'topics'), cfg)


def import_rows(path):
    with open(path, encoding='utf-8-sig') as file:
        data = json.load(file)
    if isinstance(data, list):
        rows = data
    else:
        rows = data.get('topics', data.get('candidates', data.get('docs', [])))
    out = []
    for r in rows:
        row = dict(r)
        row['title'] = row.get('title') or row.get('topic') or row.get('keyword')
        if row.get('url') and not row.get('evidence'):
            from ..topics.schema import Evidence, timestamp
            from ..topics.store import identifier
            date = timestamp(row.get('published_at') or row.get('published', ''))
            ev = Evidence(evidence_id=identifier('ev', discovery.canonical(row['url'])), url=row['url'],
                          title=row['title'] or '', text=row.get('text', ''), published_at=date.isoformat() if date else '')
            row['evidence'] = [ev.model_dump()]
        out.append(row)
    return out


async def dispatch(a, log=print):
    e = engine()
    cmd = a.topics_cmd
    try:
        if cmd == 'collect':
            if not 1 <= a.limit <= 100:
                raise ValueError('수집 개수는 1~100입니다')
            imported = import_rows(a.input) if a.input else []
            if a.candidates:
                imported += batch.load_candidates(a.candidates)['candidates']
            return await discovery.collect(e.store, e.cfg, category_filter=a.category, topics=a.topic, urls=a.url,
                                           feeds=a.rss, imported=imported, limit=a.limit, log=log)
        if cmd in ('rank', 'recommend', 'list'):
            if cmd == 'rank':
                # Same provider safety policy as make; --ai is explicit authorization for subscription calls.
                from ..topics.store import write
                from ..topics.schema import now
                import uuid
                calls = []
                with core.llmmod.provider_session(e.cfg.get('llm', {}), calls.append):
                    result = await e.rank(limit=a.limit, category=a.category, use_llm=a.ai)
                record = {'created_at':now(), 'config_version':'topic-strategy-v1', 'calls':calls}
                write(e.store.root / 'evaluations' / (uuid.uuid4().hex + '.json'), record)
                if a.b2b:
                    result = e.list(limit=a.limit, category=a.category, b2b=True)
                return {**result, 'ai_calls':calls}
            return e.list(limit=a.limit, category=a.category, recommended=cmd=='recommend', b2b=a.b2b)
        if cmd == 'calendar':
            return {'status':'ok', **calendar.make_calendar(e.store, e.cfg, weeks=a.weeks, count=a.count, start=a.start)}
        if cmd == 'request':
            intent = detect_topic_request(a.text)
            if intent['action'] in ('recommend', 'list'):
                if not e.store.topics():
                    await discovery.collect(e.store, e.cfg, category_filter=intent['category'], log=log)
                    await e.rank()
                return e.list(limit=intent['limit'], category=intent['category'], recommended=intent['action']=='recommend', b2b=intent['b2b'])
            if intent['action'] == 'calendar':
                return {'status':'ok', **calendar.make_calendar(e.store, e.cfg, weeks=intent['weeks'])}
            if intent['action'] == 'create':
                key = e.select(intent['select'], a.selection)
                # "1번으로 만들어줘" explicitly approves the seen choice; factual gates still apply.
                await e.approve(key)
                return await e.create(key, fmt=intent['format'], pages=intent['pages'], dry_run=a.dry_run, log=log)
            raise ValueError('전략 요청을 알아보지 못했습니다. 추천/목록/캘린더/번호 제작을 지정해 주세요')
        key = a.topic_id or e.select(a.select, a.selection)
        if cmd == 'inspect':
            topic = e.store.get(key)
            return {'status':'ok', 'topic':topic.model_dump(), 'evidence':[r.model_dump() for r in e.store.evidence(topic)]}
        if cmd == 'verify':
            topic = await e.refresh(key)
        elif cmd == 'approve':
            topic = await e.approve(key, followup=a.followup)
        elif cmd in ('exclude','hold','release','review'):
            topic = e.transition(key, cmd)
        elif cmd == 'published':
            topic = await e.record_published(key, url=a.url)
        elif cmd == 'edit':
            facts = None
            if a.facts:
                with open(a.facts, encoding='utf-8') as file:
                    facts = json.load(file)
            topic = e.edit(key, title=a.title, direction=a.direction, character=a.character, facts=facts,
                           followup=a.followup, series_parent_id=a.series_parent, update_of=a.update_of)
        elif cmd == 'schedule':
            topic = calendar.reschedule(e.store, key, a.date)
        elif cmd == 'plan':
            return {'status':'planned', 'plan':(await e.plan(key, fmt=a.format, pages=a.pages, preview=a.preview)).model_dump()}
        elif cmd == 'create':
            return await e.create(key, fmt=a.format, pages=a.pages, dry_run=a.dry_run, also=a.also, log=log)
        else:
            raise ValueError('지원하지 않는 전략 명령')
        return {'status':'ok', 'topic':topic.model_dump()}
    except FileNotFoundError as exc:
        raise core.FactoryError('not_found', '주제 또는 근거 파일이 없습니다') from exc
    except (ValueError, KeyError) as exc:
        raise core.FactoryError('invalid', str(exc)) from exc
