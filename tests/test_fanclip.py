"""팬 클립: 원본 영상만, 위 제목·영상 위 자막·아래 출처. 렌더는 실제 ffmpeg(합성 영상)로 확인한다."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.pipeline import fanclip as fc
from app.pipeline.media import require_ffmpeg


def plan(segs, **kw):
    return fc.FanClipPlan(title_top=kw.get("top", "인기가요 엔딩에서 보인"), title_accent=kw.get("acc", "회색 의상 디테일"),
                          segments=[fc.FanSegment(start=a, end=b, caption=c) for a, b, c in segs],
                          upload_title="t", description="d", hashtags=["#a"])


class NormalizeTests(unittest.TestCase):
    def test_clamps_overlaps_and_length(self):
        p = fc.normalize(plan([(0, 5, "첫 장면ㄷㄷ!!"), (3, 8, "겹침"), (10, 30, "길다"), (199, 205, "끝")]), 200, 15)
        self.assertEqual([(s.start, s.end) for s in p.segments], [(0, 5), (10, 20)])
        self.assertEqual(p.segments[0].caption, "첫 장면!")         # 과한 말투 줄임(ㄷㄷ 제거, !! → !)

    def test_tone_laughs_and_voice(self):
        p = fc.normalize(plan([(0, 3, "신난 멤버ㅋㅋㅋㅋ"), (5, 8, "알고 보니 다른 안무였음ㅋㅋ"), (10, 13, "친한가 봄ㅋㅋ")]), 60, 30)
        self.assertEqual([s.caption for s in p.segments], ["신난 멤버ㅋㅋ", "알고 보니 다른 안무였음ㅋㅋ", "친한가 봄"])
        q = fc.normalize(fc.FanClipPlan(title_top="a", title_accent="b", upload_title="t", description="d",
                                        segments=[fc.FanSegment(start=0, end=8, caption="상황", voice="나만 다름")]), 60, 30)
        self.assertEqual(q.segments[0].voice, "(나만 다름)")

    def test_too_short_is_rejected(self):
        with self.assertRaises(ValueError):
            fc.normalize(plan([(0, 1, ""), (5, 6, "")]), 200, 30)


class RenderTests(unittest.TestCase):
    def test_render_video_only_with_title_caption_credit(self):
        require_ffmpeg()
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg 없음")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "src.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:d=20:r=30",
                            "-f", "lavfi", "-i", "sine=f=440:d=20", "-shortest", "-c:v", "libx264", "-c:a", "aac",
                            str(src)], check=True)
            p = fc.normalize(plan([(1, 4, "엔딩 의상이 다 달라요"), (10, 13, ""), (15, 18.5, "댄서는 전원 검정")]), 20, 30)
            out = tmp / "final.mp4"
            info = fc.render(src, p, "출처 - 테스트 채널 · 무대", tmp / "work", out)
            self.assertEqual((info["segments"], info["captions"], info["audio"]), (3, 2, True))
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                                    "-of", "default=nw=1", str(out)], capture_output=True, text=True).stdout
            self.assertIn("width=1080", probe)
            self.assertIn("height=1920", probe)
            self.assertIn("codec_type=audio", probe)
            dur = float([l for l in probe.splitlines() if l.startswith("duration=")][0].split("=")[1])
            self.assertAlmostEqual(dur, 9.5, delta=0.3)

    def test_missing_credit_is_refused(self):
        with self.assertRaises(ValueError):
            fc.render(Path("x.mp4"), plan([(0, 8, "")]), "  ", Path(tempfile.gettempdir()) / "fc_none", Path("o.mp4"))


if __name__ == "__main__":
    unittest.main()
