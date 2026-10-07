"""transformative_quote: 분석·비평·비교·해설용 인용 모드.

AI·조사·TTS·렌더·클립 분석은 가짜. 비교 레이아웃 합성과 정지 화면 렌더만 실제 Pillow/ffmpeg 로 확인한다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.factory import core, state as st
from app.pipeline import bench_auto, clip_analyzer, quote as quotemod, run, source_resolver as sr, timeline
from app.pipeline.models import PlannedScript
from app.pipeline.sources import SourceRegistry

from tests.test_benchmark_auto import INTEG, make_brief
from tests.test_factory import FactoryTestCase, cat_script

URL = "https://www.youtube.com/watch?v=stagecam01"


def planned(roles: list[str]) -> PlannedScript:
    data = cat_script().model_dump()
    for i, scene in enumerate(data["scenes"]):
        scene["beat_role"] = roles[i]
    return PlannedScript.model_validate(data)


def kpop_spec() -> dict:
    return INTEG["profiles"]["kpop_observation_clip"]


def add_quote(reg: SourceRegistry, path: Path, kind: str = "video", **kw) -> None:
    reg.add(kind=kind, origin="upload", path=str(path), title=path.name,
            rights=quotemod.quote_rights(title=kw.get("title", "무대 직캠"), channel=kw.get("channel", "참고 채널"),
                                         url=kw.get("url", URL)))


def fake_analysis(path, need, **kw):
    start = 10.0 + 20 * len(kw.get("avoid") or [])
    rec = clip_analyzer.ClipCandidate(start=start, end=start + need, score=80, reason="한 샷 안")
    return clip_analyzer.ClipAnalysis(path=str(path), duration=120.0, candidates=[rec], recommended=rec)


class PolicyTests(unittest.TestCase):
    def test_unlicensed_source_becomes_transformative_quote(self):
        for code in ("", "by-nc", "by-nd", "by-sa", "all rights reserved"):
            r = sr.classify_license(code)
            self.assertEqual(r.status, "transformative_quote", code)   # 자동 reference_only 아님
        self.assertEqual(sr.classify_license("cc0", restrictions="personality").status, "reference_only")
        with tempfile.TemporaryDirectory() as d:
            reg = SourceRegistry(Path(d))
            f = Path(d) / "cam.mp4"
            add_quote(reg, f)
            item = reg.by_path(f)
            self.assertTrue(item.usable_in_video)
            self.assertEqual(item.rights_status, "transformative_quote")
            self.assertEqual(item.attribution, {"title": "무대 직캠", "channel": "참고 채널", "url": URL})
            self.assertTrue(item.credit.startswith("인용:"))
            self.assertEqual(item.media_status, "local_file")

    def test_quote_without_attribution_is_not_usable(self):
        with tempfile.TemporaryDirectory() as d:
            reg = SourceRegistry(Path(d))
            f = Path(d) / "x.jpg"
            reg.add(kind="image", origin="upload", path=str(f), rights=quotemod.quote_rights())
            self.assertFalse(reg.by_path(f).usable_in_video)

    def test_unlicensed_candidate_is_chosen_only_for_evidence_scenes(self):
        q = sr.VisualCandidate(id="q", provider="openverse", media_type="image", title="stage", width=1080, height=1920,
                               rights=sr.classify_license("by-nc"))
        fit = {"q": sr.FitScore(candidate_id="q", visual_fit=9, evidence_fit=8, reason="장면 근거")}
        scores = {"q": sr.score_candidate(q, fit["q"], 4)}
        queries = {1: sr.SceneQuery(scene_index=1, query_en="stage", prefer="image", must_show="")}
        picked = sr.choose({1: [q]}, scores, fit, queries, ["image"], min_score=40, min_visual_fit=7,
                           strategy=sr.EVIDENCE_STRATEGY, quote_scenes={1})
        self.assertEqual(picked[1].id, "q")
        self.assertEqual(sr.choose({1: [q]}, scores, fit, queries, ["image"], min_score=40, min_visual_fit=7,
                                   strategy=sr.EVIDENCE_STRATEGY, quote_scenes=set()), {})
        weak = {"q": sr.FitScore(candidate_id="q", visual_fit=9, evidence_fit=4, reason="분위기만")}
        self.assertEqual(sr.choose({1: [q]}, scores, weak, queries, ["image"], min_score=40, min_visual_fit=7,
                                   strategy=sr.EVIDENCE_STRATEGY, quote_scenes={1}), {})

    def test_enrich_attribution_from_url_analysis(self):
        with tempfile.TemporaryDirectory() as d:
            reg = SourceRegistry(Path(d))
            f = Path(d) / "cam.mp4"
            reg.add(kind="video", origin="upload", path=str(f), rights=quotemod.quote_rights(title="cam", url=URL))
            quotemod.enrich_attribution(reg, URL, {"title": "쇼케이스 무대", "channel": "공식 채널"})
            item = reg.by_path(f)
            self.assertEqual((item.attribution["title"], item.attribution["channel"]), ("쇼케이스 무대", "공식 채널"))
            self.assertIn("공식 채널", item.credit)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self.reg = SourceRegistry(self.d)
        self.cam = self.d / "cam.mp4"
        add_quote(self.reg, self.cam)
        self.script = planned(["reason_to_watch", "first_evidence", "comparison_or_interpretation",
                               "comparison_or_interpretation", "payoff_or_question"])
        self.decision = {"viewer_question": "같은 안무인데 느낌이 왜 다를까?"}

    def tearDown(self):
        self._tmp.cleanup()

    def entry(self, start, play, src_dur=200.0):
        credit = self.reg.by_path(self.cam).credit
        return {"kind": "video", "path": str(self.cam), "start": start, "end": start + play, "play": play,
                "source_duration": src_dur, "credit": credit, "quote": True, "asset_source": "quote_source"}

    def test_commentary_is_required(self):
        self.script.scenes[1].narration = "와"
        out, rep = quotemod.guard({1: self.entry(10, 2)}, self.script, [4.0] * 5, self.decision, self.reg, kpop_spec())
        self.assertNotIn(1, out)
        self.assertTrue(any("해설" in a for a in rep["actions"]))

    def test_long_unmodified_reuse_is_reduced(self):
        entries = {1: self.entry(10, 4.0), 2: self.entry(40, 4.0), 3: self.entry(70, 4.0)}
        out, rep = quotemod.guard(entries, self.script, [4.0] * 5, self.decision, self.reg, kpop_spec())
        for i in (1, 2, 3):
            self.assertLessEqual(out[i]["play"], 4.0 * quotemod.SCENE_MOTION_SHARE + 1e-6)   # 장면 나머지는 정지 화면
        self.assertLessEqual(rep["quote_motion_share"], quotemod.VIDEO_MOTION_SHARE + 1e-6)
        self.assertTrue(rep["commentary_present"] and rep["attribution_present"])
        self.assertEqual(out[1]["clip_range"], f"{clip_analyzer.fmt(10)}-{clip_analyzer.fmt(10 + out[1]['play'])}")

    def test_short_source_cannot_be_replaced(self):
        entries = {1: self.entry(1, 2.4, src_dur=6.0), 2: self.entry(3.5, 2.4, src_dur=6.0)}
        out, rep = quotemod.guard(entries, self.script, [4.0] * 5, self.decision, self.reg, kpop_spec())
        used = sum(e["play"] for e in out.values())
        self.assertLessEqual(used, 6.0 * quotemod.SOURCE_USE_SHARE + 0.31)
        self.assertTrue(any("원본 길이" in a for a in rep["actions"]))

    def test_same_range_and_too_many_quote_scenes(self):
        entries = {1: self.entry(10, 2), 2: self.entry(10.5, 2)}
        out, rep = quotemod.guard(entries, self.script, [4.0] * 5, self.decision, self.reg, kpop_spec())
        self.assertIn(1, out)
        self.assertNotIn(2, out)
        many = {i: self.entry(10 + 30 * i, 1) for i in range(5)}
        out, _ = quotemod.guard(many, self.script, [4.0] * 5, self.decision, self.reg, kpop_spec())
        self.assertLessEqual(len(out), int(5 * quotemod.QUOTE_SCENE_SHARE))

    def test_missing_attribution_is_dropped_and_viewer_question_warned(self):
        e = self.entry(10, 2)
        e["credit"] = ""
        out, rep = quotemod.guard({1: e}, self.script, [4.0] * 5, {}, self.reg, kpop_spec())
        self.assertNotIn(1, out)
        out, rep = quotemod.guard({1: self.entry(10, 2)}, self.script, [4.0] * 5, {}, self.reg, kpop_spec())
        self.assertTrue(any("viewer_question" in w for w in rep["warnings"]))


class PlacementTests(unittest.IsolatedAsyncioTestCase):
    async def test_screenshots_compose_before_after_on_comparison_scene(self):
        with tempfile.TemporaryDirectory() as d:
            job = Path(d)
            reg = SourceRegistry(job)
            for name, color in (("cap_a.jpg", (200, 30, 30)), ("cap_b.jpg", (30, 30, 200))):
                Image.new("RGB", (1280, 720), color).save(job / name)
                add_quote(reg, job / name, kind="image")
            script = planned(["hook", "background", "change", "current_update", "ending_question"])
            spec = INTEG["profiles"]["curiosity_update_story"]
            out = await quotemod.plan_quotes(job_dir=job, registry=reg, script=script, durations=[4.0] * 5,
                                             spec=spec, decision={"viewer_question": "q"})
            self.assertEqual(out[2]["layout"], "compare")
            with Image.open(out[2]["path"]) as composed:
                self.assertEqual(composed.size, (1080, 1920))
            self.assertTrue(reg.by_path(out[2]["path"]).usable_in_video)       # 합성본도 인용 출처를 잇는다
            self.assertNotIn(0, out)                                            # 훅은 자체 카드

    async def test_video_ranges_prefer_benchmark_evidence_and_do_not_repeat(self):
        with tempfile.TemporaryDirectory() as d:
            job = Path(d)
            reg = SourceRegistry(job)
            cam = job / "cam.mp4"
            cam.write_bytes(b"0" * 2048)
            add_quote(reg, cam)
            script = planned(["reason_to_watch", "first_evidence", "comparison_or_interpretation",
                              "comparison_or_interpretation", "payoff_or_question"])
            calls = []

            async def analyze(path, need, **kw):
                calls.append(kw)
                return fake_analysis(path, need, **kw)
            decision = {"evidence_moments": [{"start_sec": 31.0, "end_sec": 36.0, "what": "포인트"}]}
            with patch.object(quotemod.clip_analyzer, "analyze", new=analyze):
                out = await quotemod.plan_quotes(job_dir=job, registry=reg, script=script, durations=[4.0] * 5,
                                                 spec=kpop_spec(), decision=decision, transcript_url=URL)
            self.assertEqual(sorted(out), [1, 2, 3])
            self.assertEqual(calls[0]["prefer"], [(31.0, 36.0)])                # 같은 원본이면 근거 시각 우선
            self.assertEqual(calls[1]["avoid"], [(out[1]["start"], out[1]["end"])])   # 이미 쓴 구간 피함
            self.assertTrue(all(e["play"] <= 4.0 * quotemod.SCENE_MOTION_SHARE + 1e-6 for e in out.values()))


class KpopRouterTests(unittest.TestCase):
    def test_kpop_needs_evidence_video_but_accepts_quote_media(self):
        brief = make_brief(top="kpop_observation_clip", top_level=10)
        self.assertNotEqual(bench_auto.route(brief, INTEG, has_licensed_video=False)["selected_profile"],
                            "kpop_observation_clip")
        self.assertEqual(bench_auto.route(brief, INTEG, has_licensed_video=True)["selected_profile"],
                         "kpop_observation_clip")


class PipelineQuoteTests(FactoryTestCase):
    def setUp(self):
        super().setUp()
        self.cam = self.root / "stage_cam.mp4"
        self.cam.write_bytes(b"0" * 4096)
        self.brief = AsyncMock(return_value=make_brief(top="kpop_observation_clip", top_level=10))
        self.stack.enter_context(patch.object(run.bench_auto, "ask_structured", new=self.brief))
        self.stack.enter_context(patch.object(quotemod.clip_analyzer, "analyze",
                                              new=AsyncMock(side_effect=fake_analysis)))

    async def test_kpop_observation_consumes_quote_evidence(self):
        out = await core.make(topic="같은 안무 다른 느낌", quotes=[str(self.cam)],
                              quote_source=f"쇼케이스 직캠 | 참고 채널 | {URL}", log=lambda m: None)
        self.assertEqual(out["status"], "render_complete")
        job = Path(out["project_dir"])
        state = st.load(job)
        self.assertEqual(state["benchmark"]["selected_profile"], "kpop_observation_clip")
        self.assertIn("인용", self.brief.await_args.args[2])                  # brief 에 인용 자료가 있다고 알림
        self.assertIn("인용 장면", self.write_script.await_args.kwargs["benchmark_block"])
        tl = timeline.load(job)
        quoted = [s for s in tl["scenes"] if s["visual"]["kind"] == "video"]
        self.assertTrue(quoted)
        self.assertEqual(tl["scenes"][0]["visual"]["kind"], "image")           # 훅은 자체 카드
        for s in quoted:
            self.assertLess(s["visual"]["play"], s["duration"])                # 일부만 재생, 나머지 정지 화면
            self.assertTrue(s["credit"].startswith("인용:"))
            self.assertFalse(s["visual"]["has_audio"])
        items = json.loads((job / "sources.json").read_text(encoding="utf-8"))
        cam = [i for i in items if i["path"].endswith("stage_cam.mp4")][0]
        self.assertEqual((cam["usage"], cam["rights_status"], cam["license"]),
                         ("transformative_quote", "transformative_quote", "transformative_quote"))
        self.assertEqual(cam["attribution"], {"title": "쇼케이스 직캠", "channel": "참고 채널", "url": URL})
        self.assertTrue(cam["purpose"])
        self.assertTrue(cam["clip_ranges"] and cam["scene_ids"])
        report = json.loads((job / quotemod.PLAN_FILE).read_text(encoding="utf-8"))
        self.assertTrue(report["commentary_present"] and report["attribution_present"])
        self.assertLessEqual(report["quote_motion_share"], quotemod.VIDEO_MOTION_SHARE + 1e-6)

    async def test_resume_and_rerender_preserve_quote_status(self):
        pending = await core.make(topic="같은 안무 다른 느낌", quotes=[str(self.cam)], review=True,
                                  quote_source=f"쇼케이스 직캠 | 참고 채널 | {URL}", log=lambda m: None)
        done = await core.resume(pending["project_id"], log=lambda m: None)
        self.assertEqual(done["status"], "render_complete")
        job = Path(done["project_dir"])

        def cam_item():
            items = json.loads((job / "sources.json").read_text(encoding="utf-8"))
            return [i for i in items if i["path"].endswith("stage_cam.mp4")][0]
        before = cam_item()
        self.assertEqual(before["rights_status"], "transformative_quote")
        self.assertTrue(before["clip_ranges"])
        await core.rerender(done["project_id"], log=lambda m: None)
        after = cam_item()
        self.assertEqual((after["rights_status"], after["usage"], after["attribution"], after["clip_ranges"]),
                         (before["rights_status"], before["usage"], before["attribution"], before["clip_ranges"]))

    async def test_quote_without_media_keeps_link_analysis_only(self):
        out = await core.make(topic="같은 안무 다른 느낌", log=lambda m: None)
        bench = st.load(Path(out["project_dir"]))["benchmark"]
        self.assertNotEqual(bench["selected_profile"], "kpop_observation_clip")   # 근거 영상 없으면 다음 구조


class RealRenderTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg 필요")
    async def test_play_then_freeze_frame(self):
        from app.pipeline import render
        with tempfile.TemporaryDirectory() as d:
            vid, out = Path(d) / "cam.mp4", Path(d) / "out.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                            "-i", "testsrc=s=640x360:d=4", "-pix_fmt", "yuv420p", str(vid)], check=True)
            await render.render_broll([{"kind": "video", "path": vid, "start": 0.5, "duration": 2.0, "play": 0.6,
                                        "has_audio": False}], None, out, width=360, height=640, fps=15)
            from app.pipeline.media import probe_duration_sync
            self.assertAlmostEqual(probe_duration_sync(out), 2.0, delta=0.2)


if __name__ == "__main__":
    unittest.main()
