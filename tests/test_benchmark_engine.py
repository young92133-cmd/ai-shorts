"""Benchmark contracts, reason-first analysis and V1 render integration; no live calls."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.benchmarks import adapters, engine
from app.benchmarks.models import BenchmarkPlan, BenchmarkProfile, EvidenceClip, EvidenceSelection, Material, WatchIntent
from app.benchmarks.profiles import load_profile, profile_names
from app.pipeline import capcut, llm, render, timeline
from app.pipeline.models import Script

ROOT = Path(__file__).resolve().parents[1]


def plan_data():
    return json.loads((ROOT / "examples/benchmark_plan.json").read_text(encoding="utf-8"))


def plan():
    return BenchmarkPlan.model_validate(plan_data())


def material():
    return Material.model_validate_json((ROOT / "examples/benchmark_observations.json").read_text(encoding="utf-8"))


def sources(root):
    return {"video_1": {"path": str(Path(root) / "uploads/video_1.mp4"), "duration": 80, "has_audio": True}}


class ContractTests(unittest.TestCase):
    def test_only_requested_profile_is_available(self):
        self.assertEqual(profile_names(), ["kpop_observation_clip"])
        p = load_profile("kpop_observation_clip")
        self.assertEqual(len(p.observation_types), 6)
        self.assertEqual([s.seconds for s in p.stages], [2, 6, 14, 8])

    def test_missing_and_unsafe_profile_names(self):
        with self.assertRaises(FileNotFoundError):
            load_profile("curiosity_update_story")
        for name in ("../config", "KPOP", "", "c:/file"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                load_profile(name)

    def test_default_settings_are_genre_neutral(self):
        p = BenchmarkProfile(profile_name="unit_profile", content_type="unit_content")
        self.assertEqual(p.stages, [])
        self.assertEqual(p.observation_types, {})
        self.assertEqual((p.render.width, p.render.height, p.length.target), (1080, 1920, 30))
        self.assertFalse(p.render.narration)

    def test_clip_rejects_reversed_negative_or_nonfinite_bounds(self):
        for start, end in ((5, 5), (6, 5), (-1, 2), (0, float("inf")), (float("nan"), 5)):
            with self.subTest(start=start, end=end), self.assertRaises(ValidationError):
                EvidenceClip(source_id="video_1", start=start, end=end)

    def test_required_reason_and_confidence_schema(self):
        for field, value in (("reason_to_watch", ""), ("viewer_question", " "), ("confidence", 1.1), ("confidence", float("nan"))):
            data = plan_data()
            data[field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                BenchmarkPlan.model_validate(data)

    def test_visual_evidence_requires_clip_and_unique_ids(self):
        for edit in (lambda d: d["evidence"][0].pop("clip"),
                     lambda d: d["evidence"][1].update(id="evidence_1")):
            data = plan_data()
            edit(data)
            with self.assertRaises(ValidationError):
                BenchmarkPlan.model_validate(data)

    def test_all_six_observation_types_validate(self):
        p = load_profile("kpop_observation_clip")
        for name in p.observation_types:
            with self.subTest(name=name):
                engine.validate_plan(plan().model_copy(update={"observation_type": name}), p)

    def test_unknown_observation_and_profile_mismatch(self):
        p = load_profile("kpop_observation_clip")
        for update in ({"observation_type": "highlight"}, {"profile_name": "other"}, {"content_type": "other"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                engine.validate_plan(plan().model_copy(update=update), p)

    def test_weak_confidence_or_insufficient_comparison_is_rejected(self):
        p = load_profile("kpop_observation_clip")
        for update in ({"confidence": 0.64}, {"evidence": plan().evidence[:1], "reaction_captions": ["첫 근거"]}):
            with self.assertRaises(ValueError):
                engine.validate_plan(plan().model_copy(update=update), p)

    def test_overlapping_or_duplicate_sources_are_not_independent(self):
        p = load_profile("kpop_observation_clip")
        for start, end in ((31, 37), (35, 40)):
            data = plan_data()
            data["evidence"][1]["clip"].update(start=start, end=end)
            with self.assertRaises(ValueError):
                engine.validate_plan(BenchmarkPlan.model_validate(data), p)
        data = plan_data()
        data["evidence"][1]["clip"].update(source_id="video_2", start=31, end=37)
        s = {"video_1": {"duration": 80, "sha256": "same"}, "video_2": {"duration": 80, "sha256": "same"}}
        with self.assertRaises(ValueError):
            engine.validate_plan(BenchmarkPlan.model_validate(data), p, s)

    def test_sources_captions_and_observation_grounding(self):
        p, s = load_profile("kpop_observation_clip"), sources(ROOT)
        engine.validate_plan(plan(), p, s, material())
        for edit in (lambda d: d["evidence"][0]["clip"].update(source_id="missing"),
                     lambda d: d["evidence"][1]["clip"].update(end=90),
                     lambda d: d.update(reaction_captions=["only one"]),
                     lambda d: d["evidence"][0].update(observation_ids=["missing"]),
                     lambda d: d["evidence"][0]["clip"].update(start=30)):
            data = plan_data()
            edit(data)
            with self.assertRaises(ValueError):
                engine.validate_plan(BenchmarkPlan.model_validate(data), p, s, material())

    def test_nonvisual_contracts_do_not_require_v1_or_timestamps(self):
        # Hypothetical in-memory contract, not an implemented/shipped second profile.
        p = BenchmarkProfile(profile_name="unit_fact", content_type="unit_fact", render_adapter="unit_fact",
                             evidence_types=["fact"], observation_types={"detail": {"description": "one fact"}})
        data = {k: v for k, v in plan_data().items() if k not in ("evidence", "reaction_captions")}
        data.update(profile_name="unit_fact", content_type="unit_fact", observation_type="detail", evidence_type="fact",
                    evidence=[{"id": "fact_1", "evidence_type": "fact", "content": "dated fact", "supports_claim": "answers question",
                               "observation_ids": ["fact_observation"]}])
        m = Material(subject="fact input", observations=[{"id": "fact_observation", "evidence_type": "fact", "description": "dated fact"}])
        engine.validate_plan(BenchmarkPlan.model_validate(data), p, {}, m)
        self.assertFalse(issubclass(BenchmarkPlan, Script))
        self.assertNotIn("scenes", BenchmarkPlan.model_fields)
        for kind in ("comparison", "timeline", "reaction", "quote", "current_update", "multiple_examples"):
            d = copy.deepcopy(data)
            d["evidence_type"] = d["evidence"][0]["evidence_type"] = kind
            BenchmarkPlan.model_validate(d)

    def test_paid_providers_are_blocked_even_when_config_allows_them(self):
        p = engine.subscription_config({"provider": "auto", "allow_paid_openai": True, "allow_paid_anthropic": True})
        self.assertEqual(p["provider"], "claude")
        self.assertFalse(p["allow_paid_openai"] or p["allow_paid_anthropic"])
        for provider in ("openai", "anthropic", "gemini"):
            with self.assertRaises(ValueError):
                engine.subscription_config({"provider": provider})


class AnalysisTests(unittest.IsolatedAsyncioTestCase):
    async def test_reason_and_claim_are_locked_before_evidence_selection(self):
        data = plan_data()
        intent = WatchIntent.model_validate({k: data[k] for k in WatchIntent.model_fields})
        selection = EvidenceSelection.model_validate({k: data[k] for k in EvidenceSelection.model_fields})
        calls = []

        async def answer(cfg, system, user, schema):
            calls.append((cfg, system, user, schema))
            return intent if schema is WatchIntent else selection

        with tempfile.TemporaryDirectory() as folder, patch.object(engine, "ask_structured", side_effect=answer):
            out = await engine.analyze(load_profile("kpop_observation_clip"), material(), {"provider": "auto"}, sources(ROOT), Path(folder))
            self.assertTrue((Path(folder) / "benchmark_intent.json").exists())
        self.assertEqual([c[3] for c in calls], [WatchIntent, EvidenceSelection])
        self.assertNotIn('"start"', calls[0][2])
        self.assertNotIn('"evidence"', WatchIntent.model_json_schema()["properties"])
        self.assertNotIn("payoff", WatchIntent.model_fields)
        self.assertIn(intent.claim, calls[1][2])
        self.assertIn("LOCKED", calls[1][1])
        self.assertEqual(out.claim, intent.claim)
        self.assertEqual(out.payoff, selection.payoff)
        self.assertTrue(all(c[0]["provider"] == "claude" for c in calls))

    async def test_invalid_intent_stops_before_selecting_clips(self):
        data = plan_data()
        data["observation_type"] = "highlight"
        intent = WatchIntent.model_validate({k: data[k] for k in WatchIntent.model_fields})
        with patch.object(engine, "ask_structured", new=AsyncMock(return_value=intent)) as ask:
            with self.assertRaises(ValueError):
                await engine.analyze(load_profile("kpop_observation_clip"), material(), {}, sources(ROOT))
            self.assertEqual(ask.await_count, 1)

    async def test_subscription_images_are_inline_and_never_paid_fallback(self):
        async def answer(model, system, messages, schema, effort):
            chunks = [m async for m in messages]
            self.assertEqual(chunks[0]["message"]["content"][2]["type"], "image")
            return material()
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / "sample.jpg"
            image.write_bytes(b"fake jpeg")
            with patch.object(llm, "_ask_claude_code", side_effect=answer), patch.object(llm, "_ask_openai", new=AsyncMock()) as paid:
                await llm.ask_subscription_images({"provider": "claude"}, "system", "user", [("timestamp", image)], Material)
                paid.assert_not_awaited()
            with patch.object(llm, "_ask_claude_code", new=AsyncMock(side_effect=RuntimeError("usage limit"))), patch.object(llm, "_ask_openai", new=AsyncMock()) as paid:
                with self.assertRaises(RuntimeError):
                    await llm.ask_subscription_images({"provider": "auto", "allow_paid_openai": True}, "system", "user", [("timestamp", image)], Material)
                paid.assert_not_awaited()

    async def test_frame_sampling_is_bounded_and_rejects_invented_windows(self):
        p = load_profile("kpop_observation_clip")
        p.analysis.max_frames = 4

        async def fake_ffmpeg(args):
            Path(args[-1]).write_bytes(b"jpeg")

        async def vision(cfg, system, user, images, schema):
            self.assertEqual(len(images), 4)
            self.assertIn("NOT highlight", system)
            windows = json.loads(user.split("Allowed windows:\n")[1])
            w = windows[0]
            return Material(subject="visible", observations=[{"id": "o1", "description": "visible arm position",
                            "source_id": w["source_id"], "start": w["start"], "end": w["end"]}])

        with tempfile.TemporaryDirectory() as folder, patch.object(engine, "run_ffmpeg", side_effect=fake_ffmpeg), patch.object(engine, "ask_subscription_images", side_effect=vision):
            m = await engine.observe_video(p, sources(ROOT), {}, Path(folder), log=lambda _: None)
            self.assertEqual(m.observations[0].start, 0)
        with tempfile.TemporaryDirectory() as folder, patch.object(engine, "run_ffmpeg", side_effect=fake_ffmpeg), patch.object(engine, "ask_subscription_images", new=AsyncMock(return_value=material())):
            with self.assertRaisesRegex(ValueError, "sampled window"):
                await engine.observe_video(p, sources(ROOT), {}, Path(folder), log=lambda _: None)


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_default_stages_show_all_proof_before_payoff_without_tts(self):
        with tempfile.TemporaryDirectory() as folder:
            script, bp, tl = adapters.build(plan(), load_profile("kpop_observation_clip"), sources(folder), Path(folder))
        self.assertEqual(timeline.total_duration(tl), 30)
        self.assertEqual((tl["width"], tl["height"]), (1080, 1920))
        self.assertFalse(tl["narration"])
        self.assertEqual(bp.timing, "evidence_aligned")
        self.assertTrue(all(s.actual_tts_duration is None for s in bp.scenes))
        sums = {}
        for scene, mapping in zip(tl["scenes"], tl["benchmark"]["scene_evidence"]):
            clip = next(e.clip for e in plan().evidence if e.id == mapping["evidence_id"])
            self.assertGreaterEqual(scene["visual"]["src_start"], clip.start)
            self.assertLessEqual(scene["visual"]["src_end"], clip.end)
            if mapping["stage"] in ("first_evidence", "comparison_or_interpretation") and not mapping["replay"]:
                sums[mapping["evidence_id"]] = sums.get(mapping["evidence_id"], 0) + scene["duration"]
        self.assertEqual(sums, {"evidence_1": 6, "evidence_2": 6})
        self.assertIn(plan().payoff, [s.narration for s in script.scenes])
        self.assertIn(plan().ending_question, [s.narration for s in script.scenes])

    def test_timing_comes_from_profile_and_can_scale(self):
        p = load_profile("kpop_observation_clip")
        p.stages[0].seconds, p.stages[1].seconds = 3, 5
        _, bp, tl = adapters.build(plan(), p, sources(ROOT), ROOT, seconds=35)
        self.assertEqual(bp.scenes[0].end, 3.5)
        self.assertAlmostEqual(timeline.total_duration(tl), 35)

    def test_full_evidence_must_fit_not_silently_truncate(self):
        p = load_profile("kpop_observation_clip")
        with self.assertRaisesRegex(ValueError, "does not fit"):
            adapters.build(plan(), p, sources(ROOT), ROOT, seconds=10)

    def test_long_hook_or_caption_is_rejected_not_silently_truncated(self):
        p = load_profile("kpop_observation_clip")
        for update in ({"hook": "한" * 60}, {"payoff": "한" * 100}):
            with self.subTest(update=update), self.assertRaisesRegex(ValueError, "too long"):
                adapters.build(plan().model_copy(update=update), p, sources(ROOT), ROOT)

    def test_mute_and_subtitles_options(self):
        p = load_profile("kpop_observation_clip")
        p.render.preserve_source_audio = False
        _, _, tl = adapters.build(plan(), p, sources(ROOT), ROOT, subtitles=False)
        self.assertTrue(all(not s["visual"]["has_audio"] for s in tl["scenes"]))
        self.assertEqual(tl["source_volume"], 0)
        self.assertFalse(tl["subtitles"]["enabled"])

    async def test_timeline_calls_existing_broll_with_bounded_clips_and_static_captions(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            _, _, tl = adapters.build(plan(), load_profile("kpop_observation_clip"), sources(job), job)
            with patch.object(timeline, "render_broll", new=AsyncMock()) as broll, patch.object(timeline, "render_slideshow", new=AsyncMock()) as slideshow:
                await timeline.render_timeline(tl, job, job / "out.mp4")
            self.assertIsNone(broll.await_args.args[1])
            self.assertTrue(all("end" in c for c in broll.await_args.args[0]))
            self.assertEqual(broll.await_args.kwargs["frame_layout"], "evidence")
            slideshow.assert_not_awaited()
            ass = (job / "subs.ass").read_text(encoding="utf-8-sig")
            self.assertNotIn("\\k", ass)
            self.assertIn(plan().hook, ass)

    async def test_broll_no_narration_keeps_source_audio_and_exact_bounds(self):
        with patch.object(render, "run_ffmpeg", new=AsyncMock()) as ffmpeg:
            await render.render_broll([{"kind": "video", "path": Path("in.mp4"), "start": 31, "end": 37, "duration": 6, "has_audio": True}],
                                     None, Path("out.mp4"), source_volume=1, frame_layout="evidence", audio_fade_seconds=0)
        args = ffmpeg.await_args.args[0]
        filters = args[args.index("-filter_complex") + 1]
        self.assertIn("trim=31.000:37.000", filters)
        self.assertNotIn("trim=31.000:38.000", filters)
        self.assertNotIn("[narr]", filters)
        self.assertIn("volume=1", filters)
        self.assertNotIn("afade", filters)
        self.assertIn("force_original_aspect_ratio=decrease", filters)

    async def test_v1_broll_still_mixes_narration_with_original_defaults(self):
        with patch.object(render, "run_ffmpeg", new=AsyncMock()) as ffmpeg:
            await render.render_broll([{"kind": "video", "path": Path("in.mp4"), "start": 0, "duration": 6, "has_audio": True}], Path("narr.mp3"), Path("out.mp4"))
        args = ffmpeg.await_args.args[0]
        filters = args[args.index("-filter_complex") + 1]
        self.assertIn("narr.mp3", args)
        self.assertIn("amix=inputs=2", filters)
        self.assertIn("volume=0.12", filters)
        self.assertIn("afade=t=out:st=4.500:d=1.500", filters)

    async def test_no_narration_capcut_and_pack_export(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            s = sources(job)
            Path(s["video_1"]["path"]).parent.mkdir()
            Path(s["video_1"]["path"]).write_bytes(b"video")
            _, _, tl = adapters.build(plan(), load_profile("kpop_observation_clip"), s, job)
            timeline.save(job, tl)
            (job / "capcut").mkdir()
            async def fake_ffmpeg(args):
                Path(args[-1]).write_bytes(b"video")
            with patch.object(capcut, "run_ffmpeg", side_effect=fake_ffmpeg), patch.object(capcut, "probe_duration", new=AsyncMock(return_value=80)), patch.object(capcut, "probe_video", new=AsyncMock(return_value={"streams": [{"width": 1920, "height": 1080}], "format": {"duration": "80"}})):
                draft = await capcut.export_draft(tl, job, job / "capcut", "benchmark_test")
                self.assertTrue(draft.exists())
                pack = await capcut.export_pack(tl, job, job / "pack.zip")
                self.assertTrue(pack.exists())
