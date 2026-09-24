"""Focused checks for the new reference-video and source/comment review path."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.config import load_config, load_presets, merge_options
from app.pipeline import broll, comments, reference, run, vision
from app.pipeline.models import AssetDescription, AutoPlan, BrollPick, ResearchDoc, Scene, Script, SourceVideo, Word
from app.pipeline.subtitles import build_ass


class ReferenceWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_uploaded_video_uses_timeline_and_speech(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = root / "input.mp4"
            video.write_bytes(b"placeholder")
            frames = [root / "a.jpg", root / "b.jpg"]
            for frame in frames:
                frame.write_bytes(b"placeholder")
            words = [Word(text="공식 발표", start=2, end=3)]
            brief = reference.ReferenceBrief(topic="행사 발표", summary="행사에서 발표했다.", search_query="행사 발표 영상")
            with (patch.object(reference, "probe_duration", new=AsyncMock(return_value=24)),
                  patch.object(reference, "env", side_effect=lambda name: "test-key" if name == "GEMINI_API_KEY" else ""),
                  patch.object(reference, "extract_frames", new=AsyncMock(return_value=frames)),
                  patch.object(reference, "describe_all", new=AsyncMock(return_value=[
                      AssetDescription(description="무대", keywords=[]),
                      AssetDescription(description="발표 자료", keywords=[])])),
                  patch.object(reference, "has_audio", new=AsyncMock(return_value=True)),
                  patch.object(reference, "run_ffmpeg", new=AsyncMock()),
                  patch.object(reference, "_transcribe_audio", new=AsyncMock(return_value=words)),
                  patch.object(reference, "ask_structured", new=AsyncMock(return_value=brief)) as ask):
                result, doc, transcript = await reference.analyze_uploaded_video(
                    {"provider": "claude"}, video, root / "work")
            self.assertEqual(result.search_query, "행사 발표 영상")
            self.assertIn("공식 발표", doc.text)
            self.assertIn("발표 자료", ask.await_args.args[2])
            self.assertEqual(transcript, words)
            saved = json.loads((root / "work" / "analysis.json").read_text(encoding="utf-8"))
            self.assertEqual(len(saved["frames"]), 2)

    async def test_local_video_is_not_downloaded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mine.mp4"
            path.write_bytes(b"placeholder")
            source = SourceVideo(url="", title="내 영상", duration=30, path=str(path))
            pick = BrollPick(scene_index=0, source_index=0, start=2, end=6, reason="테스트")
            with patch.object(broll, "download_media", new=AsyncMock()) as download:
                await broll.download_sources([source], [pick], Path(folder))
                await broll.load_timelines([source], Path(folder))
            download.assert_not_awaited()
            self.assertEqual(source.path, str(path))

    async def test_gpt_can_describe_sampled_frame(self):
        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": json.dumps({
                    "description": "무대 위 발표 자료에 안전 수칙이라고 적혀 있다", "keywords": ["안전 수칙"]}, ensure_ascii=False)}}]}

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def post(self, *args, **kwargs):
                self.body = kwargs["json"]
                return Response()

        with tempfile.TemporaryDirectory() as folder:
            frame = Path(folder) / "frame.jpg"
            frame.write_bytes(b"fake-image")
            client = Client()
            with (patch.object(vision, "env", return_value="test-key"),
                  patch.object(vision.httpx, "AsyncClient", return_value=client)):
                description = await vision.describe_image(frame, provider="openai", model="gpt-4.1-mini")
            self.assertIn("안전 수칙", description.description)
            self.assertEqual(client.body["model"], "gpt-4.1-mini")
            self.assertEqual(client.body["messages"][0]["content"][1]["type"], "image_url")

    async def test_comment_api_result_and_subtitle_card(self):
        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {"items": [{"snippet": {"topLevelComment": {
                    "id": "c1", "snippet": {"textDisplay": "정말 인상적이네요", "likeCount": 5}}}}]}

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, *args, **kwargs):
                self.params = kwargs["params"]
                return Response()

        client = Client()
        with (patch.object(comments, "env", return_value="fake-api-key"),
              patch.object(comments.httpx, "AsyncClient", return_value=client)):
            candidates = await comments.fetch_candidates(["https://youtu.be/abc123"])
        self.assertEqual(candidates[0]["text"], "정말 인상적이네요")
        self.assertEqual(client.params["videoId"], "abc123")
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "subs.ass"
            build_ass([], output, 1080, 1920, comments=[(2, 5, candidates[0]["text"])])
            self.assertIn("정말 인상적이네요", output.read_text(encoding="utf-8-sig"))

    async def test_upload_job_reaches_source_and_comment_review(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            (job / "uploads").mkdir()
            (job / "uploads" / "my.mp4").write_bytes(b"placeholder")
            cfg = load_config()
            preset = load_presets(cfg)["entertainment"]
            cfg = merge_options(cfg, preset, {})
            brief = reference.ReferenceBrief(topic="행사 발표", summary="공식 발표", search_query="행사 발표 뉴스 영상")
            plan = AutoPlan(angle="발표 요약", hook_type="질문", structure="발표와 반응", scene_count=6,
                            visual_mode="broll", reason="현장 영상 필요")
            doc = ResearchDoc(title="행사 발표", url="", text="공식 발표 내용")
            script = Script(topic="행사 발표", scenes=[Scene(narration="공식 발표입니다", image_prompt="stage, no text", on_screen_text="발표")],
                            titles=["행사 발표"], description="요약", hashtags=["행사"], sources=[])
            source = SourceVideo(url="https://www.youtube.com/watch?v=abc123", title="관련 영상", duration=100)
            comment = {"id": "c1", "text": "좋은 발표네요", "url": "https://www.youtube.com/watch?v=abc123&lc=c1"}
            seen = {}

            async def review_script(proposed, preview):
                seen.update(preview)
                return proposed, {"source_indexes": [0, 1], "comment_ids": ["c1"]}

            with (patch.object(run, "require_ffmpeg"),
                  patch.object(run.refmod, "analyze_uploaded_video", new=AsyncMock(return_value=(brief, doc, [Word(text="발표", start=1, end=2)]))),
                  patch.object(run, "probe_duration", new=AsyncMock(return_value=60)),
                  patch.object(run.research, "research_topic", new=AsyncMock(return_value=[])),
                  patch.object(run.scriptmod, "make_plan", new=AsyncMock(return_value=plan)),
                  patch.object(run.scriptmod, "write_script", new=AsyncMock(return_value=script)),
                  patch.object(run.brollmod, "gather_sources", new=AsyncMock(return_value=[source])) as search,
                  patch.object(run.commentmod, "fetch_candidates", new=AsyncMock(return_value=[comment]))):
                result = await run.run_pipeline(job, "upload", "", cfg, review=review_script,
                                                until="script", visual_mode="broll", reference_name="my.mp4")
            self.assertEqual(search.await_args.args[1], "행사 발표 뉴스 영상")
            self.assertEqual(len(seen["source_candidates"]), 2)
            self.assertEqual(result["selected_comments"][0]["id"], "c1")
            self.assertIn(comment["url"], (job / "meta.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
