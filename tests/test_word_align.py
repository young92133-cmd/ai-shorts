"""TTS 단어 경계 → 나레이션 단어 재정렬. 자막 글자는 항상 나레이션과 같아야 한다."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.pipeline import run
from app.pipeline.models import Word
from app.pipeline.subtitles import words_to_lines
from app.pipeline.tts.base import align_words

NARRATION = "우리가 본 사진은 사분의 일. 나머지 칠십오 퍼센트는 스펙트라예요."

# 실제 결과(output/20261005_171137_be9d)를 재현: 문장 끝을 넘는 "일. 나" 토큰, "머지" 누락
EDGE_BOUNDARIES = [
    Word(text="우리가", start=0.0, end=0.362),
    Word(text="본", start=0.374, end=0.6),
    Word(text="사진은", start=0.612, end=0.91),
    Word(text="사분의", start=0.922, end=1.255),
    Word(text="일. 나", start=1.267, end=1.9),
    Word(text="칠십오", start=2.3, end=2.8),
    Word(text="퍼센트는", start=2.812, end=3.4),
    Word(text="스펙트라예요", start=3.412, end=4.2),
]


class AlignWordsTest(unittest.TestCase):
    def test_merged_token_and_dropped_fragment(self):
        words = align_words(NARRATION, EDGE_BOUNDARIES)
        self.assertEqual([w.text for w in words], NARRATION.split())
        by = {w.text: w for w in words}
        # "일. 나" 토큰 시간을 "일." 과 "나머지" 가 나눠 갖는다
        self.assertAlmostEqual(by["일."].start, 1.267, places=3)
        self.assertLess(by["일."].end, by["나머지"].end)
        self.assertLessEqual(by["일."].end, by["나머지"].start)
        self.assertAlmostEqual(by["나머지"].end, 1.9, places=3)
        self.assertAlmostEqual(by["칠십오"].start, 2.3, places=3)
        # 시간은 순서대로, 겹치지 않게
        for a, b in zip(words, words[1:]):
            self.assertLessEqual(a.start, a.end)
            self.assertLessEqual(a.end, b.start + 1e-9)

    def test_subtitle_text_equals_narration(self):
        lines = words_to_lines(align_words(NARRATION, EDGE_BOUNDARIES))
        shown = " ".join(w["text"] for line in lines for w in line["words"])
        self.assertEqual(shown, " ".join(NARRATION.split()))
        self.assertEqual(" ".join(line["text"] for line in lines), " ".join(NARRATION.split()))

    def test_unmatched_word_gets_time_between_neighbours(self):
        bounds = [Word(text="하나", start=0.0, end=0.5), Word(text="셋", start=1.5, end=2.0)]
        words = align_words("하나 둘 셋", bounds)
        self.assertEqual([w.text for w in words], ["하나", "둘", "셋"])
        self.assertEqual((words[1].start, words[1].end), (0.5, 1.5))

    def test_exact_boundaries_unchanged(self):
        bounds = [Word(text="안녕하세요", start=0.1, end=0.6), Word(text="여러분", start=0.7, end=1.1)]
        words = align_words("안녕하세요, 여러분!", bounds)
        self.assertEqual([(w.text, w.start, w.end) for w in words],
                         [("안녕하세요,", 0.1, 0.6), ("여러분!", 0.7, 1.1)])

    def test_split_token_merges_into_one_word(self):
        bounds = [Word(text="스펙", start=0.0, end=0.3), Word(text="트라예요", start=0.3, end=0.9)]
        words = align_words("스펙트라예요.", bounds)
        self.assertEqual([(w.text, w.start, w.end) for w in words], [("스펙트라예요.", 0.0, 0.9)])


class SynthesizeOneAlignsTest(unittest.TestCase):
    def test_synthesize_one_returns_narration_words(self):
        class FakeEdge:
            async def synthesize(self, text, out, voice):
                Path(out).write_bytes(b"x")
                return list(EDGE_BOUNDARIES)

        async def fake_probe(_):
            return 4.3

        async def fake_trim(_):
            return 0.0

        with tempfile.TemporaryDirectory() as d, \
                patch.object(run, "probe_duration", fake_probe), \
                patch.object(run, "trim_edge_silence", fake_trim):
            words, dur = asyncio.run(run._synthesize_one(FakeEdge(), NARRATION, Path(d) / "a.mp3", "v", 1, 0))
        self.assertEqual(dur, 4.3)
        self.assertEqual([w.text for w in words], NARRATION.split())


if __name__ == "__main__":
    unittest.main()
