"""V1 입력 연결·실제 공급자 기록·순차 제작·화제 선택. 네트워크/렌더는 목이다."""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.factory import core, batch, state as st
from app.pipeline import llm
from app.pipeline.models import ResearchDoc, Word
from app.pipeline.reference import ReferenceBrief
from tests.test_factory import FactoryTestCase, cat_script
from tests import test_factory as factory_tests


class FactoryV1Tests(FactoryTestCase):
    async def test_ai_provider_is_saved_on_real_call_path(self):
        cfg_call = AsyncMock(return_value=cat_script())
        async def write(llm_cfg, *args, **kwargs):
            return await llm.ask_structured(llm_cfg, "s", "u", type(cat_script()))
        with patch.dict(llm.PROVIDERS, claude=cfg_call), patch.object(core.runmod.scriptmod, "write_script", new=write):
            result = await core.make(topic="고양이", review=True, log=lambda m: None)
        saved = st.load(Path(result["project_dir"]))
        self.assertEqual(saved["ai_provider_used"], "claude")
        self.assertEqual(saved["ai_providers_used"], ["claude"])
        self.assertEqual(saved["ai_calls"][0]["status"], "success")
        self.assertEqual(core.status(result["project_id"])["ai_provider_used"], "claude")

    async def test_openai_unapproved_blocked_before_pipeline(self):
        with self.assertRaises(core.FactoryError) as ctx:
            await core.make(topic="고양이", llm="openai", log=lambda m: None)
        self.assertEqual(ctx.exception.code, "paid_not_allowed")
        self.write_script.assert_not_awaited()
        self.assertEqual(list(self.root.iterdir()), [])

    async def test_supported_modes_and_free_defaults(self):
        for provider in ("claude", "auto"):
            cfg = core._run_cfg({"llm": provider, "preset": "engineering"})
            self.assertEqual(cfg["llm"]["provider"], provider)
            self.assertEqual(cfg["images"]["provider"], "none")
            self.assertEqual(cfg["tts"]["provider"], "edge")
        with patch.object(llm, "env", return_value="test-key"):
            cfg = core._run_cfg({"llm": "openai", "allow_openai": True})
        self.assertTrue(cfg["llm"]["allow_paid_openai"])
        self.assertEqual(cfg["llm"]["model"], cfg["llm"]["openai_model"])

    async def test_switch_from_openai_config_restores_subscription_model(self):
        cfg = core._cfg()
        cfg["llm"].update(provider="openai", model="gpt-5-mini", claude_model="claude-test")
        with patch.object(core, "_cfg", return_value=cfg):
            for mode in ("claude", "auto"):
                self.assertEqual(core._run_cfg({"llm": mode})["llm"]["model"], "claude-test")

    async def test_auto_topic_reuses_existing_trend_engine(self):
        from app.pipeline.models import TrendPick
        pick = TrendPick(keyword="고양이", reason="테스트", search_query="고양이")
        with patch.object(core.research, "hot_keywords", new=AsyncMock(return_value=["고양이"])), \
             patch.object(core.runmod.scriptmod, "pick_trend", new=AsyncMock(return_value=pick)):
            result = await core.make(auto=True, log=lambda m: None)
        self.assertEqual(result["status"], "render_complete")
        self.assertEqual(st.load(Path(result["project_dir"]))["request"]["mode"], "auto")

    async def test_youtube_url_reuses_transcript_without_reusing_video(self):
        url = "https://www.youtube.com/watch?v=testvideo11"
        info = {"title": "고양이", "channel": "참고 채널", "description": "참고용", "duration": 20, "webpage_url": url}
        with patch.object(core.runmod.youtube, "fetch_info", new=AsyncMock(return_value=info)), \
             patch.object(core.runmod.youtube, "fetch_transcript", new=AsyncMock(return_value=[Word(text="고양이", start=0, end=1)])), \
             patch.object(core.runmod.youtube, "download_media", new=AsyncMock()) as download:
            result = await core.make(url=url, log=lambda m: None)
        self.assertEqual(result["status"], "render_complete")
        download.assert_not_awaited()
        sources = json.loads((Path(result["project_dir"]) / "sources.json").read_text(encoding="utf-8"))
        self.assertTrue(sources)

    async def test_reference_video_is_analysis_only_and_survives_resume(self):
        src = self.root / "reference.mp4"
        src.write_bytes(b"mock video")
        brief = ReferenceBrief(topic="고양이", summary="상자 선호", search_query="고양이")
        with patch.object(core.runmod.refmod, "analyze_uploaded_video", new=AsyncMock(return_value=(
            brief, ResearchDoc(title="고양이", url="", text="전사"), [Word(text="고양이", start=0, end=1)]))):
            pending = await core.make(reference_video=str(src), hint="고양이", review=True, log=lambda m: None)
        state = st.load(Path(pending["project_dir"]))
        self.assertEqual(state["request"]["reference_name"], "reference.mp4")
        self.assertEqual(state["asset_rights"]["reference.mp4"]["license"], "reference_only")
        with patch.object(core.runmod.refmod, "analyze_uploaded_video", new=AsyncMock()) as analysis:
            result = await core.resume(pending["project_id"], log=lambda m: None)
        analysis.assert_not_awaited()
        self.assertEqual(result["status"], "render_complete")
        tl = json.loads((Path(result["project_dir"]) / "timeline.json").read_text(encoding="utf-8"))
        self.assertNotIn(str(src), json.dumps(tl))

    async def test_invalid_reference_and_duplicate_filenames_are_rejected(self):
        with self.assertRaises(core.FactoryError):
            await core.make(reference_video="missing.mp4")
        ref = self.root / "ref.mp4"
        ref.write_bytes(b"video")
        with self.assertRaises(core.FactoryError):
            await core.make(reference_video=str(ref), assets=[str(ref)])

    async def test_direct_script_automatic_mode_and_all_three_formats(self):
        for fmt in core.FORMATS:
            result = await core.make(script_text="첫째 문장입니다. 둘째 문장입니다. 셋째 문장입니다. 마지막 문장입니다.",
                                     content_format=fmt, log=lambda m: None)
            self.assertEqual(result["status"], "render_complete")
            self.assertEqual(st.load(Path(result["project_dir"]))["request"]["format"], fmt)

    async def test_resume_without_id_chooses_pending_over_recent_complete(self):
        first = await core.make(topic="고양이", review=True, log=lambda m: None)
        await core.make(topic="두번째", log=lambda m: None)
        resumed = await core.resume(log=lambda m: None)
        self.assertEqual(resumed["project_id"], first["project_id"])

    async def test_finish_probe_failure_is_saved_with_output_preserved(self):
        with patch.object(core, "probe_video", new=AsyncMock(side_effect=RuntimeError("probe failed"))):
            result = await core.make(topic="고양이", log=lambda m: None)
        self.assertEqual(result["status"], "failed")
        self.assertTrue((Path(result["project_dir"]) / "final.mp4").is_file())

    async def test_sequential_batch_continues_after_failure(self):
        active, max_active, calls = 0, 0, []
        async def make(**kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            calls.append(kwargs["topic"])
            await asyncio.sleep(0)
            active -= 1
            if kwargs["topic"] == "실패":
                raise RuntimeError("테스트 실패")
            return {"status": "render_complete", "project_id": kwargs["topic"]}
        with patch.object(core, "make", new=make):
            result = await batch.make(topics=["성공1", "실패", "성공2"], log=lambda m: None)
        self.assertEqual(max_active, 1)
        self.assertEqual(calls, ["성공1", "실패", "성공2"])
        self.assertEqual((result["completed"], result["failed"]), (2, 1))
        self.assertEqual(batch.status(result["batch_id"])["items"][0]["result"]["project_id"], "성공1")

    async def test_trends_selected_numbers_are_stable_across_searches(self):
        with patch.object(core.research, "hot_keywords", new=AsyncMock(return_value=["하나", "둘", "셋", "넷", "다섯"])):
            found = await core.trends(limit=5, log=lambda m: None)
        batch.save_candidates(self.root, ["다른 검색"])
        with patch.object(core, "make", new=AsyncMock(return_value={"status": "render_complete"})) as make:
            result = await batch.make(select=[2, 4], candidates_id=found["candidates_id"], log=lambda m: None)
        self.assertEqual([c.kwargs["topic"] for c in make.await_args_list], ["둘", "넷"])
        self.assertEqual(result["completed"], 2)

    async def test_batch_count_and_review_then_resume(self):
        pending = await batch.make(topics=["고양이"], count=2, review=True, log=lambda m: None)
        self.assertEqual(pending["waiting"], 2)
        self.assertTrue(all(not (Path(i["result"]["project_dir"]) / "final.mp4").exists() for i in pending["items"]))
        result = await batch.resume(pending["batch_id"], log=lambda m: None)
        self.assertEqual(result["completed"], 2)
        with patch.object(core, "resume", new=AsyncMock()) as resume:
            await batch.resume(pending["batch_id"], log=lambda m: None)
        resume.assert_not_awaited()

    async def test_bad_candidate_numbers_rejected_before_any_make(self):
        batch.save_candidates(self.root, ["첫째", "둘째"])
        with patch.object(core, "make", new=AsyncMock()) as make:
            for numbers in ([0], [3], [1, 1], [-1]):
                with self.assertRaises(core.FactoryError):
                    await batch.make(select=numbers)
        make.assert_not_awaited()

    async def test_empty_trends_explains_failure(self):
        with patch.object(core.research, "hot_keywords", new=AsyncMock(return_value=[])):
            with self.assertRaises(core.FactoryError):
                await core.trends(log=lambda m: None)


class V1CliTests(unittest.TestCase):
    _cli = factory_tests.CliJsonTests._cli

    def test_batch_selection_arguments(self):
        with patch.object(batch, "make", new=AsyncMock(return_value={"status": "completed"})) as make:
            code, _ = self._cli("batch", "--select", "2", "4", "--seconds", "45", "--llm", "auto")
        self.assertEqual(code, 0)
        self.assertEqual(make.await_args.kwargs["select"], [2, 4])

    def test_cli_explicit_paid_permission(self):
        with patch.object(core, "make", new=AsyncMock(return_value={"status": "render_complete"})) as make:
            self._cli("make", "--topic", "고양이", "--llm", "openai", "--allow-openai", "--format", "information")
        self.assertTrue(make.await_args.kwargs["allow_openai"])

    def test_batch_partial_failure_returns_nonzero(self):
        with patch.object(batch, "make", new=AsyncMock(return_value={"status": "partial_failure"})):
            code, _ = self._cli("batch", "--topic", "고양이")
        self.assertEqual(code, 1)


class LocalTranscriptionTests(unittest.TestCase):
    def test_reference_transcription_works_without_cuda_and_detects_source_language(self):
        from app.pipeline import youtube

        class CpuOnlyModel:
            def __init__(self, model_size, device, compute_type):
                if device != "cpu":
                    raise RuntimeError("Library cublas64_12.dll is not found")

            def transcribe(self, audio, **kwargs):
                if kwargs["language"] is not None:
                    raise RuntimeError("외국어 참고 음성을 한국어로 강제하면 안 됩니다.")
                word = SimpleNamespace(word=" light ", start=0.12345, end=1.23456)
                return iter([SimpleNamespace(words=[word])]), SimpleNamespace(language="en")

        with patch.dict(sys.modules, faster_whisper=SimpleNamespace(WhisperModel=CpuOnlyModel)):
            words = youtube._whisper_sync(Path("source.mp3"))
        self.assertEqual([w.model_dump() for w in words], [{"text": "light", "start": 0.123, "end": 1.235}])
