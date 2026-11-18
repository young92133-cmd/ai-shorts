"""팬튜브 편집 스킨 (benchmark source lovelittt) — 실제 ffmpeg·AI 호출 없음."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.factory import __main__ as cli
from app.pipeline import fantube, render, timeline
from app.pipeline.subtitles import build_ass, write_srt


def _lines():
    return [{"start": 0.3, "end": 2.6, "text": "국밥 근데 진짜 *맛있어*", "words": []},
            {"start": 3.1, "end": 4.8, "text": "[화남] 화가 난다", "words": []},
            {"start": 5.2, "end": 6.5, "text": "[억울][강조] 나만 몰랐어", "words": []},
            {"start": 6.6, "end": 7.9, "text": "[스토리] 그런데 그때 말했다", "words": []}]


def _timeline(job: Path, mode: str = "observation") -> dict:
    scenes = [{"duration": 4, "title": "첫 장면", "credit": "", "visual": {"kind": "video", "path": job / "a.mp4",
                                                                         "src_start": 0, "has_audio": True}},
              {"duration": 4, "title": "", "credit": "", "visual": {"kind": "image", "path": job / "b.png"}}]
    return timeline.build_timeline(job, width=1080, height=1920, fps=30, mode=mode, narration=None, bgm=None,
                                   bgm_volume=0, source_volume=1, transition=0, scenes=scenes, lines=_lines(),
                                   subtitle_style={"font": "Malgun Gothic", "size": 54})


class MarkTests(unittest.TestCase):
    def test_parse_marks(self):
        m = fantube.parse_marks("[화남][강조] 진짜 *맛있어* 국밥")
        self.assertEqual((m["tone"], m["blur"], m["story"]), ("angry", True, False))
        self.assertEqual(m["text"], "진짜 맛있어 국밥")
        self.assertIn(("맛있어", True), m["spans"])
        self.assertEqual(fantube.parse_marks("[스토리] 그때")["story"], True)
        self.assertEqual(fantube.parse_marks("[억울] 왜")["tone"], "sad")

    def test_unknown_bracket_and_unpaired_star_stay_as_text(self):
        self.assertEqual(fantube.strip_marks("[속보] 소식"), "[속보] 소식")
        self.assertEqual(fantube.strip_marks("별 * 하나"), "별 * 하나")

    def test_default_skin_and_srt_hide_marks(self):
        with tempfile.TemporaryDirectory() as folder:
            words = [{"text": "[화남]", "start": 0, "end": 0.2}, {"text": "*진짜*", "start": 0.2, "end": 0.8}]
            ass = build_ass([], Path(folder) / "s.ass", 1080, 1920,
                            lines=[{"start": 0, "end": 1, "text": "[화남] *진짜*", "words": words}])
            text = ass.read_text(encoding="utf-8-sig")
            srt = write_srt([{"start": 0, "end": 1, "text": "[화남] *진짜*"}], Path(folder) / "s.srt")
            srt_text = srt.read_text(encoding="utf-8")
        self.assertNotIn("[화남]", text)
        self.assertNotIn("*", text)
        self.assertIn("진짜", text)
        self.assertNotIn("[화남]", srt_text)
        self.assertIn("진짜", srt_text)


class AssTests(unittest.TestCase):
    def test_fantube_ass_has_headline_tones_and_no_scene_titles(self):
        with tempfile.TemporaryDirectory() as folder:
            out = build_ass([], Path(folder) / "s.ass", 1080, 1920, skin="fantube", total=8,
                            headline={"accent": "아일릿 원희", "main": "술 마시고 연애 공개하는 원희 ㅋㅋ"},
                            titles=[(0, 4, "장면 키워드")], lines=_lines())
            text = out.read_text(encoding="utf-8-sig")
        for style in ("Style: FTAccent", "Style: FTMain", "Style: FTLine", "Style: FTAngry", "Style: FTSad"):
            self.assertIn(style, text)
        self.assertIn(",FTAccent,,0,0,0,,아일릿 원희", text)
        self.assertNotIn("장면 키워드", text)                       # 장면별 키워드 대신 고정 제목
        self.assertIn(",FTAngry,", text)
        self.assertIn(",FTSad,", text)
        self.assertIn(fantube.EMPH_ASS, text)                       # *맛있어* 강조색
        self.assertIn("\\clip(0,0,0,1920)", text)                    # [스토리] 밀면서 등장
        self.assertIn("\\t(0,170,0.45,\\fscx100\\fscy100)", text)  # 가속도 팝
        self.assertNotIn("[화남]", text)


class SfxTests(unittest.TestCase):
    def test_events_dedupe_and_priority(self):
        events = fantube.sfx_events([0, 3.0, 6.0], [{"start": 3.05, "text": "[화남] 왜"},
                                                    {"start": 1.0, "text": "안녕"}])
        self.assertEqual(events, [(1.0, "pop"), (3.0, "hit"), (6.0, "whoosh")])

    def test_filters_build_sfx_track(self):
        graph = ";".join(fantube.sfx_filters([(1.0, "pop"), (2.5, "whoosh")], 8))
        self.assertIn("adelay=1000|1000", graph)
        self.assertIn("amix=inputs=2", graph)
        self.assertTrue(graph.endswith("atrim=duration=8.000[sfx]"))
        self.assertEqual(fantube.sfx_filters([], 8), [])


class RenderTests(unittest.IsolatedAsyncioTestCase):
    async def test_render_timeline_passes_open_bottom_effects(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            tl = _timeline(job)
            tl["skin"] = "fantube"
            with patch.object(timeline, "render_broll", new=AsyncMock()) as broll:
                await timeline.render_timeline(tl, job, job / "final.mp4")
            kw = broll.await_args.kwargs
            self.assertEqual(kw["frame_layout"], "open_bottom")
            self.assertEqual(kw["blur_spans"], [(5.2, 6.5)])
            self.assertIn((4.0, "whoosh"), kw["sfx_events"])
            ass = (job / "subs.ass").read_text(encoding="utf-8-sig")
            self.assertIn(",FTMain,", ass)
            self.assertIn("첫 장면", ass)                             # 제목이 없으면 첫 장면 키워드를 제목으로

            tl["sfx"] = False
            tl["mode"] = "slideshow"
            with patch.object(timeline, "render_slideshow", new=AsyncMock()) as slides:
                await timeline.render_timeline(tl, job, job / "final.mp4")
            self.assertEqual(slides.await_args.kwargs["frame_layout"], "open_bottom")
            self.assertNotIn("sfx_events", slides.await_args.kwargs)

    async def test_broll_graph_open_bottom_sfx_and_blur(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(render, "run_ffmpeg", new=AsyncMock()) as ffmpeg:
            path = Path(folder)
            await render.render_broll([
                {"kind": "video", "path": path / "v.mp4", "start": 0, "duration": 4, "has_audio": True},
                {"kind": "image", "path": path / "c.png", "duration": 2},
            ], None, path / "final.mp4", frame_layout="open_bottom", source_volume=1,
                sfx_events=[(4.0, "whoosh")], blur_spans=[(1, 2)])
            args = ffmpeg.await_args.args[0]
            graph = args[args.index("-filter_complex") + 1]
        top = fantube.bar_height(1920)
        self.assertIn(f"crop=1080:{1920 - top},pad=1080:1920:0:{top}:black", graph)   # 영상: 아래까지 채움
        self.assertIn(f"pad=1080:1920:(ow-iw)/2:{top}+", graph)                      # 이미지: 잘리지 않게
        self.assertIn("[acat]anull[amain]", graph)
        self.assertIn("[amain][sfx]amix=inputs=2", graph)
        self.assertIn("enable='between(t,1.000,2.000)'", graph)
        self.assertIn("-map", args)

    async def test_default_skin_graph_unchanged(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(render, "run_ffmpeg", new=AsyncMock()) as ffmpeg:
            path = Path(folder)
            await render.render_slideshow([path / "a.png"], [3.0], path / "n.mp3", path / "final.mp4")
            args = ffmpeg.await_args.args[0]
            graph = args[args.index("-filter_complex") + 1]
        self.assertNotIn("[sfx]", graph)
        self.assertNotIn("[amain]", graph)
        self.assertNotIn("boxblur", graph)


class CliTests(unittest.TestCase):
    def test_cli_accepts_skin_options(self):
        ap = cli._parser()
        a = ap.parse_args(["make", "--topic", "x", "--skin", "fantube"])
        self.assertEqual(a.skin, "fantube")
        r = ap.parse_args(["rerender", "p1", "--skin", "fantube", "--headline", "제목", "--no-sfx"])
        self.assertEqual((r.skin, r.headline, r.sfx), ("fantube", "제목", False))
        self.assertIsNone(ap.parse_args(["rerender"]).sfx)
        b = ap.parse_args(["benchmark", "plan", "--input", "i.json", "--skin", "fantube"])
        self.assertEqual(b.skin, "fantube")


if __name__ == "__main__":
    unittest.main()
