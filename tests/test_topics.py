from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx

from app.topics import discovery
from app.topics.schema import Evidence, Topic, Fact, Citation, ScoreParts, now, timestamp, KST
from app.topics.store import Store, identifier

TODAY = '2026-10-08T09:00:00+09:00'
# 수집 단계는 본문 300자 미만 페이지를 기사로 보지 않는다 (목록·스크립트 페이지 제외)
ARTICLE = '전세와 월세는 주거 계약의 유형입니다. ' * 20


def evidence(text='전세와 월세는 주거 계약의 유형입니다.', url='https://www.molit.go.kr/example', **kw):
    return Evidence(evidence_id=identifier('ev', url), url=url, title='주거 교육 자료', text=text,
                    published_at=TODAY, retrieved_at=TODAY, **kw)


def topic_fixture(store, title='전세와 월세 중 어떤 선택이 더 유리할까?', category='housing', **kw):
    e = evidence()
    store.save_evidence(e)
    fact = Fact(fact_id='f1', claim=e.text, citations=[Citation(evidence_id=e.evidence_id, excerpt=e.text)])
    t = Topic(topic_id=identifier('topic', title), title=title, category=category, summary=e.text,
              source_urls=[e.url], evidence_ids=[e.evidence_id], facts=[fact], freshness='evergreen', **kw)
    store.save_topic(t)
    return t


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()


class CollectionTests(StoreCase):
    def test_categories_and_preserved_dates(self):
        e = evidence(event_date='2026-10-01')
        ids = discovery.ingest(self.store, [
            {'title': '전세 월세 비교', 'evidence': [e.model_dump()]},
            {'title': 'ETF 투자 기초'}, {'title': '경제 물가 지표 발표'}])
        self.assertEqual({self.store.get(i).category for i in ids}, {'housing', 'finance', 'economy'})
        first = self.store.get(ids[0])
        self.assertEqual(first.published_at, TODAY)
        self.assertEqual(self.store.evidence(first)[0].event_date, '2026-10-01')
        ledger = json.loads((self.store.root / 'sources.json').read_text(encoding='utf-8'))
        self.assertTrue(ledger)

    def test_repeat_collection_and_audit(self):
        row = {'title': '전세 월세 비교', 'evidence': [evidence().model_dump()]}
        discovery.ingest(self.store, [row, row])
        self.assertEqual(len(self.store.topics()), 1)
        self.assertEqual(len(list((self.store.root / 'audit').rglob('*.json'))), 2)

    def test_rss_atom_and_untrusted_xml(self):
        rss = '<rss><channel><item><title>금리 발표</title><link>https://bok.or.kr/x</link><pubDate>Thu, 08 Oct 2026 00:00:00 GMT</pubDate></item></channel></rss>'
        self.assertEqual(discovery.parse_feed(rss)[0]['published_at'], TODAY)
        atom = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>통계</title><link href="https://kosis.kr/a"/></entry></feed>'
        self.assertEqual(discovery.parse_feed(atom)[0]['url'], 'https://kosis.kr/a')
        with self.assertRaises(ValueError):
            discovery.parse_feed('<!DOCTYPE rss><rss/>')

    def test_official_host_boundary(self):
        self.assertTrue(discovery.official('https://www.bok.or.kr/a'))
        self.assertFalse(discovery.official('https://bok.or.kr.attacker.com/a'))

    def test_invalid_path(self):
        with self.assertRaises(ValueError):
            self.store.path('topics', '../oops')

    def test_collection_partial_outage(self):
        async def work():
            with patch.object(discovery, 'fetch_evidence', new=AsyncMock(side_effect=[RuntimeError('outage'), evidence(text=ARTICLE)])):
                return await discovery.collect(self.store, {}, urls=['https://news.example/1', 'https://molit.go.kr/example'], log=lambda _: None)
        import asyncio
        result = asyncio.run(work())
        self.assertEqual(result['count'], 1)
        self.assertEqual(len(result['errors']), 1)

    def test_feed_discovery_not_verified(self):
        discovery.ingest(self.store, [{'title': '뉴스'}])
        self.assertEqual(self.store.topics()[0].verification, 'unverified')

    def test_direct_topic_reuses_news_search_and_records_evidence(self):
        import asyncio
        from app.pipeline.models import ResearchDoc
        async def work():
            with patch.object(discovery, 'search', new=AsyncMock(return_value=[ResearchDoc(title='공식 자료', url='https://molit.go.kr/example', text='본문')])), \
                 patch.object(discovery, 'fetch_evidence', new=AsyncMock(return_value=evidence(text=ARTICLE))):
                return await discovery.collect(self.store, {}, topics=['전세 월세 비교'])
        result = asyncio.run(work())
        t = self.store.get(result['topic_ids'][0])
        self.assertEqual(t.title, '전세 월세 비교')
        self.assertEqual(len(t.evidence_ids), 1)

    def test_evergreen_and_import_cannot_forge_approval(self):
        keys = discovery.ingest(self.store, [{'title':'ETF 기초', 'status':'approved', 'verification':'verified', 'valid_until':'2099-01-01'},
                                           {'title':'금리 정책 발표'}])
        a, b = [self.store.get(i) for i in keys]
        self.assertEqual(a.freshness, 'evergreen')
        self.assertEqual(a.status, 'discovered')
        self.assertEqual(a.verification, 'unverified')
        self.assertEqual(b.freshness, 'current')


class VerificationScoringTests(StoreCase):
    def test_weight_boundaries_and_100_ceiling(self):
        from app.topics.scoring import weighted_score
        self.assertEqual(weighted_score(dict(interest=5, story=5, utility=5, business=5)), 100)
        self.assertEqual(weighted_score(dict(interest=0, story=0, utility=0, business=0)), 0)
        self.assertEqual(weighted_score(dict(interest=5, story=0, utility=0, business=0)), 30)
        self.assertEqual(weighted_score(dict(interest=0, story=5, utility=0, business=0)), 25)
        self.assertEqual(weighted_score(dict(interest=0, story=0, utility=5, business=0)), 25)
        self.assertEqual(weighted_score(dict(interest=0, story=0, utility=0, business=5)), 20)
        for bad in (6, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                weighted_score(dict(interest=bad, story=5, utility=5, business=5))

    def test_primary_exact_statement_and_no_fake_citation(self):
        from app.topics.verification import verify
        t = topic_fixture(self.store)
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'verified')
        t.facts[0].claim = '집값은 반드시 오릅니다.'
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'unverified')

    def test_missing_primary_and_syndication_hold(self):
        from app.topics.verification import verify
        t = topic_fixture(self.store)
        e = evidence(url='https://news.example/story')
        self.store.save_evidence(e)
        t.evidence_ids = [e.evidence_id]
        t.facts[0].citations = [Citation(evidence_id=e.evidence_id, excerpt=e.text)]
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'needs_review')
        second = evidence(url='https://yna.co.kr/story')
        third = evidence(url='https://hani.co.kr/story')
        for row in (second, third):
            self.store.save_evidence(row)
            t.evidence_ids.append(row.evidence_id)
            t.facts[0].citations.append(Citation(evidence_id=row.evidence_id, excerpt=row.text))
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'needs_review')
        third.text += ' 서로 독립적인 보도입니다.'
        self.store.save_evidence(third)
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'verified')

    def test_unkeyed_conflicting_numbers_and_date_not_renewed(self):
        from app.topics.verification import verify
        t = topic_fixture(self.store)
        a = evidence('2026-10-08 기준 금리는 4%입니다.')
        b = evidence('2026-10-08 기준 금리는 5%입니다.', url='https://bok.or.kr/test')
        for e in (a, b):
            self.store.save_evidence(e)
        t.evidence_ids = [a.evidence_id, b.evidence_id]
        t.facts = []
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'conflicting')

    def test_statistics_require_original_primary_and_exaggerated_title(self):
        from app.topics.verification import verify
        t = topic_fixture(self.store, title='폭등한 평균 주거비')
        e = evidence('2026-10-08 기준 평균 주거비는 10만원입니다.', url='https://kosis.kr/table')
        self.store.save_evidence(e)
        t.evidence_ids = [e.evidence_id]
        t.facts = [Fact(fact_id='f1', claim=e.text, citations=[Citation(evidence_id=e.evidence_id, excerpt=e.text)],
                        as_of='2026-10-08', unit='만원')]
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'needs_review')
        self.assertIn('통계 원자료 미확인', t.facts[0].checks)
        t.facts[0].statistic_original_url = e.url
        t.title = '평균 주거비 기준일 확인'
        t.compliance_flags = []
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'verified')

    def test_cached_verification_does_not_extend_news_freshness(self):
        from app.topics.verification import verify, eligible
        t = topic_fixture(self.store)
        t.freshness = 'current'
        verify(self.store, t, at=TODAY)
        initial = t.valid_until
        verify(self.store, t, at='2026-10-09T10:00:00+09:00')
        self.assertEqual(t.valid_until, initial)
        self.assertFalse(eligible(t, at='2026-10-09T10:00:00+09:00'))

    def test_title_numeric_claim_must_have_evidence_but_page_counts_are_allowed(self):
        from app.topics.verification import verify
        t = topic_fixture(self.store, title='주거 대출 금리 9%')
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'needs_review')
        t.title = '전세와 월세 5가지 비교'
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'verified')

    def test_numeric_scope_and_original_statistics(self):
        from app.topics.verification import verify
        t = topic_fixture(self.store)
        e = evidence(text='2026-10-08 기준 근로자 대출 금리는 4%입니다.')
        self.store.save_evidence(e)
        t.facts = [Fact(fact_id='f1', claim=e.text, citations=[Citation(evidence_id=e.evidence_id, excerpt=e.text)])]
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'needs_review')
        t.facts[0].as_of, t.facts[0].unit, t.facts[0].applies_to = '2026-10-08', '%', '근로자'
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'verified')
        t.facts[0].unit = '원'
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'needs_review')

    def test_conflict_and_outdated_even_when_retrieved_today(self):
        from app.topics.verification import verify, eligible
        t = topic_fixture(self.store)
        a = evidence('2026-10-08 기준 금리는 4%입니다.')
        b = evidence('2026-10-08 기준 금리는 5%입니다.', url='https://www.bok.or.kr/example')
        for e in (a, b):
            self.store.save_evidence(e)
        t.evidence_ids = [a.evidence_id, b.evidence_id]
        t.facts = [Fact(fact_id=f'f{i}', claim=e.text, citations=[Citation(evidence_id=e.evidence_id, excerpt=e.text)],
                        as_of='2026-10-08', unit='%', conflict_key='기준금리', value=v) for i, (e, v) in enumerate(((a, '4'), (b, '5')), 1)]
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'conflicting')
        self.assertFalse(eligible(t, at=TODAY))
        t.freshness, t.facts, t.event_date = 'current', [t.facts[0]], '2026-09-01'
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'outdated')

    def test_future_as_of_and_guarantees_held(self):
        from app.topics.verification import verify
        t = topic_fixture(self.store, title='확정 수익 투자')
        self.assertEqual(verify(self.store, t, at=TODAY).verification, 'needs_review')
        self.assertTrue(t.compliance_flags)

    def test_fact_forecast_opinion_separation(self):
        from app.topics.verification import extract_facts
        t = topic_fixture(self.store)
        rows = extract_facts(t, [evidence('전세와 월세는 주거 계약입니다. 앞으로 주거비가 오를 것으로 예상됩니다. 이것은 전문가의 개인 의견입니다.')])
        self.assertEqual({f.kind for f in rows}, {'fact', 'forecast', 'opinion'})

    def test_dedup_event_merge_but_not_different_angles(self):
        from app.topics.dedup import deduplicate
        t = topic_fixture(self.store, event_key='event1', core_claim='전월세는 계약 유형')
        second = t.model_copy(deep=True, update={'topic_id': 'topic_second', 'title': '또 다른 언론 전월세', 'source_urls': ['https://other.example/x']})
        self.store.save_topic(second)
        deduplicate(self.store, at=TODAY)
        merged = self.store.topics()
        self.assertEqual(sum(bool(t.duplicate_of) for t in merged), 1)
        self.assertEqual(len([t for t in merged if not t.duplicate_of][0].source_urls), 2)
        third = second.model_copy(deep=True, update={'topic_id': 'topic_third', 'angle': '신혼부부 보증금', 'duplicate_of': ''})
        t = [t for t in merged if not t.duplicate_of][0]
        t.angle = '사회초년생 월세'
        self.store.save_topic(t)
        self.store.save_topic(third)
        deduplicate(self.store, at=TODAY)
        self.assertFalse(self.store.get(third.topic_id).duplicate_of)

    def test_different_topics_and_explicit_followup(self):
        from app.topics.dedup import deduplicate
        a = topic_fixture(self.store, title='전세계약 등기부 확인')
        b = topic_fixture(self.store, title='전세 보증금과 월세 비교')
        deduplicate(self.store, at=TODAY)
        self.assertFalse(self.store.get(b.topic_id).duplicate_of)
        self.store.add_publication({'topic_id': 'old', 'published_at': TODAY, 'category': a.category,
                                    'title': a.title, 'core_claim': a.summary})
        deduplicate(self.store, at=TODAY)
        self.assertEqual(self.store.get(a.topic_id).duplicate_of, 'old')
        a.duplicate_of, a.followup_requested = '', True
        self.store.save_topic(a)
        deduplicate(self.store, at=TODAY)
        self.assertFalse(self.store.get(a.topic_id).duplicate_of)


class StoryTests(StoreCase):
    def test_eight_pages_character_registry_and_shared_schema(self):
        from app.topics.story import build_story, ROLES
        from app.topics.verification import verify
        from app.carousel.schema import CarouselPlan, MasterContent, ComicPage
        t = verify(self.store, topic_fixture(self.store), at=TODAY)
        p = build_story(t, self.store.evidence(t), at=TODAY)
        self.assertEqual([r.role for r in p.pages], list(ROLES))
        self.assertEqual(len(p.pages), 8)
        self.assertEqual(p.character_id, 'tory_01')
        self.assertTrue(any(isinstance(page, ComicPage) for page in CarouselPlan.model_validate(p.carousel_plan).pages))
        self.assertEqual(MasterContent.model_validate(p.master).facts[0].text, t.facts[0].claim)
        self.assertTrue(p.pages[3].fact_ids)
        self.assertIn('창작', p.dialogue_disclaimer)
        for mode in ('card_news', 'insta_toon'):
            q = build_story(t, self.store.evidence(t), fmt=mode, at=TODAY)
            cards = CarouselPlan.model_validate(q.carousel_plan)
            self.assertEqual(sum(isinstance(page, ComicPage) for page in cards.pages), 6 if mode == 'insta_toon' else 0)

    def test_missing_character_and_unauthorized_reference(self):
        from app.topics.story import build_story
        from app.topics.verification import verify
        t = verify(self.store, topic_fixture(self.store, character_id='missing_01'), at=TODAY)
        with self.assertRaises(KeyError):
            build_story(t, self.store.evidence(t), at=TODAY)
        t.character_id, t.character_rights = 'tory_01', 'benchmark_account'
        verify(self.store, t, at=TODAY)
        with self.assertRaises(ValueError):
            build_story(t, self.store.evidence(t), at=TODAY)


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from app.topics.engine import Engine
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))
        self.engine = Engine(self.store, {})
        self.t = topic_fixture(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    async def prepare(self):
        await self.engine.rank(at=TODAY)
        return await self.engine.approve(self.t.topic_id, at=TODAY)

    async def test_approval_required_and_dry_run_delivery(self):
        await self.engine.rank(at=TODAY)
        with self.assertRaises(ValueError):
            await self.engine.create(self.t.topic_id, dry_run=True, at=TODAY)
        await self.prepare()
        out = await self.engine.create(self.t.topic_id, dry_run=True, at=TODAY, fmt='all', also=['card_news'])
        self.assertEqual([r['format'] for r in out['delivery']], ['hybrid', 'shorts', 'card_news'])
        self.assertEqual(self.store.get(self.t.topic_id).status, 'planned')
        self.assertFalse(out['generated'])

    async def test_approved_plan_reaches_existing_engine_without_replanning(self):
        from app.factory import core
        from app.carousel import pipeline
        await self.prepare()
        captures = []
        async def fake_carousel(job_dir, **kw):
            captures.append(kw)
            d = job_dir / 'hybrid'
            d.mkdir(parents=True)
            paths = []
            for i in range(8):
                p = d / f'card_{i+1:02d}.png'
                p.write_bytes(b'test fixture')
                paths.append(str(p))
            m = d / 'manifest.json'
            m.write_text('{}', encoding='utf-8')
            return {'format':'hybrid', 'dir':str(d), 'pages':paths, 'manifest':str(m), 'title':kw['text']}
        with patch.object(core, 'output_root', return_value=self.store.root / 'output'), \
             patch.object(pipeline, 'run_carousel', new=fake_carousel), \
             patch.object(pipeline, 'build_master', new=AsyncMock(side_effect=AssertionError('no AI'))), \
             patch.object(pipeline, 'plan_pages', new=AsyncMock(side_effect=AssertionError('no AI'))):
            out = await self.engine.create(self.t.topic_id, at=TODAY, log=lambda _:None)
        self.assertEqual(out['status'], 'generated')
        self.assertEqual(len(captures[0]['prepared_plan'].pages), 8)
        self.assertEqual(captures[0]['prepared_master'].topic, self.t.title)
        self.assertFalse(captures[0]['image_search'])
        self.assertEqual(captures[0]['cfg']['carousel']['image_provider'], 'none')
        self.engine.transition(self.t.topic_id, 'review')
        t = await self.engine.record_published(self.t.topic_id, at=TODAY)
        self.assertEqual(t.status, 'published')
        self.assertEqual(len(self.store.history()), 1)

    async def test_shared_carousel_uses_prepared_content(self):
        from app.carousel import pipeline
        from app.carousel.schema import MasterContent, CarouselPlan
        await self.prepare()
        plan = await self.engine.plan(self.t.topic_id, at=TODAY)
        def fake_render(page, tpl, out, assets):
            out.write_bytes(b'fixture')
            return {'path':str(out), 'fallback_used':False, 'image_use':'mascot' if hasattr(page, 'panels') else 'graphic'}
        with patch.object(pipeline, 'build_master', new=AsyncMock(side_effect=AssertionError('must bypass'))), \
             patch.object(pipeline, 'plan_pages', new=AsyncMock(side_effect=AssertionError('must bypass'))), \
             patch.object(pipeline, 'gather_inputs', new=AsyncMock(side_effect=AssertionError('must bypass'))), \
             patch.object(pipeline, 'render_page', side_effect=fake_render):
            out = await pipeline.run_carousel(self.store.root / 'prod', fmt='hybrid', mode='topic_strategy', text=self.t.title,
                cfg={'llm':{}, 'carousel':{'image_provider':'none'}}, inputs={'topic':self.t.title, 'docs':[]}, image_search=False,
                prepared_master=MasterContent.model_validate(plan.master), prepared_plan=CarouselPlan.model_validate(plan.carousel_plan),
                progress=lambda *args:None)
        self.assertEqual(out['page_count'] if 'page_count' in out else len(out['pages']), 8)

    async def test_conflicting_or_modified_topic_cannot_create(self):
        from app.factory import core
        await self.prepare()
        self.engine.edit(self.t.topic_id, title='전세 월세 비교 새 제목')
        with patch.object(core, 'make_planned_carousel', new=AsyncMock()) as render:
            with patch.object(discovery, 'fetch_evidence', new=AsyncMock(return_value=evidence())):
                with self.assertRaises(ValueError):
                    await self.engine.create(self.t.topic_id, at=TODAY)
            render.assert_not_called()

    async def test_news_expiry_recheck_outage_and_no_auto_verification(self):
        await self.prepare()
        t = self.store.get(self.t.topic_id)
        t.freshness, t.valid_until = 'current', '2026-10-08T08:00:00+09:00'
        self.store.save_topic(t)
        with patch.object(discovery, 'fetch_evidence', new=AsyncMock(side_effect=RuntimeError('offline'))) as fetch:
            t = await self.engine.current(t.topic_id, at=TODAY)
        self.assertTrue(fetch.called)
        self.assertEqual(t.status, 'held')
        self.assertEqual(t.verification, 'needs_review')
        self.assertFalse(t.approval_fingerprint)

    async def test_selection_bound_to_seen_list(self):
        result = await self.engine.rank(at=TODAY)
        other = topic_fixture(self.store, title='월급 관리 기초', category='finance')
        await self.engine.rank(at=TODAY)
        self.assertEqual(self.engine.select(1, result['selection_id']), self.t.topic_id)
        with self.assertRaises(ValueError):
            self.engine.select(1, '')

    async def test_conflict_blocks_approval_and_dispatch(self):
        from app.factory import core
        await self.prepare()
        t = self.store.get(self.t.topic_id)
        t.facts[0].citations[0].result = 'contradicts'
        self.store.save_topic(t)
        with patch.object(core, 'make_planned_carousel', new=AsyncMock()) as factory:
            with self.assertRaises(ValueError):
                await self.engine.create(t.topic_id, at=TODAY)
            factory.assert_not_called()

    async def test_pub_news_fetches_again_and_preserves_human_gate(self):
        from app.topics.engine import fingerprint
        await self.prepare()
        t = self.store.get(self.t.topic_id)
        t.freshness, t.status = 'current', 'reviewed'
        t.projects = [{'status':'render_complete', 'project_id':'test_123'}]
        t.approval_fingerprint = fingerprint(self.store, t)
        self.store.save_topic(t)
        with patch.object(discovery, 'fetch_evidence', new=AsyncMock(return_value=evidence())) as fetch:
            t = await self.engine.record_published(t.topic_id, at=TODAY)
        self.assertTrue(fetch.called)
        self.assertEqual(t.status, 'published')

    async def test_changed_news_requires_reapproval_even_if_original_fact_remains(self):
        await self.prepare()
        modified = evidence(text='전세와 월세는 주거 계약의 유형입니다. 새로운 조건을 확인하세요.')
        with patch.object(discovery, 'fetch_evidence', new=AsyncMock(return_value=modified)):
            t = await self.engine.refresh(self.t.topic_id, at=TODAY)
        self.assertEqual(t.status, 'held')
        self.assertFalse(t.approval_fingerprint)

    async def test_llm_scores_mock_only_and_no_verification_upgrade(self):
        from app.topics import scoring
        t = Topic(topic_id='new_topic', title='월급 관리', category='finance')
        self.store.save_topic(t)
        result = scoring.AIEvaluation(parts=ScoreParts(interest=5, story=5, utility=5, business=5),
                                      reasons={k:'추정 근거' for k in scoring.WEIGHTS})
        with patch.object(scoring, 'ask_structured', new=AsyncMock(return_value=result)) as ask:
            scored = await scoring.evaluate(t, {'llm':{'model':'mock'}}, use_llm=True)
        self.assertEqual(scored.score.total_score, 100)
        self.assertEqual(scored.verification, 'unverified')
        self.assertEqual(scored.score.model, 'mock')

    async def test_semantic_duplicate_review_uses_existing_llm_and_never_auto_approves(self):
        from app.topics import semantic
        t2 = topic_fixture(self.store, title='월급 관리의 새로운 관점', category='finance')
        response = semantic.Review(pairs=[semantic.Pair(first_id=self.t.topic_id, second_id=t2.topic_id,
                                                       relation='new_angle', reason='독자 고민과 관점이 다름')])
        with patch.object(semantic, 'ask_structured', new=AsyncMock(return_value=response)):
            result = await semantic.review(self.store, {'llm':{'model':'mock'}})
        self.assertEqual(result['pairs'][0]['relation'], 'new_angle')
        self.assertEqual(self.store.get(self.t.topic_id).status, 'discovered')

    async def test_broken_source_or_candidate_does_not_break_other_recommendations(self):
        broken = topic_fixture(self.store, title='월급 관리 기초', category='finance')
        broken.evidence_ids = ['missing_evidence']
        self.store.save_topic(broken)
        bad_file = self.store.root / 'topics' / 'broken.json'
        bad_file.write_text('not JSON', encoding='utf-8')
        # 규칙 평가 v1.1: 우선 추천(80+)이 되려면 독자·행동 기준 단서가 제목에 있어야 한다
        self.t.title = '사회초년생 직장인, 전세와 월세 중 어떤 선택이 더 유리할까? 보증금 비교 방법'
        self.store.save_topic(self.t)
        result = await self.engine.rank(at=TODAY)
        self.assertIn(self.t.topic_id, [r['topic_id'] for r in result['top3']])
        self.assertEqual(self.store.get(broken.topic_id).verification, 'needs_review')
        self.assertTrue(result['storage_errors'])

    async def test_regenerate_after_failure_and_plan_revision_preserved(self):
        from app.factory import core
        await self.prepare()
        failed = {'status':'failed', 'message':'temporary'}
        good = {'status':'render_complete', 'project_id':'fixture_success'}
        with patch.object(core, 'make_planned_carousel', new=AsyncMock(side_effect=[failed, good])):
            result = await self.engine.create(self.t.topic_id, at=TODAY, log=lambda _:None)
            self.assertEqual(result['status'], 'partial_failure')
            result = await self.engine.create(self.t.topic_id, at=TODAY, log=lambda _:None)
            self.assertEqual(result['status'], 'generated')
        self.assertEqual(len(self.store.get(self.t.topic_id).projects), 2)
        self.assertTrue(list((self.store.root / 'plan_history').rglob('*.json')))
        self.engine.transition(self.t.topic_id, 'review')
        t = await self.engine.record_published(self.t.topic_id, at=TODAY)
        self.assertEqual(t.status, 'published')


class TopicCliTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from app.factory import __main__ as cli
        from app.topics.engine import Engine
        self.cli = cli
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))
        self.engine = Engine(self.store, {})

    def tearDown(self):
        self.tmp.cleanup()

    async def test_parser_topics_and_existing_format_backward_compatibility(self):
        parser = self.cli._parser()
        for cmd in (['topics','collect','--category','all'], ['topics','rank','--limit','10'],
                    ['topics','recommend','--limit','3'], ['topics','calendar','--weeks','4'],
                    ['topics','approve','--id','topic_abc'], ['topics','create','--id','topic_abc','--format','hybrid']):
            self.assertEqual(parser.parse_args(cmd).cmd, 'topics')
        old = parser.parse_args(['make','--topic','x','--format','information'])
        self.assertEqual(old.content_format, 'information')
        self.assertIsNone(old.output_format)

    async def test_cli_rank_approve_create_dry_run(self):
        from app.factory import topics
        t = topic_fixture(self.store)
        with patch.object(topics, 'engine', return_value=self.engine):
            out = await self.cli._dispatch(self.cli._parser().parse_args(['topics','rank']))
            self.assertEqual(out['topics'][0]['topic_id'], t.topic_id)
            await self.cli._dispatch(self.cli._parser().parse_args(['topics','approve','--id',t.topic_id]))
            packet = await self.cli._dispatch(self.cli._parser().parse_args(['topics','create','--id',t.topic_id,'--dry-run']))
        self.assertFalse(packet['generated'])
        self.assertEqual(len(packet['delivery'][0]['story_plan']['pages']), 8)

    async def test_natural_intents_and_number_selection_context(self):
        from app.factory.intent import detect_topic_request as detect
        self.assertEqual(detect('오늘 인스타툰 만들 주제 5개 추천해줘')['limit'], 5)
        self.assertEqual(detect('이번 주 부동산 주제만 보여줘')['category'], 'housing')
        self.assertEqual(detect('이번 주 콘텐츠 캘린더 만들어줘')['action'], 'calendar')
        self.assertEqual(detect('1번 주제로 8장 하이브리드 인스타툰 만들어줘')['format'], 'hybrid')
        self.assertTrue(detect('B2B 영업에 쓰기 좋은 주제 추천해줘')['b2b'])
        from app.factory import topics, core
        with patch.object(topics, 'engine', return_value=self.engine):
            with self.assertRaises(core.FactoryError):
                await self.cli._dispatch(self.cli._parser().parse_args(['topics','request','1번으로 만들어줘','--dry-run']))

    async def test_existing_research_and_trends_imports(self):
        from app.factory.topics import import_rows
        file = self.store.root / 'research.json'
        file.write_text(json.dumps({'docs':[{'title':'ETF 기초','url':'https://news.example/story','text':'본문'}]}), encoding='utf-8')
        rows = import_rows(file)
        self.assertEqual(rows[0]['evidence'][0]['url'], 'https://news.example/story')
        file.write_text(json.dumps({'candidates':[{'number':1,'topic':'월급 관리'}]}), encoding='utf-8')
        self.assertEqual(import_rows(file)[0]['title'], '월급 관리')


class BusinessCalendarTests(StoreCase):
    def pool(self, n=15):
        from app.topics.verification import verify
        from app.topics.scoring import score_topic
        from app.topics.business import assess
        for i in range(n):
            cat = ('housing', 'finance', 'economy')[i%3]
            t = topic_fixture(self.store, title=f'고민 비교 선택 관리 방법 {cat} {chr(65+i)}', category=cat)
            verify(self.store, t, at=TODAY)
            score_topic(t)
            t.opportunity = assess(t)
            self.store.save_topic(t)

    def test_b2b_housing_and_no_advertising(self):
        from app.topics.business import assess
        t = topic_fixture(self.store)
        opp = assess(t)
        self.assertIn('프롭테크', opp.target_industries)
        self.assertEqual(opp.content_type, 'independent_education')
        self.assertTrue(any('광고' in r for r in opp.compliance_risks))

    def test_rolling_last_20_nine_seven_four(self):
        from app.topics.calendar import quota_state
        rows = [{'category':'housing', 'published_at':f'2026-09-{i:02d}'} for i in range(1,10)]
        rows += [{'category':'finance', 'published_at':f'2026-09-{i:02d}'} for i in range(10,17)]
        rows += [{'category':'economy', 'published_at':f'2026-09-{i:02d}'} for i in range(17,21)]
        q = quota_state([{'category':'economy', 'published_at':'2026-08-01'}, *rows])
        self.assertEqual(q['counts'], {'housing':9, 'finance':7, 'economy':4})
        self.assertEqual(q['deficits'], {'housing':0, 'finance':0, 'economy':0})

    def test_week_and_four_weeks_no_topic_reuse(self):
        from app.topics.calendar import make_calendar
        self.pool()
        first = make_calendar(self.store, {}, weeks=1, at=TODAY)
        self.assertEqual(len(first['entries']), 3)
        second = make_calendar(self.store, {}, weeks=4, start='2026-10-19', at=TODAY)
        self.assertEqual(len(second['entries']), 12)
        self.assertFalse(set(e['topic_id'] for e in first['entries']) & set(e['topic_id'] for e in second['entries']))
        self.assertIsNotNone(first['b2b_sample_topic_id'])

    def test_unfilled_dates_not_filled_with_unverified(self):
        from app.topics.calendar import make_calendar
        topic_fixture(self.store)
        q = make_calendar(self.store, {}, weeks=1, at=TODAY)
        self.assertEqual(len(q['entries']), 0)
        self.assertEqual(len(q['unfilled_dates']), 3)
        self.assertIsNone(q['b2b_sample_topic_id'])

    def test_news_gate_reschedule_and_deficient_category(self):
        from app.topics.calendar import make_calendar, reschedule
        self.pool(6)
        for i in range(10):
            self.store.add_publication({'topic_id':f'old{i}', 'title':f'old{i}', 'category':'housing', 'published_at':f'2026-09-{i+1:02d}'})
        result = make_calendar(self.store, {}, at=TODAY)
        self.assertIn(result['entries'][0]['category'], ('finance', 'economy'))
        reschedule(self.store, result['entries'][0]['topic_id'], '2026-10-20', at=TODAY)
        saved = self.store.read(self.store.path('calendars', result['calendar_id']))
        self.assertEqual(saved['entries'][0]['scheduled_date'], '2026-10-20')

    def test_twenty_slots_achieve_target_without_forcing_bad_topics(self):
        from app.topics.calendar import make_calendar
        self.pool(45)
        result = make_calendar(self.store, {}, weeks=4, count=5, at=TODAY)
        self.assertEqual(len(result['entries']), 20)
        self.assertEqual(result['quota_after']['counts'], {'housing':9, 'finance':7, 'economy':4})

    def test_expiring_news_placed_with_reverification_gate(self):
        from app.topics.calendar import make_calendar
        self.pool(3)
        for t in self.store.topics():
            t.freshness = 'current'
            self.store.save_topic(t)
        result = make_calendar(self.store, {}, at=TODAY)
        self.assertTrue(all(e['publication_gate']=='reverify_on_publication_date' for e in result['entries']))


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_addresses_rejected(self):
        with patch.object(discovery.socket, 'getaddrinfo', return_value=[(2,1,6,'',('127.0.0.1',80))]):
            with self.assertRaises(ValueError):
                await discovery.public_url('http://localhost/data')

    async def test_redirect_checked_before_accessing_forbidden_path(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(302,headers={'location':'/forbidden'})))
        try:
            with patch.object(discovery, 'public_url', new=AsyncMock()):
                with self.assertRaises(ValueError):
                    await discovery._get(client, 'https://public.example/start', allowed=lambda url:'forbidden' not in url)
        finally:
            await client.aclose()


class RealPageFilterTests(unittest.TestCase):
    """2026-10-08 실수집에서 후보로 들어온 비기사 페이지 유형 회귀."""

    def ev(self, url, title, text):
        return Evidence(evidence_id='ev_x', url=url, title=title, text=text)

    def test_non_article_pages_rejected(self):
        body = '기준금리를 동결했다. ' * 40
        cases = {
            'https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1': ('첨부', body),
            'https://acct.fss.or.kr/error_kor.html': ('안내', body),
            'https://www.msn.com/ko-kr/money/x': ('MSN', ''),
            'https://www.fsc.go.kr/no010101': ('전체15389건', body),
            'https://kosis.kr/civilComplaint/qnaDetail.do': ('국가통계포털 질문과 답변을 게시하는 공간입니다', body),
            'https://www.fsc.go.kr/index': ('금융위원회', '\n'.join(['메뉴', '알림마당', '보도자료'] * 20)),
        }
        for url, (title, text) in cases.items():
            self.assertTrue(discovery.reject_reason(self.ev(url, title, text)), url)
        article = self.ev('https://www.newsis.com/view/1', '전월세 급등에 주거비 지원', body)
        self.assertEqual(discovery.reject_reason(article), '')

    def test_generic_title_replaced_by_page_headline(self):
        text = '2027년 주거급여 선정기준 및 최저보장수준\n- 담당부서주거복지지원과\n본문 ' * 3
        self.assertEqual(discovery.headline('주요사이트 바로가기', text), '2027년 주거급여 선정기준 및 최저보장수준')
        para = '구윤철 부총리는 4일 관계기관 합동 시장상황점검회의를 개최하여 국내외 금융·외환시장과 부동산시장 동향을 점검했다. 다음'
        title = discovery.headline('알림마당', para + '\n* 참석자: 금융위원회 위원장\n금융감독원 원장')
        self.assertTrue(title.startswith('구윤철 부총리는'))
        self.assertEqual(discovery.headline('전세 부족, 대학가 월세도 급등', 'x'), '전세 부족, 대학가 월세도 급등')

    def test_euc_kr_page_decoded_from_meta_charset(self):
        raw = '<html><head><meta charset="euc-kr"></head><body>서비스 안내</body></html>'.encode('euc-kr')
        self.assertIn('서비스 안내', discovery.decode(raw, None))
        self.assertIn('서비스 안내', discovery.decode('서비스 안내'.encode('utf-8'), 'utf-8'))


class RealNewsDedupScoringTests(StoreCase):
    """2026-10-08 실수집 회귀: 같은 사건 다매체 보도 병합, 규칙 점수 변별력."""

    def news(self, title, url, day='2026-10-02T08:00:00+09:00', cat='economy'):
        return Topic(topic_id=identifier('topic', url), title=title, category=cat, source_urls=[url], published_at=day)

    def test_same_event_from_several_outlets_is_one_topic(self):
        from app.topics.dedup import duplicate_reason
        a = self.news('9월 소비자물가 2.9% 상승··· 두 달 만에 2%대 복귀', 'https://www.jeonmae.co.kr/1')
        b = self.news("'통신비 착시' 효과에 9월 물가상승률 2%대로 하락…한은 전망", 'https://www.segye.com/2')
        c = self.news('9월 소비자물가 2.9% 상승...석유류 14.8% 치솟아 - 더나은미래', 'https://futurechosun.com/3')
        self.assertTrue(duplicate_reason(b, a))
        self.assertTrue(duplicate_reason(c, a))
        later = self.news('9월 소비자물가 2.9% 상승의 의미', 'https://x.example/4', day='2026-10-09T08:00:00+09:00')
        self.assertEqual(duplicate_reason(later, a), '')          # 며칠 뒤 해설은 후속 보도로 남긴다
        s1 = self.news('2026년 최고 적금금리 비교와 이자 많이 받는 가입 방법 - 투데이즈.kr', 'https://2days.kr/1', cat='finance')
        s2 = self.news('퇴직연금IRP 해지 전 꼭 알아야 할 세금 절약 비법 - 투데이즈.kr', 'https://2days.kr/2', cat='finance')
        self.assertEqual(duplicate_reason(s2, s1), '')            # 매체 이름만 같은 다른 기사

    def test_rule_scores_differ_and_penalize_promo_and_narrow_audience(self):
        from app.topics.scoring import score_topic
        titles = {
            'worker': ('30대 직장인 "독립했더니 월세에 지출 300만원...돈 관리 어떻게"', 'housing'),
            'campus': ('전세 부족, 대학가 월세도 급등', 'housing'),
            'promo': ('대신증권, 연금저축·IRP 순입금 이벤트 진행', 'finance'),
            'macro': ('워시 "물가 꼭 잡겠다"는데…트럼프는 "금리 1% 밑으로 내려라"', 'economy'),
        }
        scores = {k: score_topic(Topic(topic_id=identifier('topic', k), title=t, category=c)).score for k, (t, c) in titles.items()}
        totals = {k: s.total_score for k, s in scores.items()}
        self.assertEqual(len(set(totals.values())), 4)
        self.assertGreater(totals['worker'], totals['campus'])
        self.assertGreater(totals['worker'], totals['promo'])
        self.assertGreater(totals['worker'], totals['macro'])
        self.assertIn('대학가', scores['campus'].reasons['interest'])
        self.assertIn('홍보', scores['promo'].reasons['interest'])
        self.assertNotEqual(scores['worker'].reasons['story'], scores['macro'].reasons['story'])


class OfflineDemoTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_labels_synthetic_outputs_and_preserves_reruns(self):
        from scripts.demo_topic_strategy import run, NOTICE
        from app.topics import scoring
        from app.factory import core
        with tempfile.TemporaryDirectory() as d, \
             patch.object(discovery, 'fetch_evidence', new=AsyncMock(side_effect=AssertionError('no network'))), \
             patch.object(scoring, 'ask_structured', new=AsyncMock(side_effect=AssertionError('no AI'))), \
             patch.object(core, 'make_planned_carousel', new=AsyncMock(side_effect=AssertionError('no rendering'))):
            first = await run(Path(d))
            original = Path(first['dir']) / 'recommendations.json'
            saved = original.read_bytes()
            second = await run(Path(d))
            self.assertNotEqual(first['dir'], second['dir'])
            self.assertEqual(original.read_bytes(), saved)
            for result in (first, second):
                self.assertEqual(result['story_pages'], 8)
                self.assertEqual(result['cost'], 0)
                for filename in ('recommendations.json', 'calendar_1week.json', 'calendar_4weeks.json',
                                 'engine_delivery.json', 'story_plan.json'):
                    data = json.loads((Path(result['dir']) / filename).read_text(encoding='utf-8'))
                    self.assertEqual(data['notice'], NOTICE)


class CalendarFreshnessTests(StoreCase):
    def test_news_not_scheduled_after_it_expires(self):
        import datetime as _dt
        from app.topics.calendar import fresh_on
        t = Topic(topic_id='topic_cpi', title='9월 소비자물가 2.9%', category='economy',
                  published_at='2026-10-02T00:00:00+09:00', freshness='current')
        self.assertTrue(fresh_on(t, _dt.date(2026, 10, 9), 7))
        self.assertFalse(fresh_on(t, _dt.date(2026, 10, 12), 7))
        t.freshness = 'evergreen'
        self.assertTrue(fresh_on(t, _dt.date(2026, 12, 1), 7))
