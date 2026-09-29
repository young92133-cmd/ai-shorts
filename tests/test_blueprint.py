"""자동 제작 MVP 2A: 기존 대본을 장면 설계도로 기록한다."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app import main
from app.config import load_config, load_presets, merge_options
from app.pipeline import blueprint, run
from app.pipeline.models import Scene, Script


def sample_script(count: int = 4) -> Script:
    return Script(topic="콘크리트 구조", scenes=[Scene(
        narration=f"{i + 1}번째 장면입니다. 안전한 구조를 차근차근 설명합니다.",
        image_prompt="clean architectural diagram, no text" if i % 2 == 0 else "",
        on_screen_text=f"핵심 {i + 1}") for i in range(count)],
        titles=["구조 이야기"], description="구조 설명", hashtags=["건축"], sources=[])


class BlueprintTests(unittest.TestCase):
    def test_scene_fields_and_estimated_timing(self):
        bp = blueprint.from_script(sample_script(), gap=0.25)
        self.assertEqual((bp.width, bp.height, bp.fps, bp.timing), (1080, 1920, 30, "estimated"))
        self.assertEqual(len(bp.scenes), 4)
        self.assertEqual(bp.scenes[0].start, 0.0)
        self.assertEqual(bp.scenes[0].transition, "cut")
        self.assertEqual(bp.scenes[1].transition, "fade")
        self.assertEqual(bp.scenes[1].motion, "zoom_out")
        self.assertEqual(bp.scenes[1].visual_type, "card")
        self.assertEqual(bp.scenes[2].visual_type, "image")
        self.assertEqual(bp.scenes[2].subtitle, bp.scenes[2].narration)
        self.assertEqual(bp.scenes[3].end, bp.estimated_duration)
        for prev, cur in zip(bp.scenes, bp.scenes[1:]):
            self.assertEqual(prev.end, cur.start)
            self.assertAlmostEqual(cur.end - cur.start, cur.duration, places=3)

    def test_existing_ten_scene_script_remains_supported(self):
        self.assertEqual(len(blueprint.from_script(sample_script(10)).scenes), 10)

    def test_empty_narration_explains_error(self):
        script = sample_script()
        script.scenes[2].narration = " "
        with self.assertRaisesRegex(ValueError, "3번 장면"):
            blueprint.from_script(script)

    def test_atomic_save_and_load(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            source = blueprint.from_script(sample_script())
            blueprint.save(job, source)
            self.assertEqual(blueprint.load(job), source)
            self.assertFalse((job / "blueprint.json.tmp").exists())


class BlueprintPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_script_pipeline_writes_blueprint(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            cfg = load_config()
            cfg = merge_options(cfg, load_presets(cfg)["engineering"], {})
            script = sample_script()
            with (patch.object(run, "require_ffmpeg"),
                  patch.object(run.research, "research_topic", new=AsyncMock(return_value=[])),
                  patch.object(run.scriptmod, "write_script", new=AsyncMock(return_value=script))):
                result = await run.run_pipeline(job, "topic", "콘크리트 구조", cfg,
                                                 style={"name": "test"}, until="script")
            self.assertTrue((job / "blueprint.json").is_file())
            self.assertEqual(result["blueprint"]["scenes"][0]["emphasis_text"], "핵심 1")
            self.assertTrue((job / "sources.json").is_file())

    async def test_blueprint_api_returns_saved_data(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            fake = SimpleNamespace(get=lambda _: object(), job_dir=lambda _: job)
            with patch.object(main, "manager", fake, create=True):
                with self.assertRaises(HTTPException) as cm:
                    await main.get_blueprint("demo")
                self.assertEqual(cm.exception.status_code, 409)
                blueprint.save(job, blueprint.from_script(sample_script()))
                result = await main.get_blueprint("demo")
            self.assertEqual(len(result["scenes"]), 4)


if __name__ == "__main__":
    unittest.main()
