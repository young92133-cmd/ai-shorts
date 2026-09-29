"""2B: 완성 대본을 원문 그대로 보존해 4~8개 장면과 설계도로 만든다."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app import main
from app.config import load_config, load_presets, merge_options
from app.jobs import Job, JobManager
from app.pipeline import blueprint, run, script_split
from app.pipeline.models import PlannedScript
from app.pipeline.script_split import SplitPlan, SplitScene


SHORT = ("건물은 왜 바람에 쉽게 무너지지 않을까요? "
         "기둥 하나보다 힘을 나누는 구조가 중요합니다. "
         "바람의 힘은 기둥과 바닥을 따라 땅으로 전달됩니다. "
         "그래서 좋은 설계는 연결부부터 꼼꼼히 살핍니다.")
LONG = " ".join([
    "엘리베이터가 갑자기 멈춰도 안전장치는 준비되어 있습니다.",
    "케이블이 끊어지면 바로 추락한다고 생각하기 쉽습니다.",
    "하지만 실제 구조는 여러 부품이 힘을 나누도록 설계합니다.",
    "첫째로 여러 가닥의 케이블이 하중을 분담합니다.",
    "한 가닥만으로 전체를 지탱하도록 두지 않습니다.",
    "둘째로 속도가 지나치게 빨라지면 조속기가 반응합니다.",
    "조속기는 안전장치를 움직여 레일을 붙잡게 합니다.",
    "셋째로 아래쪽 완충장치가 남은 충격을 줄입니다.",
    "각 장치는 서로 다른 상황에 대비하는 역할을 합니다.",
    "정기 점검에서는 이 부품들이 제대로 움직이는지 확인합니다.",
    "그래서 하나의 부품만 보고 안전을 단정할 수 없습니다.",
    "안전은 여러 단계가 함께 작동할 때 완성됩니다.",
])
ECON = " ".join([
    "매출이 12퍼센트 늘었다는 발표, 이익도 늘었을까요?",
    "지난 분기 매출은 100억 원에서 112억 원으로 증가했습니다.",
    "그러나 영업이익은 18억 원에서 14억 원으로 줄었습니다.",
    "원가가 더 빠르게 늘었기 때문입니다.",
    "원가율이 72퍼센트에서 78퍼센트로 바뀌었습니다.",
    "매출 증가율만 보면 놓치는 부분이 있습니다.",
    "현금 흐름과 비용 변화도 함께 확인해야 합니다.",
    "이 숫자는 테스트용 가상 수치입니다.",
])


def plan_for(text: str) -> SplitPlan:
    units = script_split.sentences(text)
    groups = script_split._groups(units)
    return SplitPlan(scenes=[SplitScene(
        sentence_ids=ids, scene_type="Hook" if i == 0 else "결론" if i == len(groups) - 1 else "핵심 정보",
        visual_type="chart" if text == ECON and i == 2 else "generated_image",
        visual_description=f"내부 생성 설명 화면 {i + 1}", emphasis_text=f"핵심 {i + 1}",
        motion="zoom_in", transition="cut" if i == 0 else "fade",
        source_requirement="internal_generated", notes="") for i, ids in enumerate(groups)])


class SplitTests(unittest.IsolatedAsyncioTestCase):
    async def _check(self, text: str) -> None:
        with patch.object(script_split, "ask_structured", new=AsyncMock(return_value=plan_for(text))):
            script, method = await script_split.split_finished_script({"provider": "test"}, text)
        self.assertEqual(method, "ai")
        self.assertTrue(4 <= len(script.scenes) <= 8)
        self.assertEqual(script.full_narration(), text)
        self.assertEqual(script.scenes[0].scene_type, "Hook")
        self.assertEqual(script.scenes[-1].scene_type, "결론")
        bp = blueprint.from_script(script)
        self.assertEqual(len(bp.scenes), len(script.scenes))
        self.assertEqual(bp.scenes[0].scene_id, "scene_01")
        self.assertEqual(bp.scenes[0].subtitle, bp.scenes[0].narration)

    async def test_short_twenty_to_thirty_seconds(self):
        await self._check(SHORT)

    async def test_long_about_sixty_seconds(self):
        await self._check(LONG)

    async def test_economic_script_preserves_numbers_and_chart_plan(self):
        await self._check(ECON)
        with patch.object(script_split, "ask_structured", new=AsyncMock(return_value=plan_for(ECON))):
            script, _ = await script_split.split_finished_script({}, ECON)
        self.assertEqual(blueprint.from_script(script).scenes[2].visual_type, "chart")

    async def test_bad_ai_response_uses_sentence_boundary_fallback(self):
        bad = SplitPlan(scenes=[plan_for(SHORT).scenes[0]])
        with patch.object(script_split, "ask_structured", new=AsyncMock(return_value=bad)):
            script, method = await script_split.split_finished_script({}, SHORT)
        self.assertEqual(method, "fallback")
        self.assertEqual(script.full_narration(), SHORT)
        self.assertEqual(len(script.scenes), 4)
        self.assertEqual(script.scenes[0].visual_type, "text_card")

    async def test_api_exception_uses_fallback(self):
        with patch.object(script_split, "ask_structured", new=AsyncMock(side_effect=RuntimeError("API unavailable"))):
            script, method = await script_split.split_finished_script({}, ECON)
        self.assertEqual(method, "fallback")
        self.assertEqual(script.full_narration(), ECON)

    async def test_pipeline_writes_preview_before_review(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            cfg = merge_options(load_config(), load_presets(load_config())["engineering"], {})
            async def review(script, preview):
                self.assertTrue((job / "blueprint.json").is_file())
                self.assertEqual(len(preview["blueprint"]["scenes"]), 4)
                self.assertEqual(preview["blueprint"]["scenes"][0]["scene_type"], "Hook")
                return script, {}
            with (patch.object(run, "require_ffmpeg"),
                  patch.object(script_split, "ask_structured", new=AsyncMock(return_value=plan_for(SHORT)))):
                result = await run.run_pipeline(job, "script", SHORT, cfg, review=review, until="script")
            self.assertEqual(result["split_method"], "ai")
            self.assertEqual(blueprint.load(job).scenes[-1].scene_type, "결론")
            self.assertTrue((job / "script.json").is_file())

    async def test_too_short_script_has_clear_message(self):
        with self.assertRaisesRegex(ValueError, "최소 4문장"):
            await script_split.split_finished_script({}, "한 문장뿐입니다.")

    async def test_script_job_api_accepts_direct_input_without_api_key(self):
        class FakeManager:
            cfg = {"llm": {"provider": "openai"}}
            def create(self, mode, input_text, preset, options):
                return Job(id="demo", mode=mode, input=input_text, preset=preset, options=options)
        with patch.object(main, "manager", FakeManager(), create=True):
            job = await main.create_job(main.CreateJob(mode="script", input=SHORT, preset="engineering",
                                                        options={"review": False}))
        self.assertEqual(job["mode"], "script")
        self.assertEqual(job["input"], SHORT)
        with patch.object(main, "manager", FakeManager(), create=True):
            with self.assertRaises(HTTPException) as cm:
                await main.create_job(main.CreateJob(mode="script", input=" ", preset="engineering"))
        self.assertEqual(cm.exception.status_code, 400)

    async def test_approved_edit_keeps_planning_fields_and_updates_subtitle(self):
        with patch.object(script_split, "ask_structured", new=AsyncMock(return_value=plan_for(SHORT))):
            planned, _ = await script_split.split_finished_script({}, SHORT)
        job = Job(id="demo", mode="script", input=SHORT, preset="engineering", options={},
                  status="awaiting_review", script=planned.model_dump())
        manager = object.__new__(JobManager)
        manager.jobs = {"demo": job}
        edit = planned.model_dump()
        edit["scenes"][0]["narration"] = "수정한 훅입니다."
        manager.approve("demo", edit)
        saved = PlannedScript.model_validate(job.script)
        self.assertEqual(saved.scenes[0].subtitle, "수정한 훅입니다.")
        self.assertEqual(saved.scenes[0].scene_type, "Hook")


if __name__ == "__main__":
    unittest.main()
