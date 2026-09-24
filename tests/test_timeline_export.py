"""timeline.json(자막·댓글 수정 → 다시 만들기)과 CapCut·재료 묶음 내보내기 점검.

ffmpeg 렌더·ffprobe 는 모두 가짜로 바꿔 실제 영상을 만들지 않는다.
"""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.jobs import JobManager
from app.pipeline import capcut, comment_layout, run, timeline
from app.pipeline.models import Word
from app.pipeline.render import _apply_overlays
from app.pipeline.subtitles import build_ass, words_to_lines, write_srt


def _words(offset: float = 0.0) -> list[Word]:
    return [Word(text=t, start=offset + i * 0.5, end=offset + i * 0.5 + 0.4)
            for i, t in enumerate(["콘크리트는", "왜", "강할까", "철근", "덕분입니다"])]


def _make_timeline(job_dir: Path, subtitles: bool = True) -> dict:
    scenes_dir = job_dir / "scenes"
    scenes_dir.mkdir(parents=True)
    scenes = []
    for i in range(2):
        img = scenes_dir / f"scene_{i:02d}.jpg"
        Image.new("RGB", (108, 192), (30 * i, 40, 50)).save(img)
        scenes.append({"duration": 2.5, "title": f"키워드{i + 1}", "credit": "사진: 예시" if i else "",
                       "visual": {"kind": "image", "path": img}})
    narration = job_dir / "narration.mp3"
    narration.write_bytes(b"fake")
    return timeline.build_timeline(
        job_dir, width=1080, height=1920, fps=30, mode="slideshow", narration=narration, bgm=None,
        bgm_volume=0.1, source_volume=0.12, transition=0.4, scenes=scenes,
        lines=words_to_lines([_words(0.0), _words(2.5)]),
        subtitle_style={"font": "Malgun Gothic", "size": 74, "highlight": "#FFD400", "outline": "#000000"},
        subtitles_enabled=subtitles,
        comments=[timeline.text_comment("c1", "이거 진짜 몰랐네요", 2.5, 6.0, "https://youtu.be/x")])


class SubtitleTests(unittest.TestCase):
    def test_lines_keep_scene_boundaries_and_karaoke(self):
        lines = words_to_lines([_words(0.0), _words(2.5)])
        self.assertTrue(all(ln["end"] <= 2.5 + 1e-6 for ln in lines if ln["start"] < 2.5))
        with tempfile.TemporaryDirectory() as folder:
            out = build_ass([], Path(folder) / "s.ass", 1080, 1920, lines=lines)
            text = out.read_text(encoding="utf-8-sig")
        self.assertIn(",Sub,,", text)
        self.assertIn("\\k", text)

    def test_disabled_subtitles_have_no_sub_events(self):
        with tempfile.TemporaryDirectory() as folder:
            out = build_ass(_words(), Path(folder) / "s.ass", 1080, 1920, lines=[],
                            titles=[(0, 2, "키워드")])
            text = out.read_text(encoding="utf-8-sig")
        self.assertNotIn(",Sub,,", text)
        self.assertIn(",Title,,", text)

    def test_srt_format(self):
        with tempfile.TemporaryDirectory() as folder:
            out = write_srt([{"start": 0, "end": 1.25, "text": "안녕"}, {"start": 61.5, "end": 62, "text": " "},
                             {"start": 3661.2, "end": 3662, "text": "끝"}], Path(folder) / "a.srt")
            text = out.read_text(encoding="utf-8")
        self.assertEqual(text, "1\n00:00:00,000 --> 00:00:01,250\n안녕\n\n2\n01:01:01,200 --> 01:01:02,000\n끝\n")


class TimelineEditTests(unittest.TestCase):
    def test_edit_respreads_only_changed_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            tl = _make_timeline(Path(folder))
        lines = json.loads(json.dumps(tl["subtitles"]["lines"]))
        original_words = lines[1]["words"]
        lines[0]["text"] = "콘크리트가 튼튼한 이유"
        new, removed = timeline.apply_edit(tl, {"subtitles": {"lines": lines, "enabled": False},
                                                "titles": ["바뀐 키워드", "  "], "comments": []})
        first = new["subtitles"]["lines"][0]
        self.assertEqual([w["text"] for w in first["words"]], ["콘크리트가", "튼튼한", "이유"])
        self.assertAlmostEqual(first["words"][0]["start"], first["start"])
        self.assertAlmostEqual(first["words"][-1]["end"], first["end"], places=2)
        self.assertEqual(new["subtitles"]["lines"][1]["words"], original_words)
        self.assertFalse(new["subtitles"]["enabled"])
        self.assertEqual([s["title"] for s in new["scenes"]], ["바뀐 키워드", ""])
        self.assertEqual(new["comments"], [])
        self.assertEqual(removed, [])

    def test_edit_clamps_times_and_ignores_unknown_comments(self):
        with tempfile.TemporaryDirectory() as folder:
            tl = _make_timeline(Path(folder))
        tl["comments"].append(timeline.image_comment("overlays/a.png", 1, 3, "a.png"))
        img_id = tl["comments"][1]["id"]
        new, removed = timeline.apply_edit(tl, {
            "subtitles": {"lines": [{"start": -5, "end": 99, "text": "  너무   긴  "}, {"text": ""}]},
            "comments": [{"id": "c1", "start": 4, "end": 4.1, "x": 5, "text": "고친 댓글"},
                         {"id": "hacker", "kind": "image", "path": "../../secret.png", "start": 0, "end": 1}],
        })
        line = new["subtitles"]["lines"][0]
        self.assertEqual((line["start"], line["end"], line["text"]), (0.0, 5.0, "너무 긴"))
        self.assertEqual(len(new["subtitles"]["lines"]), 1)
        self.assertEqual([c["id"] for c in new["comments"]], ["c1"])
        c1 = new["comments"][0]
        self.assertEqual((c1["text"], c1["x"]), ("고친 댓글", 0.95))
        self.assertGreaterEqual(c1["end"] - c1["start"], 0.3)
        self.assertEqual(removed, ["overlays/a.png"])
        self.assertNotIn(img_id, [c["id"] for c in new["comments"]])


class RenderTests(unittest.IsolatedAsyncioTestCase):
    def test_overlay_filter_times_and_inputs(self):
        args, filters, last = _apply_overlays(
            [{"path": "a.png", "start": 1, "end": 4, "x": 0.5, "y": 0.25, "width": 0.8},
             {"path": "bad.png", "start": 3, "end": 3},
             {"path": "b.png", "start": 5, "end": 6}], 7, "[vcat]", 10.0, 1080, 30)
        self.assertEqual(args.count("-i"), 2)          # 길이가 0인 캡처는 건너뛴다
        self.assertIn("[7:v]scale=864:-2", filters[0])
        self.assertIn("enable='between(t,1.000,4.000)'", filters[1])
        self.assertIn("y=H*0.2500-h/2", filters[1])
        self.assertTrue(filters[2].startswith("[8:v]"))
        self.assertEqual(last, "[ovo2]")

    async def test_render_timeline_passes_overlays_and_subtitles(self):
        with tempfile.TemporaryDirectory() as folder:
            job_dir = Path(folder)
            tl = _make_timeline(job_dir)
            (job_dir / "overlays").mkdir()
            Image.new("RGB", (400, 200)).save(job_dir / "overlays" / "cap.png")
            tl["comments"].append(timeline.image_comment("overlays/cap.png", 1, 3))
            fake = AsyncMock(return_value=job_dir / "final.mp4")
            with patch.object(timeline, "render_slideshow", new=fake):
                await timeline.render_timeline(tl, job_dir, job_dir / "final.mp4")
            ass = (job_dir / "subs.ass").read_text(encoding="utf-8-sig")
        kwargs = fake.await_args.kwargs
        self.assertEqual(len(kwargs["overlays"]), 1)
        self.assertEqual(kwargs["overlays"][0]["path"], job_dir / "overlays" / "cap.png")
        self.assertEqual(fake.await_args.args[1], [2.5, 2.5])
        self.assertIn("이거 진짜 몰랐네요", ass)
        self.assertIn(",Sub,,", ass)
        self.assertIn("사진: 예시", ass)

    async def test_rerender_keeps_old_video_when_render_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            job_dir = Path(folder)
            timeline.save(job_dir, _make_timeline(job_dir))
            (job_dir / "final.mp4").write_bytes(b"old")
            with patch.object(run, "require_ffmpeg"), \
                 patch.object(run.timelinemod, "render_timeline", new=AsyncMock(side_effect=RuntimeError("x"))):
                with self.assertRaises(RuntimeError):
                    await run.rerender(job_dir, {"paths": {"assets": folder}})
            self.assertEqual((job_dir / "final.mp4").read_bytes(), b"old")

    def test_apply_voice_uses_preset_voice_for_new_provider(self):
        cfg = {"tts": {"provider": "edge", "voice": "ko-KR-InJoonNeural", "voices": {"openai": "alloy"}},
               "preset": {"voice": {"openai": "nova"}}}
        run._apply_voice(cfg, {"tts_provider": "openai"})
        self.assertEqual((cfg["tts"]["provider"], cfg["tts"]["voice"]), ("openai", "nova"))
        run._apply_voice(cfg, {"voice": "echo"})
        self.assertEqual(cfg["tts"]["voice"], "echo")


class SceneRemapTests(unittest.TestCase):
    def test_deleted_scene_shifts_pinned_files(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = JobManager.__new__(JobManager)
            manager.output = Path(folder)
            up = Path(folder) / "job1" / "uploads"
            up.mkdir(parents=True)
            for name in ("scene_00_a.png", "scene_01_b.png", "scene_02_c.png", "other.png"):
                (up / name).write_bytes(b"x")
            manager._remap_scene_files("job1", [0, 2])   # 1번(두 번째) 장면 삭제
            names = sorted(p.name for p in up.iterdir())
        self.assertEqual(names, ["_removed_scene_01_b.png", "other.png", "scene_00_a.png", "scene_01_c.png"])


class CapCutExportTests(unittest.IsolatedAsyncioTestCase):
    async def _draft(self, subtitles: bool) -> tuple[dict, Path]:
        folder = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, folder, True)
        job_dir = Path(folder) / "job"
        tl = _make_timeline(job_dir, subtitles=subtitles)
        (job_dir / "overlays").mkdir()
        Image.new("RGB", (1000, 400)).save(job_dir / "overlays" / "cap.png")
        cap = timeline.image_comment("overlays/cap.png", 1, 3)
        cap.update(y=0.25, width=0.5)
        tl["comments"].append(cap)
        root = Path(folder) / "CapCut Drafts"
        root.mkdir()
        with patch.object(capcut, "probe_duration", new=AsyncMock(return_value=5.0)):
            draft = await capcut.export_draft(tl, job_dir, root, "테스트: 영상?")
        return json.loads((draft / "draft_content.json").read_text(encoding="utf-8")), draft

    async def test_draft_structure_and_references(self):
        content, draft = await self._draft(subtitles=True)
        self.assertEqual(draft.name, "테스트 영상")
        self.assertTrue((draft / "draft_info.json").is_file())
        self.assertTrue((draft / "draft_meta_info.json").is_file())
        self.assertTrue((draft / "Resources" / "scene_01.jpg").is_file())
        self.assertEqual(content["duration"], 5_000_000)
        self.assertEqual(content["canvas_config"]["ratio"], "9:16")
        kinds = [t["type"] for t in content["tracks"]]
        self.assertEqual(kinds, ["video", "video", "audio", "text", "text", "text"])

        ids = {m["id"] for group in content["materials"].values() for m in group}
        for track in content["tracks"]:
            for seg in track["segments"]:
                self.assertIn(seg["material_id"], ids)
                for ref in seg["extra_material_refs"]:
                    self.assertIn(ref, ids)
        for m in content["materials"]["videos"] + content["materials"]["audios"]:
            self.assertTrue(Path(m["path"]).is_file(), m["path"])

        scenes = content["tracks"][0]["segments"]
        self.assertEqual([s["target_timerange"] for s in scenes],
                         [{"start": 0, "duration": 2_500_000}, {"start": 2_500_000, "duration": 2_500_000}])
        overlay = content["tracks"][1]["segments"][0]
        self.assertAlmostEqual(overlay["clip"]["transform"]["y"], 0.5)
        self.assertAlmostEqual(overlay["clip"]["scale"]["x"], 0.5)   # 1000px 캡처를 화면 폭 50% 로
        text = json.loads(content["materials"]["texts"][0]["content"])
        self.assertEqual(text["styles"][0]["range"], [0, len(text["text"])])

    async def test_draft_without_subtitles_has_no_subtitle_track(self):
        content, _ = await self._draft(subtitles=False)
        self.assertNotIn("subtitle", [m["type"] for m in content["materials"]["texts"]])
        self.assertEqual([t["type"] for t in content["tracks"]], ["video", "video", "audio", "text", "text"])

    async def test_existing_draft_folder_is_never_touched(self):
        with tempfile.TemporaryDirectory() as folder:
            job_dir = Path(folder) / "job"
            tl = _make_timeline(job_dir)
            root = Path(folder) / "drafts"
            (root / "내 영상").mkdir(parents=True)
            (root / "내 영상" / "draft_content.json").write_text("mine", encoding="utf-8")
            with patch.object(capcut, "probe_duration", new=AsyncMock(return_value=5.0)):
                draft = await capcut.export_draft(tl, job_dir, root, "내 영상")
            self.assertEqual(draft.name, "내 영상_2")
            self.assertEqual((root / "내 영상" / "draft_content.json").read_text(encoding="utf-8"), "mine")

    async def test_pack_zip_contents(self):
        with tempfile.TemporaryDirectory() as folder:
            job_dir = Path(folder)
            tl = _make_timeline(job_dir)
            out = await capcut.export_pack(tl, job_dir, job_dir / "capcut_pack.zip")
            with zipfile.ZipFile(out) as z:
                names = set(z.namelist())
                order = z.read("순서.txt").decode("utf-8")
                srt = z.read("subtitles.srt").decode("utf-8")
        self.assertTrue({"01_장면.jpg", "02_장면.jpg", "narration.mp3", "subtitles.srt", "keywords.srt"} <= names)
        self.assertIn("이거 진짜 몰랐네요", order)
        self.assertIn("00:00:00,000 -->", srt)


class CommentLayoutTests(unittest.IsolatedAsyncioTestCase):
    def test_hits_become_slots_and_merge(self):
        # 40초 영상, 10프레임(4초 간격): 2~3번 프레임에 가운데 댓글, 7번에 아래 댓글
        hits = [None, None, "middle", "middle", None, None, None, "bottom", None, None]
        slots = comment_layout.slots_from_hits(hits, 40.0)
        self.assertEqual(slots, [{"at_ratio": 0.2, "seconds": 6.0, "y": 0.42},
                                 {"at_ratio": 0.7, "seconds": 4.0, "y": 0.6}])
        merged = comment_layout.merge_slots([slots, [{"at_ratio": 0.3, "seconds": 3.0, "y": 0.42}], []])
        self.assertEqual(len(merged), 2)          # 댓글을 쓴 영상 2개의 평균 개수 1.5 → 2
        self.assertEqual(merged[0], {"at_ratio": 0.25, "seconds": 4.5, "y": 0.42})

    def test_place_and_clean(self):
        slots = comment_layout.clean_slots([{"at_ratio": 2, "seconds": 99, "y": "x"}, {"at_ratio": 0.5},
                                            {"bad": 1}])
        self.assertEqual(slots, [{"at_ratio": 0.5, "seconds": 3.5, "y": 0.42}])
        self.assertEqual(comment_layout.place(slots, 0, 40.0), (20.0, 23.5, 0.42))
        self.assertIsNone(comment_layout.place(slots, 1, 40.0))

    async def test_analyze_uses_vision_results_without_network(self):
        from app.pipeline.models import AssetDescription
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "ref.mp4"
            video.write_bytes(b"v")

            async def fake_ffmpeg(args, cwd=None):
                Path(args[-1]).write_bytes(b"jpg")

            descs = [AssetDescription(description="d", keywords=["comment", "top"] if k in (1, 2) else [])
                     for k in range(8)]
            with patch.object(comment_layout, "vision_available", return_value=True), \
                 patch.object(comment_layout, "download_media", new=AsyncMock(return_value=video)), \
                 patch.object(comment_layout, "probe_duration", new=AsyncMock(return_value=20.0)), \
                 patch.object(comment_layout, "run_ffmpeg", new=fake_ffmpeg), \
                 patch.object(comment_layout, "describe_all", new=AsyncMock(return_value=descs)):
                out = await comment_layout.analyze_comment_layout(["https://youtu.be/a"], Path(folder), log=lambda m: None)
        self.assertEqual(out["comment_slots"], [{"at_ratio": 0.125, "seconds": 5.0, "y": 0.25}])
        self.assertIn("댓글 1개", out["comment_pattern"])

    async def test_style_slots_preselect_most_liked_comment_without_review(self):
        from app.config import load_config, load_presets, merge_options
        from app.pipeline.models import Scene, Script, SourceVideo
        with tempfile.TemporaryDirectory() as folder:
            cfg = load_config()
            cfg = merge_options(cfg, load_presets(cfg)["entertainment"], {})
            style = {"name": "s", "comment_slots": [{"at_ratio": 0.5, "seconds": 2.0, "y": 0.25}]}
            script = Script(topic="t", scenes=[Scene(narration="n", image_prompt="p", on_screen_text="k")],
                            titles=["t"], description="d", hashtags=[], sources=[])
            cands = [{"id": "a", "text": "A", "likes": 1, "url": "u1"}, {"id": "b", "text": "B", "likes": 9, "url": "u2"}]
            with (patch.object(run, "require_ffmpeg"),
                  patch.object(run.research, "research_topic", new=AsyncMock(return_value=[])),
                  patch.object(run.scriptmod, "write_script", new=AsyncMock(return_value=script)),
                  patch.object(run.brollmod, "gather_sources",
                               new=AsyncMock(return_value=[SourceVideo(url="https://youtu.be/x", duration=60)])),
                  patch.object(run.commentmod, "fetch_candidates", new=AsyncMock(return_value=cands))):
                result = await run.run_pipeline(Path(folder), "topic", "주제", cfg, until="script",
                                                style=style, visual_mode="broll")
        self.assertEqual(result["suggested_comment_ids"], ["b"])
        self.assertEqual([c["id"] for c in result["selected_comments"]], ["b"])


if __name__ == "__main__":
    unittest.main()
