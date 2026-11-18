"""Google Flow 공학 쇼츠 (flowshorts · factory flow) — 실제 Flow·TTS·ffmpeg 호출 없음."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.factory import core, flow
from app.pipeline import flowshorts as fs
from app.pipeline.models import Word

NEG = "vertical 9:16. no text, no numbers, no arrows, no HUD, no logo, no watermark."


def _scene(i: int, narration: str = "문제는 물이었습니다. 바다가 도시를 밀어냅니다.") -> dict:
    return {"index": i, "narration": narration,
            "shots": [{"shot": s, "role": f"컷 {s}", "clean_prompt": f"Scene {i} shot {s} concrete seawall. {NEG}",
                       "info_prompt": "Add teal flow arrows anchored to the gate." if s == "B" else ""}
                      for s in "ABC"],
            "video_prompt": "GLOBAL CONTINUITY ... Maintain exact structural continuity across all shots. NEGATIVE ..."}


def _plan(n: int = 12) -> dict:
    return {"topic": "방조제", "angle": "왜 막지 않고 흘려보낼까?", "factcheck": ["사실"],
            "titles": ["a", "b", "c"], "visual_bible": "grey concrete, teal water",
            "scenes": [_scene(i) for i in range(1, n + 1)],
            "sources": [{"url": "https://example.org/1", "supports": "수치"},
                        {"url": "https://example.org/2", "supports": "원인"}]}


class PlanTests(unittest.TestCase):
    def test_valid_plan_has_no_errors(self):
        errors, _ = fs.check_plan(fs.FlowPlan.model_validate(_plan()))
        self.assertEqual(errors, [])

    def test_errors_for_shots_negative_continuity_and_index(self):
        data = _plan(2)
        data["scenes"][0]["shots"] = data["scenes"][0]["shots"][:2]
        data["scenes"][1]["shots"][0]["clean_prompt"] = "a seawall, 9:16"
        data["scenes"][1]["video_prompt"] = "no lock"
        data["scenes"][1]["index"] = 5
        errors, warnings = fs.check_plan(fs.FlowPlan.model_validate(data))
        text = "\n".join(errors)
        self.assertIn("A·B·C", text)
        self.assertIn("네거티브 누락", text)
        self.assertIn("structural continuity", text)
        self.assertIn("index", text)
        self.assertTrue(any("장면 2개" in w for w in warnings))

    def test_prompts_markdown_marks_clean_only_shots(self):
        md = fs.prompts_markdown(fs.FlowPlan.model_validate(_plan(1)))
        self.assertIn("📊 INFO 편집(Flow·Nano Banana 2): [Scene 1 / Shot B", md)
        self.assertIn("Shot A: INFO 사용 안 함 — CLEAN 유지", md)
        self.assertIn("🎬 영상(Flow·Gemini Omni Flash): [Scene 1 | 8s | 3 Shots]", md)
        self.assertIn("https://example.org/2", md)

    def test_scene_lengths(self):
        self.assertEqual(fs.scene_lengths([4.0, 7.9, 9.0], [8.0, 8.0, 8.0]), [6.0, 8.25, 9.35])
        self.assertEqual(fs.scene_lengths([9.3], [10.0]), [9.65])

    def test_clip_seconds_sets_narration_limit(self):
        data = _plan(1)
        data["scenes"][0]["narration"] = "가" * 45
        self.assertTrue(any("45글자" in w for w in fs.check_plan(fs.FlowPlan.model_validate(data))[1]))
        data["clip_seconds"] = 10
        plan = fs.FlowPlan.model_validate(data)
        self.assertFalse(any("45글자" in w for w in fs.check_plan(plan)[1]))
        self.assertIn("| 10s | 3 Shots]", fs.prompts_markdown(plan))


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.job = Path(self.tmp.name) / "job"
        fs.save_plan(self.job, fs.FlowPlan.model_validate(_plan(3)))
        self.dl = Path(self.tmp.name) / "dl"
        self.dl.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _video(self, name: str, age: float) -> Path:
        p = self.dl / name
        p.write_bytes(b"x")
        t = time.time() - age
        os.utime(p, (t, t))
        return p

    def test_from_dir_fills_missing_scenes_oldest_first(self):
        self._video("old.mp4", 7200)
        self._video("first.mp4", 30)
        self._video("second.mp4", 20)
        self._video("partial.mp4.crdownload", 10)
        res = fs.import_clips(self.job, from_dir=self.dl, since=time.time() - 600)
        self.assertEqual([(p["scene"], Path(p["file"]).name) for p in res["placed"]],
                         [(1, "first.mp4"), (2, "second.mp4")])
        self.assertEqual(res["missing"], [3])
        # 같은 파일은 다시 가져오지 않는다
        self._video("third.mp4", 5)
        res = fs.import_clips(self.job, from_dir=self.dl, since=time.time() - 600)
        self.assertEqual([(p["scene"], Path(p["file"]).name) for p in res["placed"]], [(3, "third.mp4")])
        self.assertTrue(res["ready"])

    def test_single_file_and_bad_scene(self):
        f = self._video("x.mp4", 1)
        res = fs.import_clips(self.job, scene=2, file=f)
        self.assertEqual(res["have"], [2])
        with self.assertRaises(fs.FlowError):
            fs.import_clips(self.job, scene=9, file=f)


class AssembleTests(unittest.TestCase):
    def test_assemble_aligns_words_and_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp)
            fs.save_plan(job, fs.FlowPlan.model_validate(_plan(2)))
            (job / "clips").mkdir()
            for i in (1, 2):
                fs.clip_path(job, i).write_bytes(b"x")
            cfg = {"tts": {"provider": "edge", "voice": "v", "retries": 0}, "subtitles": {},
                   "video": {"width": 1080, "height": 1920, "fps": 30},
                   "paths": {"assets": str(job)}}
            words = [Word(text="문제는", start=0.0, end=0.5)]
            built = {}

            def fake_ass(per_scene, out, *a, **k):
                built["words"] = per_scene
                return out

            from app.pipeline import run as runmod
            with patch.object(runmod, "_synthesize_one", new=AsyncMock(side_effect=[(words, 4.0), (words, 7.9)])), \
                 patch("app.pipeline.tts.get_tts", return_value=object()), \
                 patch.object(fs, "probe_duration", new=AsyncMock(return_value=8.0)), \
                 patch.object(fs, "has_audio", new=AsyncMock(return_value=True)), \
                 patch.object(fs, "run_ffmpeg", new=AsyncMock()), \
                 patch("app.pipeline.subtitles.build_ass", side_effect=fake_ass), \
                 patch("app.pipeline.render.render_broll", new=AsyncMock()) as rb:
                res = asyncio.run(fs.assemble(job, cfg))
            clips = rb.call_args.args[0]
            self.assertEqual([c["duration"] for c in clips], [6.0, 8.25])
            self.assertEqual(built["words"][1][0].start, 6.0)   # 둘째 장면 단어는 장면 시작만큼 밀린다
            self.assertEqual(res["scenes"][1]["seconds"], 8.25)
            self.assertIn("[출처]", (job / "meta.txt").read_text(encoding="utf-8"))

    def test_assemble_refuses_missing_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp)
            fs.save_plan(job, fs.FlowPlan.model_validate(_plan(2)))
            with self.assertRaises(fs.FlowError):
                asyncio.run(fs.assemble(job, {}))


class FactoryFlowTests(unittest.TestCase):
    def test_new_status_prompts_and_invalid_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            plan_file = Path(tmp) / "plan.json"
            plan_file.write_text(json.dumps(_plan(), ensure_ascii=False), encoding="utf-8")
            with patch.object(flow, "_output", return_value=out):
                res = flow.new(str(plan_file))
                self.assertEqual(res["scenes"], 12)
                self.assertEqual(res["next_scene"], 1)
                self.assertTrue(Path(res["prompts_file"]).is_file())
                pr = flow.prompts(None, 3)
                self.assertIsNone(pr["shots"][0]["info_prompt"])
                self.assertTrue(pr["shots"][1]["info_prompt"])
                self.assertEqual(flow.note(None, "https://flow.google.com/project/x")["flow_url"],
                                 "https://flow.google.com/project/x")
                bad = _plan()
                bad["scenes"][0]["video_prompt"] = "x"
                plan_file.write_text(json.dumps(bad), encoding="utf-8")
                with self.assertRaises(core.FactoryError) as ctx:
                    flow.new(str(plan_file))
                self.assertTrue(ctx.exception.extra["errors"])
                with self.assertRaises(core.FactoryError) as ctx:
                    asyncio.run(flow.assemble(None, 0.12, True))
                self.assertEqual(ctx.exception.code, "not_ready")


if __name__ == "__main__":
    unittest.main()
