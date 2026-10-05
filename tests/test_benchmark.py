"""Offline benchmark contracts, claim selection, rights and render adaptation.

All video probing/FFmpeg is mocked. No AI, TTS, downloads or real production.
"""
from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.factory import __main__ as cli, benchmark as factory, core
from app.pipeline import benchmark, render, timeline
from app.pipeline.benchmark_models import BenchmarkInput, BenchmarkProfile
from app.pipeline.sources import SourceRegistry
from app.pipeline.subtitles import build_ass

EXAMPLE = benchmark.PROFILE_ROOT / "examples" / "kpop_comparison.input.json"


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def input_model(raw=None) -> BenchmarkInput:
    return BenchmarkInput.model_validate(raw or example())


def selected(raw=None, seconds=30):
    return benchmark.select_pair(input_model(raw), benchmark.load_profile("kpop_observation_clip"),
                                 {"practice": 90}, seconds=seconds)


class ProfileTests(unittest.TestCase):
    def test_profile_contains_all_six_types_and_default_structure(self):
        profile = benchmark.load_profile("kpop_observation_clip")
        self.assertEqual(set(profile.observation_types), {"discovery", "unexpected_change", "comparison",
                         "common_pattern", "rediscovery", "evidence_based_reaction"})
        self.assertEqual([(b.start, b.end) for b in profile.content_structure], [(0, 2), (2, 8), (8, 22), (22, 30)])
        self.assertEqual(len(benchmark.profiles()), 8)

    def test_profile_rejects_channel_design_and_media(self):
        for field in ("logo", "font", "colors", "source_video", "channel_url"):
            with self.subTest(field=field):
                raw = benchmark.load_profile("kpop_observation_clip").model_dump()
                raw[field] = "do-not-copy"
                with self.assertRaises(ValidationError):
                    BenchmarkProfile.model_validate(raw)

    def test_profile_disallows_traversal_and_discontinuous_structure(self):
        with self.assertRaises(ValidationError):
            benchmark.load_profile("../config")
        raw = benchmark.load_profile("kpop_observation_clip").model_dump()
        raw["content_structure"][1]["start"] = 3
        with self.assertRaises(ValidationError):
            BenchmarkProfile.model_validate(raw)

    def test_other_profile_can_be_added_without_code_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            import yaml
            root = Path(folder)
            raw = benchmark.load_profile("kpop_observation_clip").model_dump()
            raw["id"] = "performance_discovery"
            (root / "performance_discovery.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
            self.assertEqual(benchmark.profiles(root)[0]["id"], "performance_discovery")


class SelectionTests(unittest.TestCase):
    def test_preserves_full_claim_evidence_pair_and_annotation_provenance(self):
        plan = selected()
        self.assertEqual(plan.selection.claim, "같은 안무인데 멤버마다 느낌이 완전히 다르다")
        self.assertEqual([(e.start, e.end) for e in plan.selection.evidence_clips], [(31, 37), (64, 70)])
        self.assertEqual(plan.confidence, 0.8)  # weak evidence caps the stronger claim
        self.assertEqual(plan.semantic_verification, "user_annotations_only")
        self.assertIn("User reasoning", plan.reasoning_summary)

    def test_all_six_observation_types_select_grounded_pairs(self):
        for kind in benchmark.load_profile("kpop_observation_clip").observation_types:
            with self.subTest(kind=kind):
                raw = example()
                raw["observations"][0]["observation_type"] = kind
                self.assertEqual(selected(raw).selection.observation_type, kind)

    def test_discovery_and_rediscovery_allow_one_clip(self):
        for kind in ("discovery", "rediscovery", "evidence_based_reaction"):
            raw = example()
            raw["observations"][0]["observation_type"] = kind
            raw["observations"][0]["evidence_clips"] = raw["observations"][0]["evidence_clips"][:1]
            self.assertEqual(len(selected(raw).selection.evidence_clips), 1)

    def test_comparative_types_reject_one_clip(self):
        for kind in ("comparison", "common_pattern", "unexpected_change"):
            raw = example()
            raw["observations"][0]["observation_type"] = kind
            raw["observations"][0]["evidence_clips"] = raw["observations"][0]["evidence_clips"][:1]
            with self.assertRaisesRegex(ValueError, "insufficient independent"):
                selected(raw)

    def test_rejects_same_perspective_or_overlapping_evidence(self):
        raw = example()
        raw["observations"][0]["evidence_clips"][1]["perspective"] = "멤버 A"
        with self.assertRaisesRegex(ValueError, "distinct perspectives"):
            selected(raw)
        raw = example()
        raw["observations"][0]["evidence_clips"][1].update(start=35, end=41)
        with self.assertRaisesRegex(ValueError, "overlapping"):
            selected(raw)

    def test_rejects_unknown_source_out_of_bounds_and_low_confidence(self):
        cases = [({"source_id": "unknown"}, "unknown source"), ({"end": 100}, "exceeds"),
                 ({"confidence": 0.4}, "below profile threshold")]
        for values, message in cases:
            with self.subTest(values=values):
                raw = example()
                raw["observations"][0]["evidence_clips"][1].update(values)
                with self.assertRaisesRegex(ValueError, message):
                    selected(raw)

    def test_reason_and_support_notes_are_required_not_just_highlight(self):
        for target, field in (("candidate", "reason_to_watch"), ("candidate", "claim"),
                              ("clip", "observation"), ("clip", "supports_claim")):
            raw = example()
            node = raw["observations"][0]
            if target == "clip":
                node = node["evidence_clips"][0]
            node[field] = "  "
            with self.assertRaises(ValidationError):
                input_model(raw)

    def test_rejects_nonfinite_or_reversed_time_and_duplicate_ids(self):
        for values in ({"start": -1}, {"end": 30}, {"start": float("nan")}, {"end": float("inf")}):
            raw = example()
            raw["observations"][0]["evidence_clips"][0].update(values)
            with self.assertRaises(ValidationError):
                input_model(raw)
        raw = example()
        raw["observations"] *= 2
        with self.assertRaises(ValidationError):
            input_model(raw)
        with self.assertRaises(ValueError):
            benchmark.select_pair(input_model(), benchmark.load_profile("kpop_observation_clip"), {"practice": float("nan")})

    def test_claim_first_ranking_drops_unsupported_high_confidence_pair(self):
        raw = example()
        invalid = copy.deepcopy(raw["observations"][0])
        invalid.update(id="unsupported", confidence=0.99)
        invalid["evidence_clips"] = invalid["evidence_clips"][:1]
        raw["observations"].insert(0, invalid)
        plan = selected(raw)
        self.assertEqual(plan.selection.id, "member_comparison")
        self.assertEqual(plan.rejected_candidates[0]["id"], "unsupported")

    def test_confidence_ranking_and_explicit_type_filter(self):
        raw = example()
        alternative = copy.deepcopy(raw["observations"][0])
        alternative.update(id="discovery", observation_type="discovery", confidence=0.95)
        for evidence in alternative["evidence_clips"]:
            evidence["confidence"] = 0.95
        raw["observations"].append(alternative)
        self.assertEqual(selected(raw).selection.id, "discovery")
        filtered = benchmark.select_pair(input_model(raw), benchmark.load_profile("kpop_observation_clip"),
                                         {"practice": 90}, observation_type="comparison")
        self.assertEqual(filtered.selection.id, "member_comparison")

    def test_duration_contract(self):
        for value in (19, 36, 30.5, True):
            with self.assertRaises(ValueError):
                selected(seconds=value)
        self.assertEqual(selected(seconds=20).target_seconds, 20)
        self.assertEqual(selected(seconds=35).target_seconds, 35)


class TimelineTests(unittest.TestCase):
    def test_structure_scales_and_every_slice_stays_inside_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            for seconds in (20, 30, 35):
                plan = selected(seconds=seconds)
                tl = benchmark.build_timeline(job, plan, {"practice": {"path": str(job / "practice.mp4"), "has_audio": True}})
                self.assertAlmostEqual(timeline.total_duration(tl), seconds, places=2)
                self.assertEqual((tl["width"], tl["height"], tl["narration"]), (1080, 1920, ""))
                self.assertEqual(tl["source_volume"], 1)
                self.assertEqual(tl["benchmark"]["structure"][-1]["end"], seconds)
                self.assertEqual({s["evidence_index"] for s in tl["scenes"]}, {0, 1})
                for scene in tl["scenes"]:
                    evidence = plan.selection.evidence_clips[scene["evidence_index"]]
                    self.assertGreaterEqual(scene["visual"]["src_start"], evidence.start)
                    self.assertLessEqual(scene["visual"]["src_start"] + scene["duration"], evidence.end + 0.001)
                for idx, evidence in enumerate(plan.selection.evidence_clips):
                    intervals = sorted((s["visual"]["src_start"], s["visual"]["src_start"] + s["duration"])
                                       for s in tl["scenes"] if s["evidence_index"] == idx
                                       and s["role"] in ("first_evidence", "comparison_or_interpretation"))
                    covered = evidence.start
                    for lo, hi in intervals:
                        self.assertLessEqual(lo, covered + 0.001)
                        covered = max(covered, hi)
                    self.assertGreaterEqual(covered, evidence.end - 0.001)
                self.assertTrue(any(s["replay"] for s in tl["scenes"]))
                self.assertEqual(tl["subtitles"]["lines"][-1]["text"], plan.selection.ending_question)

    def test_oversized_evidence_is_rejected_instead_of_losing_the_proof(self):
        raw = example()
        raw["observations"][0]["evidence_clips"][0].update(start=0, end=60)
        with self.assertRaisesRegex(ValueError, "complete evidence does not fit"):
            selected(raw, seconds=20)

    def test_long_first_evidence_continues_into_interpretation_in_full(self):
        raw = example()
        raw["observations"][0]["evidence_clips"][0].update(start=0, end=10)
        tl = benchmark.build_timeline(Path("."), selected(raw),
                                      {"practice": {"path": "practice.mp4", "has_audio": False}})
        proof = [s for s in tl["scenes"] if s["role"] in ("first_evidence", "comparison_or_interpretation")]
        self.assertEqual([(s["visual"]["src_start"], s["duration"]) for s in proof[:3]], [(0, 6), (6, 4), (64, 6)])

    def test_muted_and_silent_sources_do_not_request_audio_stream(self):
        plan = selected().model_copy(update={"preserve_audio": False})
        tl = benchmark.build_timeline(Path("."), plan, {"practice": {"path": "practice.mp4", "has_audio": True}})
        self.assertEqual(tl["source_volume"], 0)
        self.assertTrue(all(not s["visual"]["has_audio"] for s in tl["scenes"]))

    def test_four_short_evidence_clips_are_all_visible(self):
        raw = example()
        base = raw["observations"][0]["evidence_clips"][0]
        raw["observations"][0]["evidence_clips"] = [
            {**base, "start": i * 3, "end": i * 3 + 2, "perspective": f"case {i}"} for i in range(4)]
        tl = benchmark.build_timeline(Path("."), selected(raw, seconds=20),
                                      {"practice": {"path": "practice.mp4", "has_audio": False}})
        self.assertEqual({s["evidence_index"] for s in tl["scenes"]}, {0, 1, 2, 3})

    def test_static_caption_wrap_and_escaping(self):
        with tempfile.TemporaryDirectory() as folder:
            out = build_ass([], Path(folder) / "s.ass", 1080, 1920, line_wrap_chars=16,
                            lines=[{"start": 2, "end": 8, "text": "아주긴반응자막을줄바꿈해서화면안에보여준다{test}", "words": []}])
            text = out.read_text(encoding="utf-8-sig")
        self.assertIn("\\N", text)
        self.assertNotIn("{test}", text)
        self.assertNotIn("\\k", text)


class RenderGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_timeline_adapter_builds_ass_and_passes_no_narration(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            clip = job / "practice.mp4"
            clip.write_bytes(b"test video")
            registry = SourceRegistry(job)
            registry.add(kind="video", origin="upload", path=str(clip),
                         rights=core._own_rights("my_channel", "직접 촬영", True))
            tl = benchmark.build_timeline(job, selected(), {"practice": {"path": str(clip), "has_audio": True}})
            with patch.object(timeline, "render_broll", new=AsyncMock()) as broll:
                await timeline.render_timeline(tl, job, job / "final.mp4")
            self.assertIsNone(broll.await_args.args[1])
            self.assertEqual(broll.await_args.kwargs["frame_layout"], "observation")
            self.assertEqual(broll.await_args.kwargs["source_volume"], 1)
            self.assertTrue((job / "subs.ass").is_file())
            self.assertIn(selected().selection.ending_question, (job / "subs.ass").read_text(encoding="utf-8-sig").replace("\\N", ""))

    async def test_narration_free_broll_preserves_audio_and_reserves_hook_area(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(render, "run_ffmpeg", new=AsyncMock()) as ffmpeg:
            path = Path(folder)
            await render.render_broll([
                {"kind": "video", "path": path / "video.mp4", "start": 31, "duration": 6, "has_audio": True},
                {"kind": "video", "path": path / "silent.mp4", "start": 0, "duration": 6, "has_audio": False},
            ], None, path / "final.mp4", frame_layout="observation", source_volume=1,
                overlays=[{"path": path / "brand.png", "start": 0, "end": 12, "width": 1, "x": .5, "y": .5}])
            args = ffmpeg.await_args.args[0]
            graph = args[args.index("-filter_complex") + 1]
            self.assertNotIn("[narr]", graph)
            self.assertIn("[acat]anull[aout]", graph)
            self.assertIn("volume=1", graph)
            self.assertIn("force_original_aspect_ratio=decrease", graph)
            self.assertNotIn("crop=", graph)
            self.assertIn("[2:v]scale=", graph)  # overlay input index without narration
            self.assertIn("anullsrc", graph)  # safe silent-source stream

    async def test_v1_narration_and_overlay_input_indexes_remain_valid(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(render, "run_ffmpeg", new=AsyncMock()) as ffmpeg:
            path = Path(folder)
            bgm = path / "bgm.mp3"
            bgm.write_bytes(b"audio")
            await render.render_broll([{"kind": "video", "path": path / "v.mp4", "start": 0,
                                        "duration": 3, "has_audio": True}], path / "narration.mp3", path / "final.mp4",
                                      bgm=bgm, overlays=[{"path": path / "brand.png", "start": 0, "end": 3}])
            args = ffmpeg.await_args.args[0]
            graph = args[args.index("-filter_complex") + 1]
            self.assertIn("[1:a]aformat", graph)
            self.assertIn("[2:a]aloop", graph)
            self.assertIn("[3:v]scale=", graph)
            self.assertIn("amix=inputs=3", graph)


class FactoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "my_practice.mp4").write_bytes(b"local owned video")
        self.input = self.root / "input.json"
        self.input.write_text(json.dumps(example(), ensure_ascii=False), encoding="utf-8")
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(core, "output_root", return_value=self.root / "output"))
        self.stack.enter_context(patch.object(factory, "require_ffmpeg"))
        self.probe = self.stack.enter_context(patch.object(factory, "probe_video", new=AsyncMock(
            return_value={"streams": [{"width": 1080, "height": 1920}], "format": {"duration": "90"}})))
        self.stack.enter_context(patch.object(factory, "has_audio", new=AsyncMock(return_value=True)))
        self.llm = self.stack.enter_context(patch("app.pipeline.llm.ask_structured", new=AsyncMock(side_effect=AssertionError("no AI"))))
        self.tts = self.stack.enter_context(patch("app.pipeline.run.get_tts", side_effect=AssertionError("no TTS")))
        self.download = self.stack.enter_context(patch("app.pipeline.youtube.download_media", new=AsyncMock(side_effect=AssertionError("no download"))))

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    async def make_plan(self):
        return await factory.plan(str(self.input), confirm_rights=True, note="내가 직접 촬영한 영상", log=lambda _: None)

    async def successful_render(self, project_id):
        async def fake_render(tl, job, output):
            output.write_bytes(b"rendered MP4")
            (job / "subs.ass").write_text("ASS", encoding="utf-8")
            return output
        def probe_result(path):
            return {"streams": [{"width": 1080, "height": 1920}],
                    "format": {"duration": "30" if ".tmp.mp4" in str(path) else "90"}}
        with patch.object(factory, "probe_video", new=AsyncMock(side_effect=probe_result)), \
                patch.object(timeline, "render_timeline", new=AsyncMock(side_effect=fake_render)) as rendering:
            out = await factory.render(project_id, log=lambda _: None)
        return out, rendering

    async def test_plan_persists_rights_pair_and_isolated_state_without_api_calls(self):
        out = await self.make_plan()
        self.assertEqual(out["status"], "benchmark_ready")
        job = Path(out["project_dir"])
        self.assertTrue((job / "sources.json").is_file())
        self.assertTrue((job / "uploads" / "practice.mp4").is_file())
        self.assertFalse((job / "project_state.json").exists())
        self.assertEqual(core._projects(), [])  # benchmark jobs never become V1 latest
        self.assertEqual(out["ai_calls"], [])
        self.llm.assert_not_called()
        self.tts.assert_not_called()
        self.download.assert_not_called()

    async def test_requires_rights_confirmation_and_note_before_media_probe(self):
        for kwargs in ({}, {"confirm_rights": True}, {"note": "내 영상"}):
            with self.assertRaises(core.FactoryError) as error:
                await factory.plan(str(self.input), **kwargs)
            self.assertEqual(error.exception.code, "rights")
        self.probe.assert_not_awaited()

    async def test_licensed_upload_records_permission_and_remains_guarded(self):
        out = await factory.plan(str(self.input), confirm_rights=True, note="원저작자에게 영상과 음악 사용 허가를 받음",
                                 license_="licensed_upload", log=lambda _: None)
        registry = SourceRegistry(Path(out["project_dir"]))
        item = next(iter(registry.items.values()))
        self.assertEqual(item.license, "licensed_upload")
        self.assertTrue(item.usable_in_video)
        bad = registry.add(kind="video", origin="upload", path=str(self.root / "unconfirmed.mp4"),
                           rights=core._own_rights("licensed_upload", "허가 여부 미확인", False))
        self.assertFalse(bad.usable_in_video)

    async def test_two_local_sources_are_copied_and_linked_to_one_claim(self):
        raw = example()
        second = self.root / "other.mp4"
        second.write_bytes(b"other owned video")
        raw["sources"].append({"id": "other", "path": "other.mp4"})
        raw["observations"][0]["evidence_clips"][1]["source_id"] = "other"
        self.input.write_text(json.dumps(raw), encoding="utf-8")
        out = await self.make_plan()
        self.assertEqual(set(out["sources"]), {"practice", "other"})
        self.assertEqual(out["plan"]["selection"]["evidence_clips"][1]["source_id"], "other")
        self.assertEqual(len(SourceRegistry(Path(out["project_dir"])).items), 2)

    async def test_rejects_urls_network_sources_and_missing_files(self):
        for path in ("https://youtube.com/shorts/abc", "\\\\server\\video.mp4", "missing.mp4"):
            raw = example()
            raw["sources"][0]["path"] = path
            self.input.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(core.FactoryError) as error:
                await self.make_plan()
            self.assertEqual(error.exception.code, "invalid")
        self.probe.assert_not_awaited()

    async def test_render_uses_existing_timeline_and_preserves_output_records(self):
        ready = await self.make_plan()
        out, renderer = await self.successful_render(ready["project_id"])
        self.assertEqual(out["status"], "render_complete")
        tl = renderer.await_args.args[0]
        self.assertEqual(tl["mode"], "observation")
        self.assertEqual(tl["narration"], "")
        self.assertEqual(out["resolution"], "1080x1920")
        self.assertTrue(Path(out["outputs"]["final_video"]).is_file())
        SourceRegistry(Path(out["project_dir"])).guard_timeline(tl)
        self.llm.assert_not_called()
        self.tts.assert_not_called()

    async def test_render_rechecks_registry_and_source_fingerprint(self):
        for change in ("rights", "content", "registry"):
            ready = await self.make_plan()
            job = Path(ready["project_dir"])
            if change == "rights":
                rights = json.loads((job / "sources.json").read_text(encoding="utf-8"))
                rights[0]["rights_confirmed"] = False
                (job / "sources.json").write_text(json.dumps(rights), encoding="utf-8")
            elif change == "content":
                (job / "uploads" / "practice.mp4").write_bytes(b"different evidence")
            else:
                (job / "sources.json").unlink()
            with patch.object(timeline, "render_timeline", new=AsyncMock()) as renderer:
                out = await factory.render(ready["project_id"], log=lambda _: None)
            self.assertEqual(out["status"], "failed")
            self.assertEqual(out["failed_at"], "validation")
            renderer.assert_not_awaited()

    async def test_saved_evidence_edit_cannot_exceed_source_length(self):
        ready = await self.make_plan()
        job = Path(ready["project_dir"])
        raw = json.loads((job / benchmark.PLAN_FILE).read_text(encoding="utf-8"))
        raw["selection"]["evidence_clips"][1]["end"] = 100
        (job / benchmark.PLAN_FILE).write_text(json.dumps(raw), encoding="utf-8")
        with patch.object(timeline, "render_timeline", new=AsyncMock()) as renderer:
            out = await factory.render(ready["project_id"], log=lambda _: None)
        self.assertEqual(out["status"], "failed")
        renderer.assert_not_awaited()

    async def test_corrupt_saved_plan_reports_failure_and_keeps_inspect_usable(self):
        ready = await self.make_plan()
        job = Path(ready["project_dir"])
        (job / benchmark.PLAN_FILE).write_text("invalid JSON", encoding="utf-8")
        with patch.object(timeline, "render_timeline", new=AsyncMock()) as renderer:
            failed = await factory.render(ready["project_id"], log=lambda _: None)
        self.assertEqual(failed["status"], "failed")
        self.assertIsNone(failed["plan"])
        self.assertIn("plan_validation_error", failed)
        self.assertEqual(failed["next_action"], "benchmark plan")
        renderer.assert_not_awaited()

    async def test_failed_rerender_preserves_completed_video_and_plan(self):
        ready = await self.make_plan()
        completed, _ = await self.successful_render(ready["project_id"])
        final = Path(completed["outputs"]["final_video"])
        with patch.object(timeline, "render_timeline", new=AsyncMock(side_effect=RuntimeError("mock ffmpeg failure"))):
            failed = await factory.render(ready["project_id"], log=lambda _: None)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(final.read_bytes(), b"rendered MP4")
        self.assertTrue(Path(failed["plan_path"]).is_file())
        retry, _ = await self.successful_render(ready["project_id"])
        self.assertEqual(retry["status"], "render_complete")

    async def test_invalid_output_resolution_never_replaces_completed_file(self):
        ready = await self.make_plan()
        completed, _ = await self.successful_render(ready["project_id"])
        async def wrong_output(tl, job, out):
            out.write_bytes(b"wrong")
        def probe_result(path):
            return {"streams": [{"width": 720, "height": 1280}],
                    "format": {"duration": "30" if ".tmp.mp4" in str(path) else "90"}}
        with patch.object(timeline, "render_timeline", new=AsyncMock(side_effect=wrong_output)) as renderer, \
                patch.object(factory, "probe_video", new=AsyncMock(side_effect=probe_result)):
            failed = await factory.render(ready["project_id"], log=lambda _: None)
        renderer.assert_awaited_once()
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["failed_at"], "render")
        self.assertEqual(Path(completed["outputs"]["final_video"]).read_bytes(), b"rendered MP4")

    async def test_benchmark_id_cannot_escape_workspace(self):
        with self.assertRaises(core.FactoryError):
            factory.inspect("../outside")


class CLITests(unittest.TestCase):
    def test_new_commands_and_existing_v1_formats(self):
        parser = cli._parser()
        args = parser.parse_args(["benchmark", "plan", "--input", "x.json", "--mute-source"])
        self.assertEqual(args.profile_id, "kpop_observation_clip")
        self.assertTrue(args.mute_source)
        for fmt in ("information", "story", "issue"):
            self.assertEqual(parser.parse_args(["make", "--topic", "x", "--format", fmt]).content_format, fmt)

    def test_profiles_stdout_is_json_and_invalid_input_exit_code_is_two(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["benchmark", "profiles"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["profiles"][0]["id"], "kpop_observation_clip")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["benchmark", "plan", "--input", "missing.json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["error"], "rights")


if __name__ == "__main__":
    unittest.main()
