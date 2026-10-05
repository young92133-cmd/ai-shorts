"""Integration contracts and offline production boundaries for the complete inventory."""
import copy
import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.factory import benchmark as factory, core, __main__ as cli
from app.pipeline import benchmark, benchmark_registry as registry, timeline, render
from app.pipeline.benchmark_models import BenchmarkInput, BenchmarkPlan, BenchmarkProfile
from app.pipeline.benchmark_structured import common_view

NEW = [p['id'] for p in benchmark.profiles() if p['adapter'] != 'legacy_clip']


def raw(name):
    return json.loads((benchmark.PROFILE_ROOT / 'examples' / f'{name}.input.json').read_text(encoding='utf-8'))


def select(name, data=None, seconds=None):
    return benchmark.select_pair(BenchmarkInput.model_validate(data or raw(name)), benchmark.load_profile(name),
                                 {'owned': 60} if name in ('ranked_moments', 'physics_comparison_simulation') else {},
                                 seconds=seconds)


class RegistryTests(unittest.TestCase):
    def test_loads_entire_source_inventory_and_bidirectional_links(self):
        result = registry.inventory()
        self.assertEqual(result['source_count'], 6)
        self.assertEqual(result['profile_count'], 8)
        self.assertEqual({s['id'] for s in result['sources']},
                         {'doltori', 'zzal_ing', 'lesgi', 'bks_simulation', 'architecture_mania', 'factory_reference'})

    def test_reference_catalog_is_distinguished_from_observed_footage(self):
        src = registry.load_source('factory_reference')
        findings = {f.name: f for f in src.findings}
        self.assertEqual(len(findings), 13)  # 12 content styles plus tool functions
        self.assertEqual(findings['요즘PDst'].analysis_depth, 'catalog_only')
        self.assertEqual(findings['요즘PDst'].derived_profiles, [])
        self.assertEqual(findings['정치채널st'].analysis_depth, 'direct_observation')

    def test_broken_profile_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'sources').mkdir()
            source = registry.load_source('doltori').model_dump(mode='json')
            (root / 'sources' / 'doltori.json').write_text(json.dumps(source), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'broken source/profile'):
                registry.inventory(root)

    def test_source_filename_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'sources').mkdir()
            (root / 'sources' / 'wrong.json').write_text(registry.load_source('doltori').model_dump_json(), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'filename'):
                registry.load_source('wrong', root)

    def test_source_schema_and_optional_radar_metadata(self):
        data = registry.load_source('doltori').model_dump(mode='json')
        data.update(source_country='KR', source_language='ko', target_market='KR', trend_date='2026-10-02',
                    trend_signal='historical_analysis', localization_notes='manual')
        registry.BenchmarkSource.model_validate(data)
        data['logo'] = 'not allowed'
        with self.assertRaises(ValidationError):
            registry.BenchmarkSource.model_validate(data)

    def test_unknown_profile_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, 'unknown benchmark profile'):
            benchmark.load_profile('unknown')

    def test_duplicate_profile_files_are_rejected(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'profiles').mkdir()
            text = yaml.safe_dump(benchmark.load_profile('kpop_observation_clip').model_dump())
            (root / 'kpop_observation_clip.yaml').write_text(text, encoding='utf-8')
            (root / 'profiles' / 'kpop_observation_clip.yaml').write_text(text, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                benchmark.profiles(root)


class ContractTests(unittest.TestCase):
    def test_every_new_profile_selects_and_roundtrips_snapshot(self):
        for name in NEW:
            with self.subTest(profile=name):
                plan = select(name)
                loaded = BenchmarkPlan.model_validate_json(plan.model_dump_json())
                self.assertEqual(loaded.profile_id, name)
                self.assertEqual(common_view(loaded)['profile_name'], name)

    def test_shared_output_fields_for_all_profiles(self):
        from tests.test_benchmark import selected
        for plan in [selected()] + [select(name) for name in NEW]:
            output = common_view(plan)
            for key in ('profile_name', 'content_type', 'reason_to_watch', 'viewer_question', 'hook', 'claim',
                        'evidence_type', 'evidence', 'payoff', 'ending_question', 'confidence', 'reasoning_summary'):
                self.assertTrue(output[key], (plan.profile_id, key))

    def test_pre_integration_saved_plan_still_loads(self):
        path = benchmark.PROFILE_ROOT / 'examples' / 'kpop_comparison.plan.json'
        plan = BenchmarkPlan.model_validate_json(path.read_text(encoding='utf-8'))
        self.assertEqual(plan.profile_snapshot.adapter, 'legacy_clip')
        self.assertEqual(plan.target_seconds, 30)

    def test_generic_required_fields_for_every_new_profile(self):
        for name in NEW:
            for field in ('viewer_question', 'payoff', 'claim', 'hook', 'reason_to_watch', 'evidence'):
                data = raw(name); del data['observations'][0][field]
                with self.subTest(profile=name, field=field), self.assertRaises(ValidationError):
                    BenchmarkInput.model_validate(data)

    def test_unknown_evidence_type_is_schema_error(self):
        data = raw('curiosity_update_story'); data['observations'][0]['evidence'][0]['evidence_type'] = 'made_up'
        with self.assertRaises(ValidationError):
            BenchmarkInput.model_validate(data)

    def test_valid_evidence_type_disallowed_by_profile_is_rejected(self):
        data = raw('curiosity_update_story'); data['observations'][0]['evidence'][0]['evidence_type'] = 'quote'
        with self.assertRaisesRegex(ValueError, 'invalid evidence'):
            select('curiosity_update_story', data)

    def test_profile_required_roles_cannot_be_omitted_or_renamed(self):
        for name in NEW:
            data = raw(name); data['observations'][0]['evidence'][0]['role'] = 'wrong'
            with self.subTest(profile=name), self.assertRaisesRegex(ValueError, 'evidence roles'):
                select(name, data)

    def test_unreferenced_fact_evidence_is_rejected(self):
        data = raw('curiosity_update_story'); data['observations'][0]['evidence'][0]['source_id'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'unknown evidence source'):
            select('curiosity_update_story', data)

    def test_fact_input_does_not_require_timecodes_and_cannot_be_downloaded(self):
        plan = select('curiosity_update_story')
        self.assertTrue(all(e.clip is None for e in plan.selection.evidence))
        data = raw('curiosity_update_story'); data['sources'][0] = {'id': 'notes', 'path': 'remote.mp4'}
        with self.assertRaisesRegex(ValueError, 'annotation reference'):
            select('curiosity_update_story', data)

    def test_video_evidence_requires_clip_and_matching_source(self):
        data = raw('ranked_moments'); del data['observations'][0]['evidence'][0]['clip']
        with self.assertRaises(ValidationError):
            BenchmarkInput.model_validate(data)
        data = raw('ranked_moments'); data['observations'][0]['evidence'][0]['clip']['source_id'] = 'other'
        with self.assertRaises(ValidationError):
            BenchmarkInput.model_validate(data)

    def test_physics_requires_single_variable_fixed_controls_and_distinct_conditions(self):
        for change in ('missing', 'wrong_variable', 'empty_controls', 'fixed_variable', 'same_conditions'):
            data = raw('physics_comparison_simulation'); c = data['observations'][0]
            if change == 'missing': del c['experiment']
            elif change == 'wrong_variable': c['experiment']['variable'] = 'height'
            elif change == 'empty_controls': c['experiment']['controls'] = {}
            elif change == 'fixed_variable': c['experiment']['controls']['softness'] = 'fixed'
            else: c['evidence'][1]['condition_value'] = c['evidence'][0]['condition_value']
            with self.subTest(change=change), self.assertRaises((ValueError, ValidationError)):
                select('physics_comparison_simulation', data)

    def test_ranked_examples_must_count_down_to_one(self):
        for ranks in ([1,2,3,4,5], [5,4,3,2,2], [6,5,4,3,2]):
            data = raw('ranked_moments')
            for e, rank in zip(data['observations'][0]['evidence'], ranks): e['rank'] = rank
            with self.assertRaisesRegex(ValueError, 'ranks'):
                select('ranked_moments', data)

    def test_low_confidence_in_nested_clip_caps_annotated_result(self):
        data = raw('ranked_moments'); data['observations'][0]['evidence'][0]['clip']['confidence'] = .1
        with self.assertRaisesRegex(ValueError, 'below profile'):
            select('ranked_moments', data)

    def test_overlapping_clips_and_missing_duration_rejected(self):
        data = raw('ranked_moments'); data['observations'][0]['evidence'][1]['clip'].update(start=1,end=3)
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            select('ranked_moments', data)
        data = raw('ranked_moments'); data['observations'][0]['evidence'][0]['clip']['end'] = 100
        with self.assertRaisesRegex(ValueError, 'duration'):
            select('ranked_moments', data)

    def test_complete_evidence_must_fit_duration_and_no_invalid_profile_roles(self):
        data = raw('physics_comparison_simulation'); data['observations'][0]['evidence'][0]['clip']['end'] = 25
        data['observations'][0]['evidence'][1]['clip'].update(start=30,end=50)
        with self.assertRaisesRegex(ValueError, 'does not fit'):
            select('physics_comparison_simulation', data)
        p = benchmark.load_profile('curiosity_update_story').model_dump(); p['evidence_roles'] = ['absent']
        with self.assertRaises(ValidationError): BenchmarkProfile.model_validate(p)

    def test_profile_length_range_and_variation_selection(self):
        self.assertEqual(select('mechanism_explainer', seconds=90).target_seconds, 90)
        with self.assertRaises(ValueError): select('physics_comparison_simulation', seconds=90)
        with self.assertRaises(ValueError): select('curiosity_update_story', seconds=True)
        for name in NEW:
            for variation in benchmark.load_profile(name).observation_types:
                data = raw(name); data['observations'][0]['observation_type'] = variation
                if 'experiment' in data['observations'][0]: data['observations'][0]['experiment']['variable'] = variation
                self.assertEqual(select(name, data).selection.observation_type, variation)


class ProductionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        (self.root / 'my_experiment.mp4').write_bytes(b'owned test footage')
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(core, 'output_root', return_value=self.root / 'output'))
        self.stack.enter_context(patch.object(factory, 'require_ffmpeg'))
        self.stack.enter_context(patch.object(factory, 'has_audio', new=AsyncMock(return_value=True)))
        self.stack.enter_context(patch.object(factory, 'probe_video', new=AsyncMock(side_effect=lambda path:
            {'streams':[{'width':1080,'height':1920}], 'format':{'duration':'30' if str(path).endswith('.tmp.mp4') else '60'}})))
        self.ai = self.stack.enter_context(patch('app.pipeline.llm.ask_structured', new=AsyncMock(side_effect=AssertionError('no AI'))))
        self.tts = self.stack.enter_context(patch('app.pipeline.run.get_tts', side_effect=AssertionError('no TTS')))
        self.download = self.stack.enter_context(patch('app.pipeline.youtube.download_media', new=AsyncMock(side_effect=AssertionError('no download'))))

    def tearDown(self):
        self.stack.close(); self.temp.cleanup()

    async def ready(self, name):
        p = self.root / f'{name}.json'; p.write_text(json.dumps(raw(name)), encoding='utf-8')
        return await factory.plan(str(p), profile_id=name, confirm_rights=True, note='직접 작성한 근거/권리 확인', log=lambda _:None)

    async def test_every_profile_reaches_shared_renderer_and_keeps_v1_state_isolated(self):
        async def render(tl, job, output):
            self.assertEqual(timeline.total_duration(tl), 30)
            output.write_bytes(b'mock mp4'); (job/'subs.ass').write_text('mock subtitles',encoding='utf-8')
        with patch.object(timeline, 'render_timeline', new=AsyncMock(side_effect=render)) as rendering:
            for name in NEW:
                with self.subTest(profile=name):
                    out = await self.ready(name)
                    self.assertEqual(out['status'], 'benchmark_ready')
                    done = await factory.render(out['project_id'], log=lambda _:None)
                    self.assertEqual(done['status'], 'render_complete', done.get('error'))
                    self.assertEqual(done['benchmark']['profile_name'], name)
                    self.assertEqual(done['ai_calls'], [])
            self.assertEqual(rendering.await_count, len(NEW))
        self.assertEqual(core._projects(), [])
        self.ai.assert_not_called(); self.tts.assert_not_called(); self.download.assert_not_called()

    async def test_saved_snapshot_can_render_after_registry_profile_changes(self):
        out = await self.ready('curiosity_update_story')
        with patch.object(engine := benchmark, 'load_profile', side_effect=AssertionError('must use snapshot')), \
                patch.object(timeline, 'render_timeline', new=AsyncMock(side_effect=RuntimeError('renderer sentinel'))):
            done = await factory.render(out['project_id'], log=lambda _:None)
        self.assertEqual(done['failed_at'], 'render')
        self.assertIn('renderer sentinel', done['error'])

    async def test_mutated_required_evidence_in_saved_plan_is_blocked_before_render(self):
        out = await self.ready('curiosity_update_story'); path = Path(out['plan_path'])
        data = json.loads(path.read_text(encoding='utf-8')); data['selection']['evidence'][0]['role']='wrong'
        path.write_text(json.dumps(data),encoding='utf-8')
        with patch.object(timeline,'render_timeline',new=AsyncMock()) as renderer:
            done = await factory.render(out['project_id'],log=lambda _:None)
        self.assertEqual(done['failed_at'],'validation'); renderer.assert_not_called()

    async def test_ranked_timeline_preserves_five_complete_clips_in_order(self):
        out = await self.ready('ranked_moments');job=Path(out['project_dir'])
        plan=benchmark.load_plan(job)
        tl=benchmark.build_timeline(job,plan,{'owned':{'path':str(job/'uploads'/'owned.mp4'),'has_audio':True}})
        video=[s for s in tl['scenes'] if s['visual']['kind']=='video']
        self.assertEqual([s['visual']['src_start'] for s in video],[0,3,6,9,12])
        self.assertTrue(all(s['duration']==2 for s in video))
        self.assertEqual([s['evidence_id'] for s in video],[f'proof_{i}' for i in range(1,6)])
        self.assertEqual([l['text'].split('위')[0] for l in tl['subtitles']['lines']],['5','4','3','2','1'])

    async def test_cli_selects_each_profile_and_reports_unknown_as_request_error(self):
        with patch.object(factory, 'plan', new=AsyncMock(return_value={'status':'benchmark_ready'})) as planning:
            for name in NEW:
                args=cli._parser().parse_args(['benchmark','plan','--input','notes.json','--profile',name,'--observation-type',next(iter(benchmark.load_profile(name).observation_types))])
                await cli._dispatch(args)
                self.assertEqual(planning.await_args.kwargs['profile_id'],name)
    def test_cli_sources_stdout_is_json(self):
        out=io.StringIO()
        with redirect_stdout(out),redirect_stderr(io.StringIO()):
            code=cli.main(['benchmark','sources'])
        self.assertEqual(code,0);self.assertEqual(json.loads(out.getvalue())['source_count'],6)

    async def test_unknown_selection_before_any_media_io(self):
        with self.assertRaises(core.FactoryError) as error:
            await factory.plan('missing.json',profile_id='unknown',confirm_rights=True,note='confirmed')
        self.assertEqual(error.exception.code,'invalid')

    async def test_generated_cards_and_mixed_video_use_existing_ffmpeg_graph(self):
        for name in ('curiosity_update_story', 'ranked_moments'):
            out = await self.ready(name); job = Path(out['project_dir'])
            plan = benchmark.load_plan(job)
            tl = benchmark.build_timeline(job, plan, {'owned': {'path': str(job/'uploads'/'owned.mp4'), 'has_audio': True}})
            with patch.object(render, 'run_ffmpeg', new=AsyncMock()) as ffmpeg:
                await timeline.render_timeline(tl, job, job/'test.mp4')
            args = ffmpeg.await_args.args[0]; graph = args[args.index('-filter_complex')+1]
            self.assertIn('anullsrc', graph)
            self.assertIn('[acat]anull[aout]', graph)
            self.assertNotIn('[narr]', graph)
            if name == 'ranked_moments':
                self.assertIn('trim=0.000:2.000,', graph)
                self.assertNotIn('trim=0.000:3.000,', graph)
            self.assertTrue((job/'subs.ass').is_file())

    async def test_failed_card_rerender_preserves_completed_video(self):
        out = await self.ready('curiosity_update_story'); job = Path(out['project_dir'])
        (job/'final.mp4').write_bytes(b'previous final')
        with patch.object(timeline,'render_timeline',new=AsyncMock(side_effect=RuntimeError('sentinel'))):
            done = await factory.render(out['project_id'], log=lambda _:None)
        self.assertEqual(done['failed_at'],'render')
        self.assertEqual((job/'final.mp4').read_bytes(), b'previous final')


if __name__=='__main__': unittest.main()
