"""Isolated local projects with fake media/AI; never create a production video."""
from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.benchmarks import engine
from app.factory import __main__ as cli, benchmark, core, state as st
from app.pipeline import timeline
from tests.test_benchmark_engine import ROOT, material, plan, plan_data


class FactoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.video = self.root / "input.mp4"
        self.video.write_bytes(b"local test video")
        self.plan_path = self.root / "plan.json"
        self.plan_path.write_text(json.dumps(plan_data(), ensure_ascii=False), encoding="utf-8")
        self.stack = ExitStack()
        self.analyze = AsyncMock(return_value=plan())
        self.observe = AsyncMock(return_value=material())
        self.render = AsyncMock(side_effect=self.fake_render)
        self.probe = AsyncMock(side_effect=self.fake_probe)
        for p in (patch.object(core, "output_root", return_value=self.root / "output"),
                  patch.object(core, "probe_video", new=self.probe),
                  patch.object(benchmark, "require_ffmpeg"), patch.object(benchmark, "probe_video", new=self.probe),
                  patch.object(benchmark, "has_audio", new=AsyncMock(return_value=True)),
                  patch.object(benchmark, "make_thumbnail", new=AsyncMock()),
                  patch.object(timeline, "render_timeline", new=self.render),
                  patch.object(engine, "analyze", new=self.analyze), patch.object(engine, "observe_video", new=self.observe)):
            self.stack.enter_context(p)
        self.rights = core._own_rights("licensed_upload", "test: licensed footage including audio", True)

    def tearDown(self):
        self.stack.close()
        self.tmp.cleanup()

    async def fake_probe(self, path):
        duration = 80 if Path(path) == self.video else timeline.total_duration(timeline.load(Path(path).parent))
        return {"streams": [{"width": 1080, "height": 1920}], "format": {"duration": str(duration)}}

    async def fake_render(self, tl, job, out, fonts):
        self.assertFalse(tl.get("narration"))
        Path(out).write_bytes(b"rendered test video")
        return Path(out)

    async def make(self, **extra):
        return await core.make(video=[str(self.video)], benchmark="kpop_observation_clip", asset_rights=self.rights,
                               benchmark_plan=str(self.plan_path), log=lambda _: None, **extra)

    async def test_supplied_plan_renders_with_no_ai_or_tts(self):
        out = await self.make()
        self.assertEqual(out["status"], "render_complete")
        self.assertEqual(out["resolution"], "1080x1920")
        self.assertEqual(out["duration"], 30)
        self.assertEqual(out["tts"], "none")
        self.assertEqual(out["analysis_method"], "supplied_plan")
        self.analyze.assert_not_awaited()
        self.observe.assert_not_awaited()
        job = Path(out["project_dir"])
        self.assertFalse((job / "narration.mp3").exists())
        self.assertNotIn("tts_complete", [s["status"] for s in st.load(job)["history"]])
        self.assertTrue((job / "job.json").exists())
        self.assertTrue((job / "sources.json").exists())

    async def test_review_edit_and_resume_reuse_saved_evidence(self):
        out = await self.make(review=True)
        self.assertEqual(out["status"], "waiting_for_script_approval")
        self.render.assert_not_awaited()
        core.edit_scene(out["project_id"], 1, narration="직접 확인할 시선 방향", emphasis="시선 비교")
        done = await core.resume(out["project_id"], log=lambda _: None)
        self.assertEqual(done["status"], "render_complete")
        tl = timeline.load(Path(done["project_dir"]))
        self.assertEqual(tl["subtitles"]["lines"][0]["text"], "직접 확인할 시선 방향")
        self.assertEqual(tl["scenes"][0]["title"], "시선 비교")
        self.analyze.assert_not_awaited()
        self.observe.assert_not_awaited()

    async def test_profile_snapshot_survives_rerender_and_inspection(self):
        out = await self.make()
        with patch.object(benchmark, "load_profile", side_effect=AssertionError("must use snapshot")):
            done = await core.rerender(out["project_id"], log=lambda _: None)
        self.assertTrue(done["rerendered"])
        view = core.inspect(out["project_id"], "benchmark")
        self.assertEqual(view["benchmark"]["claim"], plan().claim)
        self.assertEqual(view["benchmark_profile"]["profile_name"], "kpop_observation_clip")
        self.analyze.assert_not_awaited()

    async def test_failed_rerender_preserves_previous_final(self):
        out = await self.make()
        final = Path(out["final_video"])
        before = final.read_bytes()
        self.render.side_effect = RuntimeError("test render failure")
        done = await core.rerender(out["project_id"], log=lambda _: None)
        self.assertEqual(done["status"], "failed")
        self.assertFalse(done["rerendered"])
        self.assertEqual(final.read_bytes(), before)

    async def test_wrong_output_resolution_preserves_previous_final(self):
        out = await self.make()
        before = Path(out["final_video"]).read_bytes()
        self.probe.side_effect = None
        self.probe.return_value = {"streams": [{"width": 720, "height": 1280}], "format": {"duration": "30"}}
        done = await core.rerender(out["project_id"], log=lambda _: None)
        self.assertEqual(done["status"], "failed")
        self.assertEqual(Path(out["final_video"]).read_bytes(), before)

    async def test_source_changes_and_timeline_escape_are_rejected_before_render(self):
        for mutation in ("source", "timeline"):
            with self.subTest(mutation=mutation):
                out = await self.make(review=True)
                job = Path(out["project_dir"])
                if mutation == "source":
                    (job / "uploads/video_1.mp4").write_bytes(b"changed")
                else:
                    tl = timeline.load(job)
                    tl["scenes"][0]["visual"]["src_start"] = 0
                    timeline.save(job, tl)
                self.render.reset_mock()
                done = await core.resume(out["project_id"], log=lambda _: None)
                self.assertEqual(done["status"], "failed")
                self.render.assert_not_awaited()

    async def test_replacing_evidence_with_unrelated_visual_is_blocked(self):
        out = await self.make(review=True)
        with self.assertRaises(core.FactoryError):
            await core.set_visual(out["project_id"], 1, card="hook_card")

    async def test_removing_second_proof_is_rejected_even_with_in_bounds_clips(self):
        out = await self.make(review=True)
        job = Path(out["project_dir"])
        tl = timeline.load(job)
        for scene, mapping in zip(tl["scenes"], tl["benchmark"]["scene_evidence"]):
            if mapping["evidence_id"] == "evidence_2":
                mapping.update(evidence_id="evidence_1", src_start=31, src_end=31 + scene["duration"])
                scene["visual"].update(src_start=31, src_end=31 + scene["duration"])
        timeline.save(job, tl)
        done = await core.resume(out["project_id"], log=lambda _: None)
        self.assertEqual(done["status"], "failed")
        self.render.assert_not_awaited()

    async def test_long_caption_edit_is_reported_before_render_not_silently_cut(self):
        out = await self.make(review=True)
        core.edit_scene(out["project_id"], 1, narration="한" * 100)
        done = await core.resume(out["project_id"], log=lambda _: None)
        self.assertEqual(done["status"], "failed")
        self.render.assert_not_awaited()

    async def test_rights_are_required_before_project_creation(self):
        with self.assertRaises(core.FactoryError):
            await core.make(video=[str(self.video)], benchmark="kpop_observation_clip", benchmark_plan=str(self.plan_path))
        self.assertFalse((self.root / "output").exists())

    async def test_remote_input_is_not_downloaded(self):
        with self.assertRaises(core.FactoryError):
            await core.make(video=["https://example.com/video.mp4"], benchmark="kpop_observation_clip", asset_rights=self.rights)
        self.probe.assert_not_awaited()

    async def test_invalid_plan_duration_fails_before_project_creation(self):
        data = plan_data()
        data["evidence"][1]["clip"]["end"] = 90
        self.plan_path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(core.FactoryError):
            await self.make()
        self.assertFalse((self.root / "output").exists())

    async def test_paid_or_v1_options_cannot_enter_benchmark(self):
        for opts in ({"llm": "openai"}, {"allow_openai": True}, {"tts": "edge"}, {"content_format": "information"}, {"topic": "topic"}):
            with self.subTest(opts=opts), self.assertRaises(core.FactoryError):
                await self.make(**opts)
        self.analyze.assert_not_awaited()

    async def test_supplied_observations_skip_vision_but_run_reason_first_analysis(self):
        out = await core.make(video=[str(self.video)], benchmark="kpop_observation_clip", asset_rights=self.rights,
                              benchmark_observations=str(ROOT / "examples/benchmark_observations.json"), review=True, log=lambda _: None)
        self.assertEqual(out["status"], "waiting_for_script_approval")
        self.observe.assert_not_awaited()
        self.analyze.assert_awaited_once()

    async def test_default_video_path_collects_observations_then_analyzes(self):
        out = await core.make(video=[str(self.video)], benchmark="kpop_observation_clip", asset_rights=self.rights,
                              review=True, instructions="짧은 해설", log=lambda _: None)
        self.assertEqual(out["status"], "waiting_for_script_approval")
        self.observe.assert_awaited_once()
        self.analyze.assert_awaited_once()
        self.assertEqual(self.analyze.await_args.kwargs["instructions"], "짧은 해설")
        self.assertEqual(out["analysis_method"], "sampled_frames")

    async def test_benchmark_cli_and_existing_cli_parse_independently(self):
        a = cli._parser().parse_args(["make", "--video", str(self.video), "--benchmark", "kpop_observation_clip", "--review", "--confirm-rights", "--note", "my footage"])
        self.assertEqual(a.video, [str(self.video)])
        self.assertEqual(cli._parser().parse_args(["make", "--topic", "cat", "--format", "story"]).content_format, "story")
        result = await cli._dispatch(cli._parser().parse_args(["benchmark-profiles"]))
        self.assertEqual(len(result["profiles"]), 1)

    async def test_video_without_benchmark_is_a_clear_error(self):
        with self.assertRaises(core.FactoryError):
            await core.make(video=[str(self.video)])
