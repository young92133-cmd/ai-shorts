"""Optional renderer contract/security tests. No Node, network, AI, or TTS calls."""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.pipeline import hyperframes as hf, timeline, render, run
from app.pipeline.media import ff_path
from app.factory import __main__ as cli, core
from tests.test_factory import FactoryTestCase, fake_render


def fixture(root: Path) -> dict:
    (root / "scenes").mkdir(exist_ok=True)
    Image.new("RGB", (108, 192), "navy").save(root / "scenes" / "한글 & 사진.jpg")
    (root / "voice.wav").write_bytes(b"fake-audio")
    return {"version": 1, "width": 1080, "height": 1920, "fps": 30, "mode": "slideshow",
            "narration": "voice.wav", "bgm": "", "bgm_volume": 0.1, "source_volume": 0.12, "transition": 0.4,
            "scenes": [{"index": 0, "start": 0, "duration": 3,
                        "title": "한국어 제목", "credit": "사진: 작가 / CC BY",
                        "visual": {"kind": "image", "path": "scenes/한글 & 사진.jpg"}}],
            "subtitles": {"enabled": True, "style": {"font": "Malgun Gothic", "size": 64},
                          "lines": [{"start": 0, "end": 2.9, "text": "한국어 단어를 지켜요.", "words": [
                              {"text": "한국어", "start": 0, "end": 0.6},
                              {"text": "단어를", "start": 0.7, "end": 1.3},
                              {"text": "지켜요.", "start": 1.4, "end": 2.7}]}]}, "comments": []}


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tl = fixture(self.root)

    def test_v1_without_extensions_reuses_original_timings_and_local_assets(self):
        before = copy.deepcopy(self.tl)
        project = self.root / "export"
        exported = hf.export_project(self.tl, self.root, project)
        self.assertEqual(self.tl, before)
        self.assertEqual(exported["total"], 3)
        pages = json.loads((project / "caption-map.json").read_text(encoding="utf-8"))
        got = [w for page in pages for row in page["rows"] for w in row]
        self.assertEqual(got, before["subtitles"]["lines"][0]["words"])
        page = (project / "index.html").read_text(encoding="utf-8") + (project / "compositions/shorts.html").read_text(encoding="utf-8")
        self.assertIn('data-duration="3.000000"', page)
        self.assertIn('font-family: "Noto Sans KR"', page)
        self.assertNotIn('src="http', page)
        self.assertNotIn('file://', page)
        for asset in json.loads((project / "asset-manifest.json").read_text(encoding="utf-8")):
            self.assertTrue((project / asset["asset"]).is_file())

    def test_untrusted_text_is_escaped_and_never_inserted_into_javascript(self):
        payload = '</script><img src=x onerror="alert(1)"> & \' 한글'
        self.tl["scenes"][0].update(title=payload, credit=payload)
        self.tl["subtitles"]["lines"][0]["words"][0]["text"] = payload
        hf.export_project(self.tl, self.root, self.root / "export")
        page = (self.root / "export/compositions/shorts.html").read_text(encoding="utf-8")
        self.assertNotIn(payload, page)
        self.assertIn('&lt;/script&gt;&lt;img', page)
        self.assertIn('&quot;', page)
        self.assertNotIn(payload, page[page.rindex('<script>'):])

    def test_missing_optional_audio_and_captions_are_supported(self):
        self.tl.pop("narration"); self.tl.pop("bgm"); self.tl.pop("subtitles")
        valid = hf.validate(self.tl, self.root)
        self.assertIsNone(valid["audio"]["narration"])
        self.assertIsNone(valid["audio"]["bgm"])
        self.assertEqual(valid["pages"], [])

    def test_windows_separators_and_absolute_paths_with_unicode(self):
        relative = "scenes\\한글 & 사진.jpg"
        self.assertEqual(hf.local_asset(relative, self.root, hf.IMAGE_EXT), (self.root / relative.replace('\\','/')).resolve())
        original = (self.root / "scenes/한글 & 사진.jpg").resolve()
        self.assertEqual(hf.local_asset(str(original), self.root, hf.IMAGE_EXT), original)

    def test_urls_unc_drive_relative_devices_and_missing_paths_are_rejected(self):
        for path in ["https://example.com/a.jpg", "file:///C:/x.jpg", "javascript:evil", "\\\\host\\share\\a.jpg",
                     "//host/share/a.jpg", "\\\\?\\C:\\a.jpg", "C:a.jpg", "missing.jpg", "bad\x00.jpg"]:
            with self.subTest(path=path), self.assertRaises(hf.AdapterValidationError):
                hf.local_asset(path, self.root, hf.IMAGE_EXT)

    def test_parent_traversal_and_unsupported_files_are_rejected(self):
        outside = self.root.parent / (self.root.name + '-outside.jpg')
        outside.write_bytes(b'x'); self.addCleanup(outside.unlink)
        for value in [str(outside), '../' + outside.name, "voice.wav"]:
            with self.subTest(value=value), self.assertRaises(hf.AdapterValidationError):
                hf.local_asset(value, self.root, hf.IMAGE_EXT)

    def test_external_bgm_requires_explicit_trusted_root(self):
        with tempfile.TemporaryDirectory() as d:
            sound = Path(d) / "bed.wav"; sound.write_bytes(b'sound')
            self.tl["bgm"] = str(sound)
            with self.assertRaises(hf.AdapterValidationError): hf.validate(self.tl, self.root)
            result = hf.validate(self.tl, self.root, {"asset_roots": [d]})
            self.assertEqual(result["audio"]["bgm"], sound.resolve())

    def test_invalid_timing_resolution_and_empty_scenes_are_rejected(self):
        cases = [({"fps": 60}), ({"width": 720}), ({"scenes": []}), ({"version": 2})]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(hf.AdapterValidationError):
                hf.validate({**self.tl, **change}, self.root)
        for duration in [0, -1, float('nan'), float('inf'), True]:
            t = copy.deepcopy(self.tl); t["scenes"][0]["duration"] = duration
            with self.subTest(duration=duration), self.assertRaises(hf.AdapterValidationError): hf.validate(t, self.root)

    def test_bad_scene_data_cannot_silently_change_visual_or_timing(self):
        for key, value in [("start", 2), ("effect", "javascript"), ("visual", {"kind": "unknown"})]:
            t = copy.deepcopy(self.tl);t["scenes"][0][key] = value
            with self.subTest(key=key), self.assertRaises(hf.AdapterValidationError): hf.validate(t, self.root)

    def test_long_words_are_preserved_and_pages_have_at_most_two_rows(self):
        text = ['아주긴한국어단어도그대로유지합니다', '그리고', '다음', '문장도', '보존해요.', '계속', '말합니다.']
        words = [{"text":w, "start":i*.6, "end":i*.6+.5} for i,w in enumerate(text)]
        pages = hf.caption_pages([{"start":0,"end":5,"words":words}], 5)
        self.assertEqual([w for p in pages for row in p['rows'] for w in row],words)
        self.assertTrue(all(len(p['rows'])<=2 for p in pages))
        self.assertTrue(all(a['end']<=b['start'] for a,b in zip(pages,pages[1:])))

    def test_invalid_word_order_is_rejected(self):
        self.tl["subtitles"]["lines"][0]["words"][1]["start"] = .1
        with self.assertRaises(hf.AdapterValidationError): hf.validate(self.tl,self.root)

    def test_disabled_subtitles_and_titles_stay_disabled(self):
        self.tl['subtitles'].update(enabled=False,titles_enabled=False)
        hf.export_project(self.tl,self.root,self.root/'export')
        page=(self.root/'export/compositions/shorts.html').read_text(encoding='utf-8')
        self.assertNotIn('id="caption-0"',page);self.assertNotIn('id="title-0"',page)

    def test_existing_export_folder_is_not_overwritten(self):
        target=self.root/'export';target.mkdir();(target/'mine.txt').write_text('mine')
        with self.assertRaises(FileExistsError):hf.export_project(self.tl,self.root,target)
        self.assertEqual((target/'mine.txt').read_text(),'mine')

    def test_template_marker_in_caption_is_preserved_as_text(self):
        self.tl['subtitles']['lines'][0]['words'][0]['text']='{{TWEENS}}'
        hf.export_project(self.tl,self.root,self.root/'export')
        page=(self.root/'export/compositions/shorts.html').read_text(encoding='utf-8')
        self.assertIn('>{{TWEENS}}</span>',page)

    def test_supplied_missing_bgm_and_sfx_are_errors_not_silent_drops(self):
        self.tl['bgm']='missing.wav'
        with self.assertRaises(hf.AdapterValidationError):hf.validate(self.tl,self.root)
        self.tl['bgm']='';self.tl['sfx']=[{'path':'missing.wav','start':1}]
        with self.assertRaises(hf.AdapterValidationError):hf.validate(self.tl,self.root)

    def test_os_lock_blocks_other_render_and_releases_after_error(self):
        with self.assertRaisesRegex(RuntimeError,'test interruption'):
            with hf.render_slot(self.root/'tools'):
                with self.assertRaises(hf.HyperframesError):
                    with hf.render_slot(self.root/'tools'):pass
                raise RuntimeError('test interruption')
        with hf.render_slot(self.root/'tools'):pass


class DispatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.tl=fixture(self.root);self.out=self.root/'new.mp4'

    async def encode(self,tl,job,out,*args):
        out.write_bytes(b'fake MP4');return out

    async def test_old_timeline_defaults_to_only_ffmpeg(self):
        with patch.object(timeline,'_render_ffmpeg',new=AsyncMock(side_effect=self.encode)) as ff, \
             patch.object(hf,'render_hyperframes',new=AsyncMock()) as other:
            await timeline.render_timeline(self.tl,self.root,self.out)
        ff.assert_awaited_once();other.assert_not_awaited()
        self.assertEqual(timeline.render_record(self.out)['actual_renderer'],'ffmpeg')

    async def test_selected_hyperframes_does_not_call_ffmpeg(self):
        self.tl['render']={'renderer':'hyperframes'}
        async def encode(tl,job,out,project,options):return await self.encode(tl,job,out)
        with patch.object(timeline,'_render_ffmpeg',new=AsyncMock()) as ff, \
             patch.object(hf,'render_hyperframes',new=AsyncMock(side_effect=encode)):
            await timeline.render_timeline(self.tl,self.root,self.out)
        ff.assert_not_awaited();self.assertEqual(timeline.render_record(self.out)['actual_renderer'],'hyperframes')

    async def test_failure_has_log_and_no_automatic_fallback(self):
        self.tl['render']={'renderer':'hyperframes'}
        with patch.object(timeline,'_render_ffmpeg',new=AsyncMock()) as ff, \
             patch.object(hf,'render_hyperframes',new=AsyncMock(side_effect=hf.HyperframesError('broken browser'))):
            with self.assertRaises(hf.HyperframesError):await timeline.render_timeline(self.tl,self.root,self.out)
        ff.assert_not_awaited();self.assertFalse(self.out.exists())
        record=json.loads(next((self.root/'renders').glob('*/render-result.json')).read_text())
        self.assertEqual(record['status'],'failed');self.assertIn('broken browser',record['error'])

    async def test_explicit_fallback_records_actual_renderer(self):
        self.tl['render']={'renderer':'hyperframes','fallback':'ffmpeg'}
        with patch.object(timeline,'_render_ffmpeg',new=AsyncMock(side_effect=self.encode)), \
             patch.object(hf,'render_hyperframes',new=AsyncMock(side_effect=hf.HyperframesError('failure'))):
            await timeline.render_timeline(self.tl,self.root,self.out)
        record=timeline.render_record(self.out)
        self.assertEqual(record['requested_renderer'],'hyperframes');self.assertEqual(record['actual_renderer'],'ffmpeg')
        self.assertTrue(record['fallback_used']);self.assertEqual(len(record['errors']),1)

    async def test_security_validation_error_never_falls_back(self):
        self.tl['render']={'renderer':'hyperframes','fallback':'ffmpeg'}
        with patch.object(timeline,'_render_ffmpeg',new=AsyncMock()) as ff, \
             patch.object(hf,'render_hyperframes',new=AsyncMock(side_effect=hf.AdapterValidationError('traversal'))):
            with self.assertRaises(hf.AdapterValidationError):await timeline.render_timeline(self.tl,self.root,self.out)
        ff.assert_not_awaited()

    async def test_existing_user_video_and_sidecar_are_never_overwritten(self):
        self.out.write_bytes(b'user video')
        with self.assertRaises(FileExistsError):await timeline.render_timeline(self.tl,self.root,self.out)
        self.assertEqual(self.out.read_bytes(),b'user video')

    async def test_publish_race_preserves_the_other_writers_output(self):
        async def racing_encode(tl,job,out,*args):
            self.out.write_bytes(b'another user');return await self.encode(tl,job,out)
        with patch.object(timeline,'_render_ffmpeg',new=AsyncMock(side_effect=racing_encode)):
            with self.assertRaises(FileExistsError):await timeline.render_timeline(self.tl,self.root,self.out)
        self.assertEqual(self.out.read_bytes(),b'another user')

    async def test_invalid_renderer_does_not_create_output(self):
        with self.assertRaises(ValueError):await timeline.render_timeline(self.tl,self.root,self.out,options={'renderer':'bad'})
        self.assertFalse(self.out.exists())

    async def test_legacy_ffmpeg_graph_and_ass_are_unchanged_by_dispatch(self):
        commands=[]
        async def process(args,cwd=None):
            commands.append(args);Path(args[-1]).write_bytes(b'mp4')
        with patch.object(render,'run_ffmpeg',new=process):
            old=self.root/'old.mp4'
            await timeline._render_ffmpeg(self.tl,self.root,old)
            old_ass=(self.root/'subs.ass').read_bytes()
            await timeline.render_timeline(self.tl,self.root,self.out)
        self.assertEqual(old_ass,next((self.root/'renders').glob('*/subs.ass')).read_bytes())
        a,b=commands
        def normalise(args):
            return ['ASS' if s.startswith('ass=') else s for s in args[:-1]]
        a_filter=a[a.index('-filter_complex')+1];b_filter=b[b.index('-filter_complex')+1]
        b_ass=next((self.root/'renders').glob('*/subs.ass'))
        self.assertEqual(a_filter.replace(ff_path(self.root/'subs.ass'),'<ASS>'),b_filter.replace(ff_path(b_ass),'<ASS>'))
        # Every other input/encoder/audio/transition argument is exactly the legacy value.
        aa=a[:-1];bb=b[:-1];aa[aa.index('-filter_complex')+1]='<FILTER>';bb[bb.index('-filter_complex')+1]='<FILTER>'
        self.assertEqual(aa,bb)

    async def test_rerender_preserves_old_video_thumb_and_timeline(self):
        timeline.save(self.root,self.tl);(self.root/'final.mp4').write_bytes(b'old');(self.root/'thumb.jpg').write_bytes(b'old thumb')
        original=(self.root/'timeline.json').read_bytes()
        async def thumb(video,out,at):out.write_bytes(b'new thumb')
        with patch.object(run,'require_ffmpeg'),patch.object(run,'guard_timeline'),patch.object(run,'make_thumbnail',new=thumb), \
             patch.object(timeline,'_render_ffmpeg',new=AsyncMock(side_effect=self.encode)):
            result=await run.rerender(self.root,{'paths':{'assets':str(self.root)}})
        self.assertNotEqual(result['video'],str(self.root/'final.mp4'))
        self.assertEqual((self.root/'final.mp4').read_bytes(),b'old');self.assertEqual((self.root/'thumb.jpg').read_bytes(),b'old thumb')
        self.assertEqual((self.root/'timeline.json').read_bytes(),original)

    async def test_hyperframes_audio_handles_no_bgm_no_narration(self):
        self.tl['narration']='';ex=hf.export_project(self.tl,self.root,self.root/'export')
        process=AsyncMock()
        with patch.object(hf,'run_ffmpeg',new=process):await hf.prepare_media(ex)
        args=process.await_args.args[0]
        self.assertIn('anullsrc=r=44100:cl=stereo',args)
        self.assertNotIn('sidechaincompress',' '.join(args))

    async def test_ducking_is_only_in_hyperframes_pre_mix(self):
        self.tl['bgm']='voice.wav';ex=hf.export_project(self.tl,self.root,self.root/'export')
        process=AsyncMock()
        with patch.object(hf,'run_ffmpeg',new=process):await hf.prepare_media(ex,duck_bgm=True)
        args=process.await_args.args[0]
        self.assertIn('sidechaincompress',' '.join(args));self.assertEqual(self.tl['bgm_volume'],.1)

    async def test_video_offset_play_limit_and_freeze_reuse_local_source(self):
        video=self.root/'한글 video.mp4';video.write_bytes(b'video')
        self.tl['scenes'][0]['visual']={'kind':'video','path':str(video),'src_start':1.25,'play':.5,'has_audio':False}
        ex=hf.export_project(self.tl,self.root,self.root/'export')
        process=AsyncMock()
        with patch.object(hf,'run_ffmpeg',new=process),patch.object(hf,'probe_duration',new=AsyncMock(return_value=5)):
            await hf.prepare_media(ex)
        args=process.await_args_list[0].args[0]
        self.assertEqual(args[args.index('-ss')+1],'1.250000')
        self.assertIn('trim=duration=0.500000',' '.join(args))
        self.assertIn('tpad=stop_mode=clone',' '.join(args))
        page=(self.root/'export/compositions/shorts.html').read_text(encoding='utf-8')
        self.assertIn('muted playsinline',page)
        self.assertIn('data-hf-media-start-basis="local"',page)

    async def test_sfx_is_mixed_at_its_original_offset_and_volume(self):
        self.tl['sfx']=[{'path':'voice.wav','start':1.25,'volume':.2}]
        ex=hf.export_project(self.tl,self.root,self.root/'export')
        process=AsyncMock()
        with patch.object(hf,'run_ffmpeg',new=process):await hf.prepare_media(ex)
        args=process.await_args.args[0]
        self.assertIn('volume=0.2,adelay=1250:all=1',' '.join(args))

    async def test_cancel_waits_for_command_thread_cleanup_before_returning(self):
        started=threading.Event();cleaned=threading.Event()
        def execute(command,cwd,env,log,timeout,cancelled):
            started.set()
            if not cancelled.wait(2):raise RuntimeError('Cancellation was not forwarded')
            cleaned.set();raise hf.HyperframesError('cancelled')
        with patch.object(hf,'_execute',new=execute):
            task=asyncio.create_task(hf._execute_async([],self.root,{},self.root/'log',30))
            for _ in range(200):
                if started.is_set():break
                await asyncio.sleep(.01)
            self.assertTrue(started.is_set());task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(cleaned.is_set())


class FactorySelectionTests(FactoryTestCase):
    async def test_make_selection_is_saved_and_passed_to_existing_pipeline(self):
        fake=AsyncMock(side_effect=fake_render)
        with patch.object(run.timelinemod,'render_timeline',new=fake):
            result=await core.make(topic='고양이',renderer='hyperframes',log=lambda *_:None)
        self.assertEqual(result['status'],'render_complete')
        self.assertEqual(fake.await_args.args[0]['render']['renderer'],'hyperframes')
        state=json.loads((Path(result['project_dir'])/'project_state.json').read_text(encoding='utf-8'))
        self.assertEqual(state['request']['renderer'],'hyperframes')

    async def test_rerender_selects_renderer_without_research_or_tts(self):
        first=await core.make(topic='고양이',log=lambda *_:None)
        fake=AsyncMock(side_effect=fake_render)
        with patch.object(run.timelinemod,'render_timeline',new=fake):
            result=await core.rerender(first['project_id'],renderer='hyperframes',log=lambda *_:None)
        self.assertTrue(result['rerendered']);self.assertNotEqual(first['final_video'],result['final_video'])
        self.assertEqual(fake.await_args.args[0]['render']['renderer'],'hyperframes')
        self.research.assert_awaited_once();self.write_script.assert_awaited_once()

    def test_cli_choices_and_default(self):
        parser=cli._parser()
        self.assertIsNone(parser.parse_args(['make','--topic','x']).renderer)
        for command in [['make','--topic','x'],['rerender','abc']]:
            parsed=parser.parse_args(command+['--renderer','hyperframes','--renderer-fallback','ffmpeg'])
            self.assertEqual((parsed.renderer,parsed.renderer_fallback),('hyperframes','ffmpeg'))
