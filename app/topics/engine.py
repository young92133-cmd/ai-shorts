"""Application service and approval workflow. Never posts to a social platform."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from . import discovery, verification, scoring, dedup, story, calendar, business
from .schema import Topic, StoryPlan, Publication, timestamp, now
from .store import Store, write


def fingerprint(store: Store, t: Topic) -> str:
    data = {'title': t.title, 'angle': t.angle, 'facts': [f.model_dump(exclude={'verification', 'checks'}) for f in t.facts],
            'evidence': [e.model_dump(exclude={'retrieved_at'}) for e in store.evidence(t)],
            'character': t.character_id, 'character_rights': t.character_rights,
            'followup': t.followup_requested, 'update_of': t.update_of, 'series_parent_id': t.series_parent_id}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def recommendation_row(t: Topic, at=None) -> dict:
    return {'topic_id': t.topic_id, 'title': t.title, 'category': t.category,
            'score': t.score.model_dump() if t.score else None, 'verification': t.verification,
            'eligible': verification.eligible(t, at), 'verification_reasons': t.verification_reasons,
            'status': t.status, 'duplicate_of': t.duplicate_of, 'source_urls': t.source_urls,
            'published_at': t.published_at, 'event_date': t.event_date,
            'b2b': t.opportunity.model_dump() if t.opportunity else None}


class Engine:
    def __init__(self, store: Store, cfg: dict, *, character_root=None):
        self.store, self.cfg, self.character_root = store, cfg, character_root

    async def rank(self, *, limit=10, category='all', use_llm=False, at=None) -> dict:
        dedup.deduplicate(self.store, at)
        if use_llm:
            from .semantic import review
            await review(self.store, self.cfg)
        for t in self.store.topics():
            if t.status in ('excluded', 'published', 'held') or t.duplicate_of:
                continue
            try:
                if t.valid_until and timestamp(t.valid_until) < timestamp(at or now()):
                    t = await self.refresh(t.topic_id, at)
                else:
                    verification.verify(self.store, t, self.cfg, at)
            except (OSError, ValueError) as exc:
                from ..pipeline.llm import safe_error
                t.verification, t.valid_until, t.approval_fingerprint = 'needs_review', '', ''
                t.verification_reasons = ['저장된 근거 확인 실패: ' + safe_error(exc)]
            t = await scoring.evaluate(t, self.cfg, use_llm=use_llm)
            t.opportunity = business.assess(t)
            if verification.eligible(t, at) and t.score.recommendation == 'priority' and t.status == 'scored':
                t.status = 'shortlisted'
            self.store.save_topic(t, 'score')
        return self.list(limit=limit, category=category, at=at)

    def list(self, *, limit=10, category='all', recommended=False, b2b=False, at=None) -> dict:
        if not 1 <= limit <= 100:
            raise ValueError('목록 개수는 1~100입니다')
        items = [t for t in self.store.topics() if category in ('all', t.category) and not t.duplicate_of and t.status not in ('excluded', 'published', 'held')]
        if recommended:
            items = [t for t in items if verification.eligible(t, at) and t.score and t.score.recommendation == 'priority']
        if b2b:
            items = [t for t in items if verification.eligible(t, at) and t.opportunity and t.opportunity.b2b_fit_score >= 65]
        items.sort(key=lambda t:(verification.eligible(t, at), t.opportunity.b2b_fit_score if b2b and t.opportunity else t.score.total_score if t.score else 0), reverse=True)
        rows = [dict(number=i, **recommendation_row(t, at)) for i,t in enumerate(items[:limit], 1)]
        cid = 'selection_' + uuid.uuid4().hex[:12]
        selection = {'selection_id': cid, 'created_at': at or now(), 'items': [{'number': r['number'], 'topic_id': r['topic_id']} for r in rows]}
        write(self.store.path('selections', cid), selection)
        top = [r for r in rows if r['eligible'] and r['score'] and r['score']['recommendation'] == 'priority'][:3]
        return {'status': 'ok', 'selection_id': cid, 'topics': rows, 'top3': top,
                'storage_errors':self.store.errors,
                'notice': '내부 추정 점수이며 실제 검색량·조회수·성과 예측이 아닙니다.'}

    def select(self, number: int, selection_id: str) -> str:
        if not selection_id:
            raise ValueError('후보 번호에는 사용자가 본 selection_id를 반드시 지정해야 합니다')
        data = self.store.read(self.store.path('selections', selection_id))
        if not data:
            raise ValueError('후보 목록이 없습니다')
        row = next((r for r in data['items'] if r['number'] == number), None)
        if not row:
            raise ValueError('목록에 없는 후보 번호입니다')
        return row['topic_id']

    async def refresh(self, topic_id: str, at=None) -> Topic:
        topic = self.store.get(topic_id)
        failures = []
        for old in self.store.evidence(topic):
            try:
                fresh = await discovery.fetch_evidence(old.url)
                fresh.evidence_id = old.evidence_id
                self.store.save_evidence(fresh)
            except Exception as exc:
                from ..pipeline.llm import safe_error
                failures.append(safe_error(exc))
        if failures or not topic.evidence_ids:
            topic.verification, topic.status, topic.approval_fingerprint = 'needs_review', 'held', ''
            topic.verification_reasons = ['발행일 재검증 실패: ' + x for x in failures] or ['근거 자료 없음']
            topic.valid_until = ''
            self.store.save_topic(topic, 'refresh_failed')
            return topic
        previous = topic.approval_fingerprint
        topic = verification.verify(self.store, topic, self.cfg, at)
        if previous and fingerprint(self.store, topic) != previous:
            topic.status, topic.approval_fingerprint = 'held', ''
            topic.verification_reasons.append('원자료 변경: 재승인 필요')
            self.store.save_topic(topic, 'refresh_changed')
        return topic

    async def current(self, topic_id: str, at=None) -> Topic:
        topic = self.store.get(topic_id)
        deadline = timestamp(topic.valid_until)
        if not deadline or deadline < timestamp(at or now()):
            return await self.refresh(topic_id, at)
        return verification.verify(self.store, topic, self.cfg, at)

    async def approve(self, topic_id: str, *, followup=False, at=None) -> Topic:
        topic = self.store.get(topic_id)
        if followup:
            topic.followup_requested, topic.duplicate_of = True, ''
            self.store.save_topic(topic, 'explicit_followup')
        topic = await self.current(topic_id, at)
        if not verification.eligible(topic, at) or not topic.score or topic.score.recommendation == 'hold':
            raise ValueError('승인 보류: 검증 상태·유효기간·중복·점수·사용 권한을 확인해 주세요')
        topic.status, topic.approved_at = 'approved', at or now()
        topic.approval_fingerprint = fingerprint(self.store, topic)
        return self.store.save_topic(topic, 'human_approve')

    def edit(self, topic_id: str, *, title=None, direction=None, character=None, facts=None, followup=None, series_parent_id=None, update_of=None) -> Topic:
        topic = self.store.get(topic_id)
        if topic.status == 'published':
            raise ValueError('발행 기록 수정 대신 새 후속/업데이트 주제를 등록해 주세요')
        if title is not None:
            if not title.strip():
                raise ValueError('제목은 비울 수 없습니다')
            topic.title = title.strip()
        if direction is not None:
            topic.angle = direction
        if character is not None:
            from ..carousel.characters import get_character
            get_character(character, self.character_root)
            topic.character_id = character
        if facts is not None:
            from .schema import Fact
            topic.facts = [Fact.model_validate(f) for f in facts]
        for key,val in (('followup_requested', followup), ('series_parent_id', series_parent_id), ('update_of', update_of)):
            if val is not None:
                setattr(topic, key, val)
        if topic.followup_requested or topic.series_parent_id or topic.update_of:
            topic.duplicate_of = ''
        topic.status, topic.verification, topic.approval_fingerprint = 'discovered', 'needs_review', ''
        topic.score = None
        return self.store.save_topic(topic, 'human_edit')

    def transition(self, topic_id: str, action: str) -> Topic:
        topic = self.store.get(topic_id)
        if action == 'exclude' and topic.status != 'published':
            topic.status = 'excluded'
        elif action == 'hold' and topic.status != 'published':
            topic.status = 'held'
        elif action == 'release' and topic.status == 'held':
            topic.status, topic.verification, topic.valid_until = 'discovered', 'needs_review', ''
        elif action == 'review' and topic.status == 'generated':
            if topic.approval_fingerprint != fingerprint(self.store, topic):
                raise ValueError('승인 이후 근거가 바뀌었습니다. 다시 검증·승인해 주세요')
            topic.status = 'reviewed'
        else:
            raise ValueError('현재 상태에서 요청한 작업을 할 수 없습니다')
        if action in ('exclude', 'hold', 'release'):
            topic.approval_fingerprint = ''
        return self.store.save_topic(topic, 'human_' + action)

    async def plan(self, topic_id: str, *, fmt='hybrid', pages=8, preview=False, at=None) -> StoryPlan:
        topic = await self.current(topic_id, at)
        if not preview and (topic.status not in ('approved', 'planned', 'generated', 'reviewed') or
                            topic.approval_fingerprint != fingerprint(self.store, topic)):
            raise ValueError('사용자가 승인한 주제만 제작 계획을 확정할 수 있습니다')
        plan = story.build_story(topic, self.store.evidence(topic), fmt=fmt, pages=pages,
                                 character_root=self.character_root, direction=topic.angle, at=at)
        key = topic_id + '_' + fmt
        previous_plan = self.store.read(self.store.path('plans', key))
        if previous_plan is not None:
            write(self.store.root / 'plan_history' / key / (uuid.uuid4().hex + '.json'), previous_plan)
        write(self.store.path('plans', key), plan.model_dump())
        if not preview:
            topic.status = 'planned'
            self.store.save_topic(topic, 'story_plan')
        return plan

    async def create(self, topic_id: str, *, fmt='hybrid', pages=8, dry_run=False, also=None, at=None, log=print) -> dict:
        if fmt not in ('shorts', 'card_news', 'insta_toon', 'hybrid', 'all'):
            raise ValueError('지원하지 않는 제작 형식')
        modes = list(dict.fromkeys((['hybrid', 'shorts'] if fmt == 'all' else [fmt]) + list(also or [])))
        if any(m not in ('shorts', 'card_news', 'insta_toon', 'hybrid') for m in modes):
            raise ValueError('추가 제작 형식은 shorts/card_news/insta_toon/hybrid입니다')
        packets = []
        for mode in modes:
            plan = await self.plan(topic_id, fmt='hybrid' if mode == 'shorts' else mode, pages=pages, at=at)
            packets.append({'format': mode, 'story_plan': plan.model_dump(), 'engine': 'app.pipeline.run' if mode == 'shorts' else 'app.carousel.pipeline'})
        if dry_run:
            return {'status': 'planned', 'topic_id': topic_id, 'delivery': packets, 'cost': 0, 'generated': False}
        from ..factory import core
        from ..carousel.schema import MasterContent
        results = []
        for packet in packets:
            plan = StoryPlan.model_validate(packet['story_plan'])
            try:
                if packet['format'] == 'shorts':
                    narration = '\n'.join(f.text for f in MasterContent.model_validate(plan.master).facts)
                    result = await core.make(script_text=narration, output_format='shorts', benchmark='off', visuals='cards', log=log)
                    if result.get('project_id'):
                        write(Path(result['project_dir']) / 'topic_strategy.json', plan.model_dump())
                else:
                    result = await core.make_planned_carousel(plan, self.store.evidence(self.store.get(topic_id)),
                                                              character_root=self.character_root, log=log)
            except Exception as exc:
                from ..pipeline.llm import safe_error
                result = {'status': 'failed', 'message': safe_error(exc)}
            results.append({'format': packet['format'], **result})
        topic = self.store.get(topic_id)
        topic.projects += results
        topic.current_projects = results
        completed = all(r.get('status') == 'render_complete' for r in results)
        topic.status = 'generated' if completed else 'planned'
        self.store.save_topic(topic, 'production_result')
        return {'status': 'generated' if completed else 'partial_failure', 'topic_id': topic_id, 'results': results}

    async def record_published(self, topic_id: str, *, url='', at=None) -> Topic:
        topic = self.store.get(topic_id)
        if topic.status != 'reviewed':
            raise ValueError('제작물 검토 완료 후에만 발행 이력을 기록할 수 있습니다')
        topic = await self.refresh(topic_id, at) if topic.freshness != 'evergreen' else await self.current(topic_id, at)
        if not verification.eligible(topic, at) or topic.approval_fingerprint != fingerprint(self.store, topic) or topic.status != 'reviewed':
            raise ValueError('발행 보류: 근거 재확인 또는 변경된 내용의 재승인이 필요합니다')
        current_projects = topic.current_projects or topic.projects
        if not current_projects or any(r.get('status') != 'render_complete' for r in current_projects):
            raise ValueError('아직 제작이 끝나지 않았습니다')
        self.store.add_publication(Publication(topic_id=topic.topic_id, published_at=at or now(), category=topic.category,
            title=topic.title, core_claim=topic.core_claim or topic.summary, event_key=topic.event_key,
            keywords=topic.keywords, target_audience=topic.target_audience, url=url,
            project_id=topic.projects[-1].get('project_id', '')).model_dump())
        topic.status = 'published'
        return self.store.save_topic(topic, 'human_record_publication')
