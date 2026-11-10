"""경쟁 채널 벤치마킹: 지표 계산·AI 결과 검증·캐시·추천 주제·패턴 적용 제작 (네트워크·AI 는 전부 가짜)."""
from __future__ import annotations

import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.pipeline import channels as ch

NOW = dt.datetime(2026, 11, 5, 21, 0, tzinfo=ch.KST)
PROFILES = ["curiosity_update_story", "event_timeline_story", "ranked_moments"]


def video(i, views, days, **kw):
    published = (NOW - dt.timedelta(days=days)).isoformat(timespec="minutes")
    return {"id": f"v{i}", "title": f"제목 {i}", "views": views, "duration": 20, "published": published,
            "listed_order": i, "has_auto_subs": True, **kw}


def scan_data():
    vids = [video(1, 90000, 2), video(2, 10000, 3), video(3, 12000, 4), video(4, 11000, 5),
            video(5, 300000, 60), video(6, 280000, 70), video(7, 260000, 80), video(8, 20000, 40)]
    return {"channel": {"id": "UCtest_channel_0000000001", "name": "테스트 채널", "subscribers": 50000,
                        "url": "https://www.youtube.com/@test"},
            "source": "test", "coverage": {"listed": 8, "detailed": 8}, "videos": vids,
            "scanned_at": NOW.isoformat(timespec="seconds")}


def ai_result():
    pattern = {"type": "근황·후속형", "name": "반전 근황", "evidence_video_ids": ["v1", "v1", "missing"],
               "observed": ["짧은 근황 제목"], "hypotheses": ["궁금증"], "hook_formula": "결과를 먼저 말한다",
               "retention_structure": "과거→변화→현재", "reveal_order": ["결과", "이유", "현재"], "twist_position": "마지막 20%",
               "recommended_seconds": 20, "screen_and_subtitles": "큰 자막 제안", "good_topics": ["근황"], "profile_id": "없는구조"}
    return {"summary": "s", "recurring_topics": ["아이돌"], "narration": "빠름", "source_usage": "미확인",
            "audience_interest": "미수집", "patterns": [pattern],
            "topic_ideas": [{"title": "제목 1", "angle": "a", "pattern_index": 3, "why": "w", "needs_research": "r"}] +
                           [{"title": f"새 주제 {i}", "angle": "a", "pattern_index": 0, "why": "w", "needs_research": "r",
                             "search_query": f"K팝 새 주제 {i}"} for i in range(4)]}


class EngineTests(unittest.TestCase):
    def test_channel_url_forms(self):
        self.assertEqual(ch.channel_url("@zzal_ing"), "https://www.youtube.com/@zzal_ing/shorts")
        self.assertEqual(ch.channel_url("https://www.youtube.com/@abc/videos"), "https://www.youtube.com/@abc/shorts")
        self.assertTrue(ch.channel_url("https://youtube.com/channel/UCMilw9TMHP-zAoWBiuYZvug").endswith("/shorts"))
        with self.assertRaises(ValueError):
            ch.channel_url("https://example.com/@x")

    def test_age_adjusted_does_not_favor_old_videos(self):
        d = ch.metrics(scan_data(), now=NOW)
        v = {x["id"]: x for x in d["videos"]}
        self.assertGreater(v["v1"]["age_adjusted"], v["v5"]["age_adjusted"])     # 새 영상 9만 > 오래된 30만
        self.assertIn("급상승(추정)", v["v1"]["groups"])
        self.assertIn("인기 상위", v["v5"]["groups"])
        self.assertIn("구독자 초과", v["v5"]["groups"])
        self.assertFalse(d["stats"]["real_growth_measured"])
        self.assertTrue(any("추정" in n for n in d["stats"]["notes"]))

    def test_rescan_measures_real_growth(self):
        old = ch.metrics(scan_data(), now=NOW - dt.timedelta(days=2))
        old["scanned_at"] = (NOW - dt.timedelta(days=2)).isoformat()
        new = scan_data()
        new["videos"][1]["views"] = 210000
        d = ch.metrics(new, previous=old, now=NOW)
        v2 = next(v for v in d["videos"] if v["id"] == "v2")
        self.assertEqual(v2["views_gain_per_day"], 100000.0)
        self.assertIn("급상승(실측)", v2["groups"])
        self.assertTrue(d["stats"]["real_growth_measured"])

    def test_ai_result_is_checked_by_code(self):
        d = ch.metrics(scan_data(), now=NOW)
        r = ch.finish(ai_result(), d, PROFILES)
        p = r["patterns"][0]
        self.assertEqual(p["evidence_video_ids"], ["v1"])                  # 없는 id·중복 제거
        self.assertEqual(p["stats"]["median_views"], 90000)                 # 수치는 코드가 계산
        self.assertEqual(p["profile_id"], "curiosity_update_story")         # 목록 밖 구조 보정
        self.assertTrue(r["topic_ideas"][0]["too_similar"])                 # 원본 제목과 같은 주제 표시
        self.assertEqual(r["topic_ideas"][0]["pattern_index"], 0)
        self.assertTrue(any("비공개" in u for u in r["uncollected"]))

    def test_idea_follows_its_pattern_after_sorting(self):
        d = ch.metrics(scan_data(), now=NOW)
        r = ai_result()
        weak = {**r["patterns"][0], "type": "비교·순위형", "name": "약한 패턴", "evidence_video_ids": ["v2"], "profile_id": "ranked_moments"}
        r["patterns"] = [weak, r["patterns"][0]]            # AI 순서: 약한 것이 0번
        r["topic_ideas"][1]["pattern_index"] = 1           # '반전 근황' 패턴 주제
        out = ch.finish(r, d, PROFILES)
        self.assertEqual(out["patterns"][0]["name"], "반전 근황")   # 성과순 정렬
        self.assertEqual(out["patterns"][out["topic_ideas"][1]["pattern_index"]]["name"], "반전 근황")

    def test_make_options_reference_structure_not_script(self):
        r = ch.finish(ai_result(), ch.metrics(scan_data(), now=NOW), PROFILES)
        o = ch.make_options(r, 0, r["topic_ideas"][1])
        self.assertEqual((o["benchmark"], o["seconds"]), ("curiosity_update_story", 20))
        self.assertIn("결과를 먼저 말한다", o["instructions"])
        self.assertIn("옮기지 말고", o["instructions"])
        self.assertIn("보장", o["instructions"])

    def test_compare_finds_common_types_without_ai(self):
        a = ch.finish(ai_result(), ch.metrics(scan_data(), now=NOW), PROFILES)
        b = copy.deepcopy(a)
        a["channel_id"], b["channel_id"] = "ch_a", "ch_b"
        out = ch.compare([a, b])
        self.assertEqual(out["common_types"], ["근황·후속형"])
        self.assertTrue(out["patterns"][0]["common"])
        self.assertTrue(all(not i.get("too_similar") for i in out["topic_ideas"]))

    def test_overlap_detects_copied_script(self):
        ref = "작년 복귀 선언을 했던 멤버들이 결국 다시 무대에 섰다는 소식입니다"
        self.assertGreater(ch.overlap(ref + " 추가 문장", [ref]), 0.5)
        self.assertEqual(ch.overlap("전혀 다른 새 대본으로 쓴 이야기입니다", [ref]), 0.0)


class FactoryChannelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from app.factory import core
        self.core = core
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(core, "output_root", return_value=Path(self.tmp.name))
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    async def analyzed(self):
        from app.factory import channels as fc
        async def fake_transcripts(data, workdir, k=6, log=print):
            data["videos"][0]["transcript"] = "작년 복귀 선언을 했던 멤버들이 결국 다시 무대에 섰다는 소식입니다"
            data["coverage"]["transcripts"] = 1
        data = scan_data()
        # This cache-reuse test must stay fresh after the original fixture date.
        data["scanned_at"] = dt.datetime.now(ch.KST).isoformat(timespec="seconds")
        with patch.object(ch, "scan", new=AsyncMock(return_value=data)) as scan, \
             patch.object(ch, "add_transcripts", new=fake_transcripts), \
             patch.object(fc.comments, "fetch_candidates", new=AsyncMock(return_value=[])), \
             patch.object(ch, "ask_structured", new=AsyncMock(return_value=ch.ChannelAnalysis.model_validate(ai_result()))) as ask:
            first = await fc.analyze("@test", log=lambda *_: None)
            second = await fc.analyze("@test", log=lambda *_: None)
        return fc, first, second, scan, ask

    async def test_analysis_is_cached_and_reused(self):
        fc, first, second, scan, ask = await self.analyzed()
        self.assertEqual(scan.await_count, 1)
        self.assertEqual(ask.await_count, 1)
        self.assertTrue(second["reused_cache"])
        self.assertEqual(first["channel_id"], second["channel_id"])
        self.assertEqual(fc.show("@test")["analysis"]["patterns"][0]["type"], "근황·후속형")
        self.assertEqual(fc.channels()["channels"][0]["videos"], 8)

    async def test_ai_failure_reports_recovery(self):
        from app.factory import channels as fc
        with patch.object(ch, "scan", new=AsyncMock(return_value=scan_data())), \
             patch.object(ch, "add_transcripts", new=AsyncMock()), \
             patch.object(fc.comments, "fetch_candidates", new=AsyncMock(return_value=[])), \
             patch.object(ch, "ask_structured", new=AsyncMock(side_effect=RuntimeError("OAuth session expired"))):
            with self.assertRaises(self.core.FactoryError) as err:
                await fc.analyze("@test", log=lambda *_: None)
        self.assertIn("claude-login", err.exception.message)

    async def test_topics_then_batch_select_uses_pattern(self):
        from app.factory import batch
        fc, first, *_ = await self.analyzed()
        listed = fc.topics([first["channel_id"]])
        self.assertEqual(len(listed["candidates"]), 5)
        self.assertTrue(listed["candidates"][0]["too_similar"])
        job = Path(self.tmp.name) / "p1"
        job.mkdir()
        (job / "script.json").write_text('{"scenes": [{"narration": "새로 쓴 대본"}]}', encoding="utf-8")
        done = {"status": "render_complete", "project_id": "p1", "project_dir": str(job)}
        with patch.object(self.core, "make", new=AsyncMock(return_value=done)) as make:
            out = await batch.make(select=[2], candidates_id=listed["candidates_id"], benchmark="auto", log=lambda *_: None)
        self.assertEqual(out["items"][0]["result"]["channel_benchmark"]["overlap_with_benchmark"], 0.0)
        self.assertTrue((job / "channel_benchmark.json").is_file())   # batch --select 경로도 복사 감시 기록
        kw = make.call_args.kwargs
        self.assertEqual(kw["topic"], "K팝 새 주제 0")                    # 조사용 문장(분야 포함)이 주제로
        self.assertIn("영상 제목 후보: 새 주제 0", kw["instructions"])
        self.assertEqual(kw["benchmark"], "curiosity_update_story")       # 패턴 구조가 CLI 기본 auto 보다 우선
        self.assertEqual(kw["seconds"], 20)
        self.assertIn("후킹", kw["instructions"])

    async def test_channel_make_records_overlap(self):
        fc, first, *_ = await self.analyzed()
        job = Path(self.tmp.name) / "job1"
        job.mkdir()
        (job / "script.json").write_text(json.dumps({"scenes": [{"narration": "완전히 새로 조사해서 쓴 대본입니다"}]},
                                                    ensure_ascii=False), encoding="utf-8")
        done = {"status": "render_complete", "project_id": "job1", "project_dir": str(job)}
        with patch.object(self.core, "make", new=AsyncMock(return_value=done)) as make:
            out = await fc.make(first["channel_id"], topic="새 주제", log=lambda *_: None)
        self.assertEqual(make.call_args.kwargs["benchmark"], "curiosity_update_story")
        self.assertEqual(out["channel_benchmark"]["overlap_with_benchmark"], 0.0)
        self.assertTrue((job / "channel_benchmark.json").is_file())

    async def test_auto_picks_common_pattern_topic(self):
        fc, first, *_ = await self.analyzed()
        done = {"status": "script_review", "project_id": "p2"}
        with patch.object(self.core, "make", new=AsyncMock(return_value=done)) as make:
            out = await fc.auto([first["channel_id"]], review=True, log=lambda *_: None)
        self.assertEqual(out["picked"]["topic"], "K팝 새 주제 0")
        self.assertTrue(make.call_args.kwargs["review"])

    async def test_parser(self):
        from app.factory import __main__ as cli
        a = cli._parser().parse_args(["channel", "analyze", "@x", "--no-ai"])
        self.assertEqual((a.cmd, a.channel_cmd, a.no_ai), ("channel", "analyze", True))
        a = cli._parser().parse_args(["channel", "topics", "ch_a", "ch_b"])
        self.assertEqual(a.channels, ["ch_a", "ch_b"])


if __name__ == "__main__":
    unittest.main()
