"""사진 편집형 이슈 쇼츠 (issueshorts · factory issue) — 실제 Flow·TTS·네트워크 호출 없음."""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.factory import core, issue
from app.pipeline import issueshorts as iss


def _plan(**over) -> dict:
    d = {
        "topic": "시험 부정행위", "title_top": "실시간 적발됐다는", "title_bottom": "시험 부정행위 수법",
        "titles": ["실시간 적발됐다는 시험 부정행위 수법 ㄷㄷ"], "facts": ["보도 확인"], "sources": ["https://news.example/1"],
        "character_bible": "Korean man late 20s, black glasses",
        "photos": [
            {"id": "P01", "kind": "real", "desc": "보도 화면", "source": {"kind": "news", "url": "https://news.example/1", "site": "예시일보"}},
            {"id": "P02", "kind": "ai", "desc": "시험장 수험생", "prompt": "A student in an exam hall holding the paper up."},
            {"id": "P03", "kind": "ai", "desc": "놀란 수험생", "prompt": "Same student, surprised face.", "refs": ["P02"]},
            {"id": "P04", "kind": "real", "desc": "뉴스 영상 장면",
             "source": {"kind": "youtube", "url": "https://youtube.com/watch?v=x", "site": "예시뉴스", "at": 12.5}},
        ],
        "lines": [
            {"text": "시험에서 적발된 부정행위 수법?", "photo": "P01"},
            {"text": "최근 부정행위가 논란인데", "photo": "P01", "color": "yellow"},
            {"text": "한 감독관이 수상한 수험생을 봤다며", "photo": "P02", "tag": "(수상...)"},
            {"text": "시험지를 자꾸 들었다 놨다 했는데", "photo": "P02"},
            {"text": "확인해 보니 진짜였던 거임", "photo": "P03", "color": "red", "mark": "x"},
            {"text": "결국 응시 금지 처분까지 받았다고", "photo": "P04", "color": "green", "tag": "(ㄷㄷ)"},
            {"text": "생각보다 일이 커졌네", "photo": "P04"},
        ],
    }
    d.update(over)
    return d


class PlanTests(unittest.TestCase):
    def test_valid_plan_has_no_errors(self):
        errors, _ = iss.check_plan(iss.IssuePlan.model_validate(_plan()))
        self.assertEqual(errors, [])

    def test_errors_for_missing_photo_prompt_source(self):
        d = _plan()
        d["lines"][0]["photo"] = "P09"
        d["photos"][1]["prompt"] = ""
        d["photos"][0]["source"] = None
        errors, _ = iss.check_plan(iss.IssuePlan.model_validate(d))
        joined = " ".join(errors)
        self.assertIn("P09", joined)
        self.assertIn("prompt", joined)
        self.assertIn("source.url", joined)

    def test_warns_when_no_real_photo_and_community_without_hide(self):
        d = _plan()
        for p in d["photos"]:
            p.update(kind="ai", prompt=p.get("prompt") or "x", source=None)
        _, w = iss.check_plan(iss.IssuePlan.model_validate(d))
        self.assertTrue(any("실제 사진" in x for x in w))
        d = _plan()
        d["photos"][0]["source"]["kind"] = "community"
        _, w = iss.check_plan(iss.IssuePlan.model_validate(d))
        self.assertTrue(any("hide_note" in x for x in w))

    def test_flow_prompt_adds_refs_and_photoreal_rules(self):
        plan = iss.IssuePlan.model_validate(_plan())
        p = iss.flow_prompt(plan, plan.photos[2])
        self.assertIn("Name the result 'P03'", p)
        self.assertIn("P02 as the visual reference", p)
        self.assertIn("black glasses", p)
        for w in ("photorealistic", "no text", "no watermark", "no logo"):
            self.assertIn(w, p)

    def test_segments_merge_same_photo(self):
        plan = iss.IssuePlan.model_validate(_plan())
        segs = iss.segments(plan, [2.0] * 7)
        self.assertEqual([s["photo"] for s in segs], ["P01", "P02", "P03", "P04"])
        self.assertEqual([s["duration"] for s in segs], [4.0, 4.0, 2.0, 4.0])
        self.assertEqual(segs[2]["start"], 8.0)


class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.job = self.tmp / "job"
        iss.save_plan(self.job, iss.IssuePlan.model_validate(_plan()))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _img(self, name: str) -> Path:
        p = self.tmp / name
        p.write_bytes(b"\x89PNG" + b"0" * 2000)
        return p

    def test_add_file_records_source(self):
        iss.add_file(self.job, "P01", self._img("cap.png"))
        self.assertTrue((self.job / "photos" / "P01.png").is_file())
        rec = json.loads((self.job / iss.SOURCES_FILE).read_text(encoding="utf-8"))["P01"]
        self.assertEqual(rec["rights_status"], "transformative_quote")
        self.assertEqual(rec["site"], "예시일보")

    def test_add_from_dir_matches_ids(self):
        dl = self.tmp / "dl"
        dl.mkdir()
        for n in ("P02_flow.png", "P03 (1).jpeg", "P10_other.png", "random.png"):
            (dl / n).write_bytes(b"0" * 2000)
        res = iss.add_from_dir(self.job, dl)
        self.assertEqual(sorted(a["photo"] for a in res["added"]), ["P02", "P03"])
        self.assertEqual(res["missing_real"], ["P01", "P04"])
        self.assertTrue((self.job / "photos" / "P03.jpg").is_file())

    def test_youtube_uses_plan_source(self):
        async def fake(url, at, out):
            out.write_bytes(b"0" * 2000)
            return out
        with patch.object(iss, "youtube_frame", side_effect=fake) as yf:
            res = asyncio.run(iss.add_youtube(self.job, "P04", None, None))
        yf.assert_called_once()
        self.assertEqual(yf.call_args.args[:2], ("https://youtube.com/watch?v=x", 12.5))
        self.assertEqual(res["at"], 12.5)

    def test_unknown_photo_and_non_image(self):
        with self.assertRaises(iss.IssueError):
            iss.add_file(self.job, "P99", self._img("a.png"))
        bad = self.tmp / "a.txt"
        bad.write_text("x")
        with self.assertRaises(iss.IssueError):
            iss.add_file(self.job, "P01", bad)

    def test_ass_has_title_colors_tag_mark_credit(self):
        plan = iss.load_plan(self.job)
        out = iss.build_ass(plan, [0, 2, 4, 6, 8, 10, 12], [2.0] * 7,
                            [{"start": 0, "duration": 4, "text": "출처: 예시일보"}], self.job / "s.ass", 1080, 1920, "Malgun Gothic")
        t = out.read_text(encoding="utf-8-sig")
        self.assertIn("실시간 적발됐다는", t)
        self.assertIn(iss._ass_color(iss.COLORS["yellow"]), t)
        self.assertIn(iss._ass_color(iss.COLORS["red"]), t)
        self.assertIn("(수상...)", t)
        self.assertIn("\p1}m ", t)
        self.assertIn("출처: 예시일보", t)
        self.assertEqual(t.count(",ISLine,"), 7)


class FactoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = {"paths": {"output": str(self.tmp / "out"), "assets": str(self.tmp)}}
        self.p = patch("app.factory.issue.load_config", return_value=self.cfg)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _file(self, data: dict) -> str:
        f = self.tmp / "plan.json"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(f)

    def test_new_status_prompts_and_not_ready(self):
        res = issue.new(self._file(_plan()))
        self.assertEqual(res["photos_total"], 4)
        self.assertFalse(res["ready"])
        self.assertTrue(Path(res["prompts_file"]).is_file())
        pr = issue.prompts(res["project_id"], None)
        kinds = {p["photo"]: p["kind"] for p in pr["photos"]}
        self.assertEqual(kinds, {"P01": "real", "P02": "ai", "P03": "ai", "P04": "real"})
        self.assertIn("flow_prompt", pr["photos"][1])
        with self.assertRaises(core.FactoryError) as cm:
            asyncio.run(issue.assemble(res["project_id"], True))
        self.assertEqual(cm.exception.code, "not_ready")

    def test_bad_plan_is_rejected(self):
        with self.assertRaises(core.FactoryError) as cm:
            issue.new(self._file(_plan(lines=_plan()["lines"][:3])))
        self.assertIn("6줄", " ".join(cm.exception.extra.get("errors", [])))


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg 없음")
class RenderTests(unittest.TestCase):
    """합성 사진 + 무음 가짜 TTS 로 실제 ffmpeg 렌더 (네트워크·Edge TTS 호출 없음)."""

    def test_assemble_renders_band_layout(self):
        from app.config import load_config, merge_options
        from app.pipeline.media import probe_video
        tmp = Path(tempfile.mkdtemp())
        try:
            job = tmp / "job"
            iss.save_plan(job, iss.IssuePlan.model_validate(_plan()))
            import subprocess
            sizes = {"P01": "1200x900", "P02": "1600x900", "P03": "900x1600", "P04": "1280x720"}
            for pid, sz in sizes.items():
                f = tmp / f"{pid}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={sz}:rate=1",
                                "-frames:v", "1", str(f)], check=True)
                iss.add_file(job, pid, f)

            async def fake_synth(tts, text, out, voice, attempts, wait, log=None):
                subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                                "-t", "0.8", str(out)], check=True)
                return [], 0.8

            cfg = merge_options(load_config(), {}, {})
            cfg = {**cfg, "video": {**cfg["video"], "fps": 15}}
            with patch("app.pipeline.run._synthesize_one", side_effect=fake_synth), \
                    patch("app.pipeline.tts.get_tts", return_value=object()):
                res = asyncio.run(iss.assemble(job, cfg))
            self.assertEqual(res["photo_cuts"], 4)
            self.assertEqual(res["photos"], {"ai": 2, "real": 2})
            self.assertAlmostEqual(res["seconds"], 7 * (0.8 + iss.LINE_PAD), delta=0.4)
            info = asyncio.run(probe_video(Path(res["final_video"])))
            st = info["streams"][0]
            self.assertEqual((st["width"], st["height"]), (cfg["video"]["width"], cfg["video"]["height"]))
            meta = (job / "meta.txt").read_text(encoding="utf-8")
            self.assertIn("AI 생성 이미지", meta)
            self.assertIn("예시뉴스", meta)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
