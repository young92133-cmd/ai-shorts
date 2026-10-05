"""Benchmark × V1 통합: 자동 구조 선택(router)·대본 프롬프트·장면 계획·상태 저장.

AI·조사·TTS·렌더는 모두 가짜다. 실제 Claude 호출이나 네트워크 없이 돈다.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.factory import core, state as st
from app.pipeline import bench_auto, benchmark, run
from app.pipeline.bench_auto import (ContentBrief, ContentCandidate, Fact, FollowupQuery, ProfileScore,
                                     SourceAnalysis)
from app.pipeline.models import PlannedScript, Script, Word

from tests.test_factory import FactoryTestCase, cat_script

INTEG = bench_auto.load_integration()


def ps(pid: str, level: int, slots: list[str] | None = None, **override) -> ProfileScore:
    values = {c: level for c in bench_auto.CRITERIA}
    values.update(override)
    return ProfileScore(profile_id=pid, covered_slots=slots or [], reason=f"{pid} 이유", **values)


def make_brief(*, top: str = "curiosity_update_story", top_slots: list[str] | None = None, top_level: int = 9,
               others: int = 4, extra: dict[str, ProfileScore] | None = None, source: bool = False) -> ContentBrief:
    scores = []
    for pid, spec in INTEG["profiles"].items():
        if extra and pid in extra:
            scores.append(extra[pid])
        elif pid == top:
            scores.append(ps(pid, top_level, top_slots if top_slots is not None
                             else spec["research_needs"]["required"]))
        else:
            scores.append(ps(pid, others, spec["research_needs"]["required"]))
    return ContentBrief(
        topic="아이돌 최근 스타일 변화",
        verified_facts=[Fact(text="최근 무대 의상 색이 바뀌었다", source_index=1, date="2026-09"),
                        Fact(text="작년 무대는 검은 의상 위주였다", source_index=2)],
        inferences=["새 앨범 콘셉트에 맞춘 변화일 가능성"],
        source_analysis=SourceAnalysis(source_topic="스타일 변화", source_hook="결과 먼저", source_structure="현재→과거→이유",
                                       interesting_points=["익숙한 인물의 변화"]) if source else None,
        candidates=[
            ContentCandidate(viewer_question="최근 분위기가 달라 보이는 이유는?", reason_to_watch="익숙한 인물의 변화",
                             claim="최근 무대에서 이전과 다른 요소가 반복된다", creative_hook="결국 달라졌다",
                             evidence_fact_ids=[1, 2], hook_strength=18, evidence_strength=17, visual_potential=16,
                             freshness=15, payoff=18),
            ContentCandidate(viewer_question="최근 근황은?", reason_to_watch="근황", claim="활동 중", creative_hook="근황",
                             evidence_fact_ids=[1], hook_strength=12, evidence_strength=12, visual_potential=12,
                             freshness=12, payoff=12),
        ],
        profile_scores=scores,
        followup_queries=[FollowupQuery(profile_id=top, query="최근 무대 의상 변화 반응")],
    )


class RouterTests(unittest.TestCase):
    def test_integration_covers_every_production_profile(self):
        self.assertEqual(set(INTEG["profiles"]), {p["id"] for p in benchmark.profiles()})
        self.assertIn(INTEG["fallback"], INTEG["profiles"])

    def test_scores_all_profiles_and_picks_top_eligible(self):
        decision = bench_auto.route(make_brief(), INTEG)
        self.assertEqual(decision["mode"], "auto")
        self.assertEqual(decision["selected_profile"], "curiosity_update_story")
        self.assertEqual(len(decision["candidate_scores"]), 8)
        self.assertEqual(len(decision["top3"]), 3)
        scores = [r["score"] for r in decision["ranking"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(decision["candidate_scores"]["curiosity_update_story"], 90)
        self.assertIn("다음 후보", decision["selection_reason"])
        self.assertIn("조회수", decision["note"])            # 점수가 조회수 예측이 아님을 남긴다
        self.assertFalse(decision["fallback_used"])

    def test_scores_are_clamped(self):
        score, parts = bench_auto.score_profile(ps("x", 99), INTEG["weights"])
        self.assertEqual(score, 100)
        self.assertTrue(all(v == 10 for v in parts.values()))

    def test_licensed_video_profiles_are_gated_without_video(self):
        brief = make_brief(top="kpop_observation_clip", top_level=10)
        decision = bench_auto.route(brief, INTEG, has_licensed_video=False)
        self.assertNotEqual(decision["selected_profile"], "kpop_observation_clip")
        kpop = next(r for r in decision["ranking"] if r["profile_id"] == "kpop_observation_clip")
        self.assertFalse(kpop["eligible"])
        self.assertTrue(any("권리" in g for g in kpop["gates"]))
        with_video = bench_auto.route(brief, INTEG, has_licensed_video=True)
        self.assertEqual(with_video["selected_profile"], "kpop_observation_clip")
        self.assertEqual(with_video["narration_mode"], "optional")

    def test_missing_required_evidence_falls_back(self):
        brief = make_brief(top_slots=["past_state"], others=2)   # 변화·현재 근거 없음
        decision = bench_auto.route(brief, INTEG)
        cur = next(r for r in decision["ranking"] if r["profile_id"] == "curiosity_update_story")
        self.assertFalse(cur["eligible"])
        self.assertIn("change_point", cur["missing_slots"])
        self.assertEqual(decision["selected_profile"], INTEG["fallback"])
        self.assertEqual(decision["mode"], "fallback")
        self.assertTrue(decision["fallback_used"])
        self.assertTrue(decision["fallback_reason"])

    def test_brief_failure_uses_safe_fallback(self):
        decision = bench_auto.route(None, INTEG)
        self.assertEqual(decision["selected_profile"], INTEG["fallback"])
        self.assertEqual(decision["narration_mode"], "narrated")
        self.assertTrue(decision["fallback_used"])

    def test_forced_profile_and_gated_force(self):
        forced = bench_auto.route(make_brief(top="mechanism_explainer"), INTEG, forced="event_timeline_story")
        self.assertEqual((forced["mode"], forced["selected_profile"]), ("forced", "event_timeline_story"))
        gated = bench_auto.route(make_brief(), INTEG, forced="physics_comparison_simulation")
        self.assertEqual(gated["mode"], "forced_fallback")
        self.assertEqual(gated["selected_profile"], INTEG["fallback"])
        self.assertTrue(gated["warnings"])

    def test_invalid_profile_is_rejected(self):
        self.assertEqual(bench_auto.validate_choice(None), "auto")
        self.assertEqual(bench_auto.validate_choice("off"), "off")
        with self.assertRaises(ValueError):
            bench_auto.validate_choice("comparison_story")


class CandidateAndPromptTests(unittest.TestCase):
    def test_view_potential_picks_highest_candidate(self):
        index, cand, scored = bench_auto.pick_candidate(make_brief())
        self.assertEqual(index, 0)
        self.assertEqual(scored[0]["view_potential"]["total"], 84)
        self.assertEqual(cand.viewer_question, "최근 분위기가 달라 보이는 이유는?")
        self.assertEqual(bench_auto.pick_candidate(None), (-1, None, []))

    def test_prompt_block_injects_structure_and_separates_facts(self):
        brief = make_brief(source=True)
        decision = bench_auto.route(brief, INTEG)
        _, cand, _ = bench_auto.pick_candidate(brief)
        block = bench_auto.compose_prompt_block("curiosity_update_story", INTEG, decision, brief, cand, 30)
        for text in ("beat_role=hook", "beat_role=background", "beat_role=change", "beat_role=current_update",
                     "beat_role=payoff", "beat_role=ending_question", "viewer_question", "F1.", "★주장의 근거",
                     "I1.", "추론", "creative_hook", "원본 문장", "정확히 7개"):
            self.assertIn(text, block)
        self.assertIn("0~3초", block)                    # 첫 역할은 영상 맨 앞

    def test_short_videos_use_fewer_scenes(self):
        spec = INTEG["profiles"]["curiosity_update_story"]
        self.assertEqual(len(bench_auto.scene_roles(spec, 20)), 6)
        self.assertLessEqual(max(len(bench_auto.scene_roles(s, 60)) for s in INTEG["profiles"].values()), 8)

    def test_write_script_receives_block(self):
        captured = {}

        async def fake_ask(llm, system, user, schema):
            captured["user"] = user
            return cat_script()
        with patch.object(run.scriptmod, "ask_structured", new=fake_ask):
            import asyncio
            asyncio.run(run.scriptmod.write_script({}, {}, "주제", [], 30, benchmark_block="[콘텐츠 구조 — X]\n",
                                                   benchmark_scenes=7))
        self.assertIn("[콘텐츠 구조 — X]", captured["user"])
        self.assertIn("정확히 7개", captured["user"])


class ScenePlanTests(unittest.TestCase):
    def planned(self, roles=None) -> PlannedScript:
        data = cat_script().model_dump()
        for i, scene in enumerate(data["scenes"]):
            scene["beat_role"] = (roles or [""] * 5)[i]
        return PlannedScript.model_validate(data)

    def test_roles_follow_order_without_ai_roles(self):
        script = bench_auto.apply_scene_plan(self.planned(), "curiosity_update_story", INTEG, 20)
        roles = [s.beat_role for s in script.scenes]
        self.assertEqual(roles[0], "hook")
        self.assertEqual(roles[-1], "ending_question")
        self.assertEqual(script.scenes[0].content_kind, "hook")
        self.assertEqual(script.scenes[-1].content_kind, "conclusion")
        self.assertTrue(all(s.scene_type == s.beat_role for s in script.scenes))
        self.assertTrue(all("benchmark:curiosity_update_story" in s.notes for s in script.scenes))
        self.assertTrue(all(len(s.on_screen_text) <= 12 for s in script.scenes))

    def test_ai_roles_are_kept_and_invalid_ones_replaced(self):
        roles = ["hook", "background", "nonsense", "current_update", "ending_question"]
        script = bench_auto.apply_scene_plan(self.planned(roles), "curiosity_update_story", INTEG, 30)
        got = [s.beat_role for s in script.scenes]
        self.assertEqual(got[1], "background")
        self.assertIn(got[2], INTEG["profiles"]["curiosity_update_story"]["beats"][2]["role"])
        self.assertEqual(got[3], "current_update")

    def test_quality_check_reports_missing_roles(self):
        decision = {"selected_profile": "illustrated_fact_explainer"}
        good = bench_auto.apply_scene_plan(self.planned(), "illustrated_fact_explainer", INTEG, 30)
        self.assertEqual([s.beat_role for s in good.scenes],
                         ["hook", "context", "explanation", "payoff", "ending_question"])
        self.assertEqual(bench_auto.quality_check(decision, good, 30.0, INTEG), [])
        bad = self.planned(["background"] * 5)
        warnings = bench_auto.quality_check(decision, bad, 200.0, INTEG)
        self.assertTrue(any("훅" in w for w in warnings))
        self.assertTrue(any("길이" in w for w in warnings))

    def test_fit_roles_keeps_distinct_roles_first(self):
        roles = ["hook", "a", "b", "b", "c", "end"]
        self.assertEqual(bench_auto._fit_roles(roles, 5), ["hook", "a", "b", "c", "end"])
        self.assertEqual(bench_auto._fit_roles(roles, 6), roles)
        self.assertEqual(len(bench_auto._fit_roles(roles, 8)), 8)
        self.assertEqual(bench_auto._fit_roles(roles, 8)[0], "hook")
        self.assertEqual(bench_auto._fit_roles(roles, 3), ["hook", "b", "end"])

    def test_old_script_json_without_beat_role_still_loads(self):
        raw = json.loads(cat_script().model_dump_json())
        for scene in raw["scenes"]:
            scene.pop("beat_role", None)
        self.assertEqual(Script.model_validate(raw).scenes[0].beat_role, "")


class PipelineIntegrationTests(FactoryTestCase):
    def setUp(self):
        super().setUp()
        self.brief_call = AsyncMock(return_value=make_brief())
        self.make_plan = AsyncMock(side_effect=RuntimeError("구성 AI 없음"))
        self.stack.enter_context(patch.object(run.bench_auto, "ask_structured", new=self.brief_call))
        self.stack.enter_context(patch.object(run.scriptmod, "make_plan", new=self.make_plan))

    async def test_topic_make_selects_profile_and_records_state(self):
        out = await core.make(topic="아이돌 최근 스타일 변화", seconds=30, log=lambda m: None)
        self.assertEqual(out["status"], "render_complete")
        job = Path(out["project_dir"])
        state = st.load(job)
        bench = state["benchmark"]
        self.assertEqual(state["request"]["benchmark"], "auto")
        self.assertEqual(bench["selected_profile"], "curiosity_update_story")
        self.assertEqual(bench["viewer_question"], "최근 분위기가 달라 보이는 이유는?")
        self.assertEqual(bench["view_potential_score"], 84)
        self.assertEqual(len(bench["candidate_scores"]), 8)
        self.assertTrue(bench["selection_reason"])
        self.assertEqual(bench["narration_mode"], "narrated")
        self.assertIn("quality", bench)
        self.assertEqual(out["benchmark"]["selected_profile"], "curiosity_update_story")
        decision = bench_auto.load_decision(job)
        self.assertEqual(decision["verified_facts"][0]["text"], "최근 무대 의상 색이 바뀌었다")
        self.assertEqual(decision["research_followup"]["query"], "최근 무대 의상 변화 반응")
        # 대본 프롬프트에 구조가 들어가고, 기존 구성 분석(make_plan)은 건너뛴다
        kwargs = self.write_script.await_args.kwargs
        self.assertIn("beat_role=change", kwargs["benchmark_block"])
        self.assertEqual(kwargs["benchmark_scenes"], 7)
        self.make_plan.assert_not_awaited()
        saved = PlannedScript.model_validate_json((job / "script.json").read_text(encoding="utf-8"))
        self.assertEqual(saved.scenes[0].beat_role, "hook")
        self.assertEqual(saved.scenes[-1].beat_role, "ending_question")
        # 보충 조사가 원래 조사와 별도로 한 번 더 돌았다
        self.assertEqual(self.research.await_count, 2)
        insp = core.inspect(out["project_id"], "benchmark")
        self.assertEqual(insp["benchmark"]["selected_profile"], "curiosity_update_story")

    async def test_youtube_url_passes_source_analysis_without_download(self):
        url = "https://www.youtube.com/watch?v=testvideo11"
        info = {"title": "스타일 변화 영상", "channel": "참고 채널", "description": "참고용", "duration": 20,
                "webpage_url": url}
        with patch.object(core.runmod.youtube, "fetch_info", new=AsyncMock(return_value=info)), \
             patch.object(core.runmod.youtube, "fetch_transcript",
                          new=AsyncMock(return_value=[Word(text="변화", start=0, end=1)])), \
             patch.object(core.runmod.youtube, "download_media", new=AsyncMock()) as download:
            self.brief_call.return_value = make_brief(source=True)
            out = await core.make(url=url, log=lambda m: None)
        self.assertEqual(out["status"], "render_complete")
        download.assert_not_awaited()
        user = self.brief_call.await_args.args[2]
        self.assertIn("reference_url", user)
        self.assertIn("참고 유튜브 제목: 스타일 변화 영상", user)
        self.assertIn("원본 구조", self.write_script.await_args.kwargs["benchmark_block"])
        decision = bench_auto.load_decision(Path(out["project_dir"]))
        self.assertEqual(decision["source_analysis"]["source_hook"], "결과 먼저")

    async def test_direct_script_is_not_restructured(self):
        out = await core.make(script_text="첫째 문장입니다. 둘째 문장입니다. 셋째 문장입니다. 마지막 문장입니다.",
                              log=lambda m: None)
        self.assertEqual(out["status"], "render_complete")
        self.brief_call.assert_not_awaited()
        self.assertEqual(st.load(Path(out["project_dir"]))["benchmark"]["mode"], "not_applicable")

    async def test_benchmark_off_keeps_v1_flow(self):
        out = await core.make(topic="고양이", benchmark="off", log=lambda m: None)
        self.assertEqual(out["status"], "render_complete")
        self.brief_call.assert_not_awaited()
        self.make_plan.assert_awaited()
        self.assertEqual(self.write_script.await_args.kwargs["benchmark_block"], "")
        state = st.load(Path(out["project_dir"]))
        self.assertNotIn("benchmark", state)
        self.assertEqual(core.status(out["project_id"])["benchmark"], {"mode": "off"})

    async def test_invalid_profile_is_a_request_error(self):
        with self.assertRaises(core.FactoryError) as ctx:
            await core.make(topic="고양이", benchmark="comparison_story", log=lambda m: None)
        self.assertEqual(ctx.exception.code, "invalid")
        self.brief_call.assert_not_awaited()

    async def test_forced_profile_is_used(self):
        out = await core.make(topic="사건", benchmark="event_timeline_story", log=lambda m: None)
        bench = st.load(Path(out["project_dir"]))["benchmark"]
        self.assertEqual((bench["mode"], bench["selected_profile"]), ("forced", "event_timeline_story"))

    async def test_brief_failure_still_makes_video_with_fallback(self):
        self.brief_call.side_effect = RuntimeError("AI 없음")
        out = await core.make(topic="고양이", log=lambda m: None)
        self.assertEqual(out["status"], "render_complete")
        bench = st.load(Path(out["project_dir"]))["benchmark"]
        self.assertEqual(bench["selected_profile"], INTEG["fallback"])
        self.assertTrue(bench["fallback_used"])

    async def test_resume_and_rerender_keep_the_decision(self):
        pending = await core.make(topic="아이돌 최근 스타일 변화", review=True, log=lambda m: None)
        self.assertEqual(pending["status"], "waiting_for_script_approval")
        self.assertEqual(pending["benchmark"]["selected_profile"], "curiosity_update_story")
        self.assertEqual(self.brief_call.await_count, 1)
        done = await core.resume(pending["project_id"], log=lambda m: None)
        self.assertEqual(done["status"], "render_complete")
        self.assertEqual(self.brief_call.await_count, 1)          # 다시 고르지 않는다
        job = Path(done["project_dir"])
        after_resume = st.load(job)["benchmark"]
        self.assertEqual(after_resume["selected_profile"], "curiosity_update_story")
        self.assertIn("quality", after_resume)
        await core.rerender(done["project_id"], log=lambda m: None)
        self.assertEqual(st.load(job)["benchmark"]["selected_profile"], "curiosity_update_story")
        self.assertEqual(self.brief_call.await_count, 1)

    async def test_project_without_benchmark_reads_as_off(self):
        out = await core.make(topic="고양이", log=lambda m: None)
        job = Path(out["project_dir"])
        state = st.load(job)
        state.pop("benchmark")
        st.save(job, state)
        (job / bench_auto.DECISION_FILE).unlink()
        self.assertEqual(core.status(out["project_id"])["benchmark"], {"mode": "off"})
        self.assertEqual(core.inspect(out["project_id"], "benchmark")["benchmark"], {"mode": "off"})


if __name__ == "__main__":
    unittest.main()
