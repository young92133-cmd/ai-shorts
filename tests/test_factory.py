"""콘텐츠팩토리(app.factory): Claude Code / Codex 가 부르는 명령층.

새 엔진이 아니라 app/pipeline 을 그대로 부르는지, 상태 파일과 JSON 결과가 맞는지 확인한다.
AI·TTS·렌더는 가짜로 바꿔 네트워크·유료 호출 없이 돈다.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.factory import __main__ as cli, core, state as st
from app.pipeline import blueprint, run, timeline
from app.pipeline.models import ResearchDoc, Scene, Script

from tests.test_tts_timeline import FakeTTS, fake_concat, fake_probe, no_trim

NARR = ["고양이는 왜 좁은 상자에 들어갈까요?", "상자 안은 사방이 막혀 있어 안전하다고 느낍니다.",
        "야생에서 숨을 곳은 곧 생존이었습니다.", "좁은 곳은 체온 유지에도 유리합니다.",
        "그래서 새 상자를 보면 먼저 들어가 봅니다."]


def cat_script() -> Script:
    return Script(topic="고양이가 상자를 좋아하는 이유", titles=["고양이와 상자"], description="d", hashtags=["고양이"],
                  sources=[], scenes=[Scene(narration=n, image_prompt="cat", on_screen_text="") for n in NARR])


async def fake_render(tl, job_dir, out, fonts=None):
    Path(out).write_bytes(b"MP4")
    return Path(out)


async def fake_video_probe(path):
    return {"streams": [{"width": 1080, "height": 1920}], "format": {"duration": "21.4"}}


class FactoryTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.stack = ExitStack()
        self.research = AsyncMock(return_value=[ResearchDoc(title="고양이 습성", url="https://example.com/cat", text="상자")])
        self.write_script = AsyncMock(side_effect=lambda *a, **k: cat_script())
        self.fetch_articles = AsyncMock(return_value=([ResearchDoc(title="고양이 기사", url="https://news.example/1", text="본문")], []))
        orig_cfg = core._run_cfg

        def quiet_cfg(request):
            cfg = orig_cfg(request)
            cfg["tts"]["retry_wait"] = 0
            cfg["images"]["provider"] = "none"
            return cfg
        for p in [patch.object(core, "output_root", return_value=self.root),
                  patch.object(core, "_run_cfg", side_effect=quiet_cfg),
                  patch.object(core, "require_ffmpeg"), patch.object(core, "probe_video", new=fake_video_probe),
                  patch.object(run, "require_ffmpeg"), patch.object(run, "get_tts", return_value=FakeTTS()),
                  patch.object(run, "probe_duration", new=fake_probe), patch.object(run, "concat_audio", new=fake_concat),
                  patch.object(run, "trim_edge_silence", new=no_trim),
                  patch.object(run.timelinemod, "render_timeline", new=fake_render),
                  patch.object(run, "make_thumbnail", new=AsyncMock()),
                  patch.object(run.research, "research_topic", new=self.research),
                  patch.object(run.articlemod, "fetch_articles", new=self.fetch_articles),
                  patch.object(run.scriptmod, "make_plan", new=AsyncMock(side_effect=RuntimeError("테스트: 구성 AI 없음"))),
                  patch.object(run.scriptmod, "write_script", new=self.write_script),
                  patch.object(run.script_split, "ask_structured", new=AsyncMock(side_effect=RuntimeError("테스트: AI 없음"))),
                  # make 기본값은 benchmark=auto. 구조 분석 AI 도 가짜로 막아 안전한 정보형 구조로 진행한다.
                  patch.object(run.bench_auto, "ask_structured", new=AsyncMock(side_effect=RuntimeError("테스트: AI 없음")))]:
            self.stack.enter_context(p)

    def tearDown(self):
        self.stack.close()
        self._tmp.cleanup()


def _quiet(msg: str) -> None:
    pass


class MakeTests(FactoryTestCase):
    async def test_topic_make_runs_to_final_video(self):
        out = await core.make(topic="고양이가 상자를 좋아하는 이유", seconds=45, log=_quiet)
        self.assertEqual(out["status"], "render_complete")
        self.assertEqual(out["next_action"], "done")
        self.assertEqual(out["resolution"], "1080x1920")
        job = Path(out["project_dir"])
        self.assertTrue(Path(out["final_video"]).is_file())
        state = st.load(job)
        seen = [h["status"] for h in state["history"]]
        for s in ("research_complete", "script_ready", "blueprint_complete", "tts_complete", "visuals_complete",
                  "render_complete"):
            self.assertIn(s, seen)
        self.assertEqual(state["request"]["seconds"], 45)
        self.assertEqual(blueprint.load(job).timing, "tts_aligned")          # 2C 그대로
        self.assertTrue(all(s.visual_decision for s in blueprint.load(job).scenes))   # 2D 그대로
        self.assertTrue((job / "sources.json").is_file())                    # 권리 대장 그대로
        web = json.loads((job / "job.json").read_text(encoding="utf-8"))
        self.assertEqual(web["status"], "done")                              # 웹 UI 목록에도 보인다
        self.assertTrue(web["result"]["video"].endswith("final.mp4"))

    async def test_url_make_uses_article_path(self):
        out = await core.make(url="https://news.example/1", log=_quiet)
        self.assertEqual(out["status"], "render_complete")
        self.fetch_articles.assert_awaited()
        self.assertEqual(st.load(Path(out["project_dir"]))["request"]["mode"], "url")

    async def test_factory_reuses_pipeline_engine(self):
        with patch.object(core.runmod, "run_pipeline", wraps=run.run_pipeline) as engine:
            await core.make(topic="고양이", log=_quiet)
        engine.assert_awaited_once()
        self.assertEqual(engine.await_args.args[1], "topic")

    async def test_only_one_input_allowed(self):
        with self.assertRaises(core.FactoryError):
            await core.make(topic="a", url="https://x", log=_quiet)
        with self.assertRaises(core.FactoryError):
            await core.make(log=_quiet)


class ReviewResumeTests(FactoryTestCase):
    async def test_stop_at_script_then_resume_without_new_research(self):
        out = await core.make(topic="고양이가 상자를 좋아하는 이유", seconds=45, review=True, log=_quiet)
        self.assertEqual(out["status"], "waiting_for_script_approval")
        self.assertEqual(out["next_action"], "resume")
        self.assertTrue(out["script_path"].endswith("script.json"))
        self.assertEqual([s["narration"] for s in out["scenes"]], NARR)       # 대본을 바로 보여줄 수 있다
        job = Path(out["project_dir"])
        self.assertFalse((job / "final.mp4").exists())
        self.assertFalse((job / "narration.mp3").exists())                   # 음성도 아직 안 만든다
        before = json.loads((job / "script.json").read_text(encoding="utf-8"))
        self.research.reset_mock()
        self.write_script.reset_mock()

        done = await core.resume(out["project_id"], log=_quiet)
        self.assertEqual(done["status"], "render_complete")
        self.research.assert_not_awaited()                                   # 조사 다시 안 함
        self.write_script.assert_not_awaited()                               # 대본 다시 안 씀
        after = json.loads((job / "script.json").read_text(encoding="utf-8"))
        self.assertEqual([s["narration"] for s in after["scenes"]], [s["narration"] for s in before["scenes"]])
        seen = [h["status"] for h in st.load(job)["history"]]
        self.assertLess(seen.index("waiting_for_script_approval"), seen.index("script_approved"))
        self.assertLess(seen.index("script_approved"), seen.index("render_complete"))

    async def test_edit_scene_before_resume_is_used(self):
        out = await core.make(topic="고양이", review=True, log=_quiet)
        edited = core.edit_scene(out["project_id"], 2, narration="상자 안은 포근하고 안전하게 느껴집니다.")
        self.assertEqual(edited["scenes"][1]["narration"], "상자 안은 포근하고 안전하게 느껴집니다.")
        await core.resume(out["project_id"], log=_quiet)
        bp = blueprint.load(Path(out["project_dir"]))
        self.assertEqual(bp.scenes[1].narration, "상자 안은 포근하고 안전하게 느껴집니다.")
        with self.assertRaises(core.FactoryError):                           # 렌더 후에는 대본 수정 불가
            core.edit_scene(out["project_id"], 2, narration="x")

    async def test_resume_rejects_finished_or_scriptless_projects(self):
        out = await core.make(topic="고양이", log=_quiet)
        with self.assertRaises(core.FactoryError) as e:
            await core.resume(out["project_id"], log=_quiet)
        self.assertEqual(e.exception.code, "not_ready")


class FailureTests(FactoryTestCase):
    async def test_failure_is_saved_and_resume_continues(self):
        with patch.object(run, "get_tts", return_value=FakeTTS(fail_times=99)):
            out = await core.make(topic="고양이", log=_quiet)
        self.assertEqual(out["status"], "failed")
        self.assertIn("TTSFailed", out["message"])
        self.assertEqual(out["failed_at"], "blueprint_complete")
        self.assertEqual(out["next_action"], "resume")                       # 대본이 있으니 이어서 가능
        state = st.load(Path(out["project_dir"]))
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["error"])
        self.research.reset_mock()
        done = await core.resume(out["project_id"], log=_quiet)
        self.assertEqual(done["status"], "render_complete")
        self.research.assert_not_awaited()

    async def test_failure_before_script_suggests_make(self):
        self.research.side_effect = RuntimeError("검색 실패")
        out = await core.make(topic="고양이", log=_quiet)
        self.assertEqual(out["status"], "failed")
        self.assertEqual(out["next_action"], "make")
        with self.assertRaises(core.FactoryError):
            await core.resume(out["project_id"], log=_quiet)

    async def test_invalid_project_id(self):
        for bad in ("없는프로젝트", "../etc", "nope_1234"):
            with self.assertRaises(core.FactoryError) as e:
                core.status(bad)
            self.assertIn(e.exception.code, ("invalid", "not_found"))


class InspectTests(FactoryTestCase):
    async def test_status_inspect_and_latest_default(self):
        out = await core.make(topic="고양이", log=_quiet)
        s = core.status()                                                    # id 없으면 최근 프로젝트
        self.assertEqual(s["project_id"], out["project_id"])
        self.assertEqual(s["status"], "render_complete")
        self.assertEqual(s["resolution"], "1080x1920")
        self.assertTrue(s["recent_projects"])
        info = core.inspect(out["project_id"])
        self.assertEqual(len(info["script"]["scenes"]), len(info["scenes"]))
        first = info["scenes"][0]
        for key in ("narration", "start", "end", "actual_tts", "visual", "rights", "reason"):
            self.assertIn(key, first)
        self.assertIn("final.mp4", info["files"])
        self.assertNotIn("visual", core.inspect(out["project_id"], "scenes")["scenes"][0])

    async def test_rerender_keeps_timing_and_updates_state(self):
        out = await core.make(topic="고양이", log=_quiet)
        job = Path(out["project_dir"])
        tl_before = timeline.load(job)
        again = await core.rerender(out["project_id"], log=_quiet)
        self.assertTrue(again["rerendered"])
        self.assertEqual(again["status"], "render_complete")
        self.assertEqual(timeline.load(job)["scenes"], tl_before["scenes"])
        self.research.assert_awaited_once()                                  # 다시 조사하지 않음

    async def test_set_visual_card_after_render(self):
        out = await core.make(topic="고양이", log=_quiet)
        again = await core.set_visual(out["project_id"], 3, card="number_card", log=_quiet)
        self.assertEqual(again["changed_scene"], 3)
        bp = blueprint.load(Path(out["project_dir"]))
        self.assertEqual(bp.scenes[2].visual_decision.resolved_visual_type, "number_card")
        self.assertEqual(timeline.load(Path(out["project_dir"]))["scenes"][2]["title"], "")

    async def test_set_visual_file_requires_rights(self):
        out = await core.make(topic="고양이", review=True, log=_quiet)
        img = self.root / "my_cat.jpg"
        Image.new("RGB", (800, 600), "orange").save(img)
        with self.assertRaises(core.FactoryError) as e:                      # 권리 확인 없으면 거부
            await core.set_visual(out["project_id"], 2, file=str(img), log=_quiet)
        self.assertEqual(e.exception.code, "rights")
        await core.set_visual(out["project_id"], 2, file=str(img), note="내가 찍은 사진", confirm_rights=True,
                              log=_quiet)
        await core.resume(out["project_id"], log=_quiet)
        bp = blueprint.load(Path(out["project_dir"]))
        self.assertEqual(bp.scenes[1].visual_decision.asset_source, "user_upload")


class CliJsonTests(unittest.TestCase):
    """stdout 은 JSON 한 덩어리, 종료 코드로 성공/오류를 구분한다."""

    def _cli(self, *argv: str) -> tuple[int, dict]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, json.loads(out.getvalue())

    def test_invalid_id_json(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(core, "output_root", return_value=Path(folder)):
            code, data = self._cli("status", "nope_1234")
        self.assertEqual(code, 2)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "not_found")

    def test_styles_json(self):
        code, data = self._cli("styles")
        self.assertEqual(code, 0)
        self.assertTrue(any(p["id"] == "daily" for p in data["presets"]))

    def test_make_json_shape(self):
        fake = {"status": "waiting_for_script_approval", "project_id": "p1", "script_path": "x/script.json",
                "next_action": "resume", "message": "m"}
        with patch.object(core, "make", new=AsyncMock(return_value=fake)) as make:
            code, data = self._cli("make", "--topic", "고양이", "--seconds", "45", "--review")
        self.assertEqual(code, 0)
        self.assertEqual(data, fake)
        self.assertEqual(make.await_args.kwargs["seconds"], 45)
        self.assertTrue(make.await_args.kwargs["review"])

    def test_failed_make_exit_code(self):
        with patch.object(core, "make", new=AsyncMock(return_value={"status": "failed", "next_action": "resume"})):
            code, data = self._cli("make", "--topic", "x")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
