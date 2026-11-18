"""Adaptive presentation contracts; local mocks only, no browser/network/AI."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.pipeline import hyperframes as hf, hyperframes_layout as layout
from app.pipeline.sources import SourceRegistry
from tests.test_hyperframes import fixture


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.tl = fixture(self.root)
        registry = SourceRegistry(self.root)
        registry.add(kind="image", origin="generated", path=str((self.root/self.tl['scenes'][0]['visual']['path']).resolve()))
        registry.save()
        self.blueprint = {"scenes":[{"start":0,"duration":3,"narration":"원래 음성","emphasis_text":"한국어 제목",
                            "visual_decision":{"resolved_visual_type":"statement_card","asset_path":self.tl['scenes'][0]['visual']['path']}}]}
        self.script = {"scenes":[{"narration":"원래 음성","on_screen_text":"한국어 제목","compare_a":"","compare_b":"","visual_description":""}]}
        self.save()

    def save(self):
        for name,value in [('blueprint',self.blueprint),('script',self.script)]:
            (self.root/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

    def export(self, **options):
        return hf.export_project(self.tl,self.root,self.root/'export',{'layout':'adaptive',**options})

    def test_native_cards_use_matched_saved_text_and_skip_raster_loading(self):
        before = copy.deepcopy(self.tl); self.export()
        markup = (self.root/'export/compositions/shorts.html').read_text('utf-8')
        self.assertIn('id="native-title-0"',markup)
        self.assertNotIn('<img id="visual-0"',markup)
        self.assertIn('>한국어 제목</span>',markup)
        self.assertEqual(self.tl,before)
        self.assertEqual(json.loads((self.root/'export/caption-map.json').read_text('utf-8'))[0]['rows'][0],before['subtitles']['lines'][0]['words'])

    def test_stale_blueprint_does_not_replace_timeline_raster(self):
        self.blueprint['scenes'][0]['start']=1;self.save();self.export()
        data=json.loads((self.root/'export/layout-map.json').read_text('utf-8'))
        self.assertEqual(data['scenes'][0]['kind'],'media')

    def test_unregistered_image_cannot_be_treated_as_generated_card(self):
        (self.root/'sources.json').unlink();self.export()
        data=json.loads((self.root/'export/layout-map.json').read_text('utf-8'))
        self.assertEqual(data['scenes'][0]['kind'],'media')

    def test_no_sidecars_v1_is_compatible_and_keeps_existing_media(self):
        (self.root/'blueprint.json').unlink();(self.root/'script.json').unlink();self.export()
        markup=(self.root/'export/compositions/shorts.html').read_text('utf-8')
        self.assertIn('id="visual-0"',markup)
        self.assertNotIn('native-title-0',markup)

    def test_safe_area_is_configurable_and_impossible_bounds_fail(self):
        for value in [{'left':900},{'top':1200},{'bottom':900},{'right':float('nan')}]:
            with self.subTest(value=value),self.assertRaises(hf.AdapterValidationError):layout.safe_area({'safe_area':value})
        self.export(safe_area={'left':90,'top':270,'right':170,'bottom':420})
        css=(self.root/'export/compositions/shorts.html').read_text('utf-8')
        self.assertIn('left:90px;width:820px',css)
        self.assertEqual(json.loads((self.root/'export/layout-map.json').read_text('utf-8'))['safe_area']['top'],270)

    def test_titles_disabled_never_reappear_from_blueprint(self):
        self.tl['subtitles']['titles_enabled']=False;self.export()
        markup=(self.root/'export/compositions/shorts.html').read_text('utf-8')
        self.assertNotIn('native-title-0',markup);self.assertNotIn('id="title-0"',markup)

    def test_untrusted_sidecar_text_is_escaped(self):
        text='<img src=x onerror=alert(1)> & {{TWEENS}}'
        self.script['scenes'][0]['on_screen_text']=text;self.blueprint['scenes'][0]['emphasis_text']=text
        self.save();self.export()
        markup=(self.root/'export/compositions/shorts.html').read_text('utf-8')
        self.assertNotIn(text,markup);self.assertIn('&lt;img',markup)
        self.assertNotIn(text,markup[markup.rindex('<script>'):])

    def test_chart_steps_require_explicit_saved_count_and_are_not_statistical(self):
        self.script['scenes'][0]['visual_description']='3단 계단형 그래프';self.save();self.export()
        record=json.loads((self.root/'export/layout-map.json').read_text('utf-8'))['scenes'][0]
        self.assertEqual(record['steps'],3);self.assertFalse(record['quantitative_chart'])
        self.assertIn('요금 비율이 아님',(self.root/'export/compositions/shorts.html').read_text('utf-8'))

    def test_missing_numeric_data_does_not_create_count_or_statistic(self):
        self.export();record=json.loads((self.root/'export/layout-map.json').read_text('utf-8'))['scenes'][0]
        self.assertNotIn('steps',record)
        markup=(self.root/'export/compositions/shorts.html').read_text('utf-8')
        self.assertNotIn('class="step"',markup)

    def test_existing_key_number_is_preserved_without_inventing_a_value(self):
        self.script['scenes'][0]['key_number']='40%';self.save();self.export()
        record=json.loads((self.root/'export/layout-map.json').read_text('utf-8'))['scenes'][0]
        self.assertEqual(record['key_number'],'40%')
        self.assertIn('>40%</span>',(self.root/'export/compositions/shorts.html').read_text('utf-8'))

    def test_wide_and_low_resolution_images_keep_entire_subject(self):
        for size in [(1920,1080),(220,277),(400,800)]:
            p=self.root/'source.jpg';Image.new('RGB',size).save(p)
            result=layout.image_geometry(p)
            self.assertEqual(result['mode'],'contain-blur')
            self.assertLessEqual(result['foreground_size'][0]/size[0],2.51)
        Image.new('RGB',(1080,1920)).save(p)
        self.assertEqual(layout.image_geometry(p)['mode'],'cover')

    def test_important_text_fits_without_splitting_or_truncating_words(self):
        text='한국어단어중간잘림을막습니다 다음 문장도 보존해요'
        rows,size=layout.text_rows(text,760)
        self.assertEqual(' '.join(rows).split(),text.split());self.assertLessEqual(len(rows),2)
        self.assertTrue(all(layout.font(size).getlength(x)<=760 for x in rows))

    def test_unapproved_parent_path_is_rejected(self):
        registry=SourceRegistry(self.root);child=registry.by_path((self.root/self.tl['scenes'][0]['visual']['path']).resolve())
        parent=registry.add(kind='image',origin='generated',path=str(self.root.parent/'outside.jpg'))
        parent.credit=self.tl['scenes'][0]['credit'];child.parent_id=parent.id;registry.save()
        with self.assertRaises(hf.AdapterValidationError):self.export()


class MediaTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_only_skips_redundant_premix_and_reuses_exact_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);tl=fixture(root)
            ex=hf.export_project(tl,root,root/'export',{'layout':'adaptive'})
            with patch.object(hf,'run_ffmpeg',new=AsyncMock()) as process:await hf.prepare_media(ex)
            process.assert_not_awaited()
            self.assertEqual(ex['audio']['narration'].read_bytes(),(root/'voice.wav').read_bytes())
            self.assertNotIn('src="assets/mix.wav"',(root/'export/index.html').read_text('utf-8'))

    async def test_bgm_still_uses_existing_mixer_in_adaptive_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);tl=fixture(root);tl['bgm']='voice.wav'
            ex=hf.export_project(tl,root,root/'export',{'layout':'adaptive'})
            with patch.object(hf,'run_ffmpeg',new=AsyncMock()) as process:await hf.prepare_media(ex,True)
            self.assertIn('sidechaincompress',' '.join(process.await_args.args[0]))

    async def test_identical_video_reuses_cache_but_offset_change_invalidates(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);tl=fixture(root);(root/'source.mp4').write_bytes(b'original video')
            tl['scenes'][0]['visual']={'kind':'video','path':'source.mp4','src_start':1,'has_audio':False}
            async def encode(args,cwd=None):Path(args[-1]).write_bytes(b'complete prepared video')
            with patch.object(hf,'TOOLS',root/'tools'),patch.object(hf,'run_ffmpeg',new=AsyncMock(side_effect=encode)) as process,patch.object(hf,'probe_duration',new=AsyncMock(return_value=10)):
                for i in range(3):
                    if i==2:tl['scenes'][0]['visual']['src_start']=2
                    ex=hf.export_project(tl,root,root/f'export{i}',{'layout':'adaptive','cache_media':True})
                    await hf.prepare_media(ex)
                # Two transcodes + one tiny first-frame backdrop per export.
                self.assertEqual(process.await_count,5)
                flags=[json.loads((root/f'export{i}/media-preparation.json').read_text('utf-8'))['videos'][0]['cache_hit'] for i in range(3)]
                self.assertEqual(flags,[False,True,False])
                page=(root/'export0/compositions/shorts.html').read_text('utf-8')
                self.assertLess(page.index('<video '),page.index('<div id="scene-0"'))
