"""2C: 장면별 실제 TTS 길이로 설계도·영상·자막 시간을 확정한다.

TTS·ffprobe·ffmpeg 는 가짜로 바꿔 네트워크·렌더 없이 확인한다. 실제 음성 검증은
scripts/verify_tts_timeline.py 가 한다.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.config import load_config, load_presets, merge_options
from app.pipeline import blueprint, run, script_split, timeline
from app.pipeline.models import SceneAudio, Scene, Script, Word
from app.pipeline.subtitles import words_to_lines

from tests.test_script_split import ECON, SHORT, plan_for


def _script(n: int, lengths: list[int] | None = None) -> Script:
    lengths = lengths or [30] * n
    return Script(topic="t", titles=["t"], description="d", hashtags=[], sources=[],
                  scenes=[Scene(narration="가" * k, image_prompt="p", on_screen_text=f"k{i}")
                          for i, k in enumerate(lengths)])


def _audio(durs: list[float], gap: float = 0.25) -> list[SceneAudio]:
    out, t = [], 0.0
    for i, d in enumerate(durs):
        out.append(SceneAudio(index=i, path=f"a{i}.mp3", duration=d, words=[], offset=round(t, 3)))
        t += d + gap
    return out


class FakeTTS:
    """문장 길이에 비례한 가짜 음성. fail_times 만큼 먼저 실패한다."""

    def __init__(self, fail_times: int = 0, empty: bool = False):
        self.calls = 0
        self.fail_times = fail_times
        self.empty = empty

    async def synthesize(self, text, out, voice):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("edge-tts 연결 끊김")
        out.write_bytes(b"" if self.empty else b"ID3" + b"x" * 100)
        # 마지막 단어 끝이 실제 길이보다 약간 길게 오는 경우도 흉내 낸다
        return [Word(text=w, start=i * 0.4, end=i * 0.4 + 0.5) for i, w in enumerate(text.split())]


def fake_len(path: Path) -> float:
    """가짜 음성 파일 길이: 파일 이름 번호로 정해 둔다."""
    return {"scene_00.mp3": 0.8, "scene_01.mp3": 14.0, "scene_02.mp3": 3.2}.get(Path(path).name, 2.0)


async def fake_probe(path):
    return fake_len(path)


async def no_trim(path):
    return 0.0


async def fake_concat(parts, out, gap=0.25, sample_rate=24000, tail=0.0):
    Path(out).write_bytes(b"ID3")
    offsets, t = [], 0.0
    for p in parts:
        offsets.append(round(t, 3))
        t += fake_len(p) + gap
    return offsets


class AlignTests(unittest.TestCase):
    def test_short_long_and_many_scenes(self):
        durs = [0.8, 14.0, 3.2, 2.0, 2.5, 4.1, 1.7, 6.3]
        bp = blueprint.from_script(_script(8))
        est = [s.estimated_duration for s in bp.scenes]
        out = blueprint.align_to_audio(bp, _audio(durs), gap=0.25)
        self.assertEqual(out.timing, "tts_aligned")
        self.assertEqual([s.estimated_duration for s in out.scenes], est)      # 예상치는 비교용으로 보존
        self.assertEqual([s.actual_tts_duration for s in out.scenes], durs)
        self.assertEqual(out.scenes[0].timeline_start, 0.0)
        self.assertEqual(out.scenes[0].timeline_end, 1.05)                      # 0.8 + 여백 0.25
        self.assertEqual(out.scenes[1].timeline_start, 1.05)
        self.assertEqual(out.scenes[1].speech_end, 15.05)
        for a, b in zip(out.scenes, out.scenes[1:]):
            self.assertEqual(a.timeline_end, b.timeline_start)                  # 빈틈·겹침 없음
            self.assertGreaterEqual(a.timeline_end, a.speech_end)               # 음성이 잘리지 않음
        last = out.scenes[-1]
        self.assertAlmostEqual(last.timeline_end - last.speech_end, 0.5)         # 마지막 여운만
        self.assertAlmostEqual(out.actual_duration, sum(durs) + 0.25 * 7 + 0.5, places=3)
        self.assertEqual(blueprint.scene_durations(out),
                         [round(d + 0.25, 3) for d in durs[:-1]] + [round(durs[-1] + 0.5, 3)])
        self.assertEqual(bp.timing, "estimated")                                # 원본은 그대로

    def test_scene_count_mismatch_and_bad_length_are_errors(self):
        bp = blueprint.from_script(_script(3))
        with self.assertRaisesRegex(ValueError, "장면 수"):
            blueprint.align_to_audio(bp, _audio([1.0, 2.0]), gap=0.25)
        with self.assertRaisesRegex(ValueError, "2번 장면"):
            blueprint.align_to_audio(bp, _audio([1.0, 0.0, 2.0]), gap=0.25)

    def test_estimated_blueprint_cannot_drive_render(self):
        with self.assertRaisesRegex(ValueError, "실제 음성"):
            blueprint.scene_durations(blueprint.from_script(_script(2)))

    def test_old_blueprint_json_still_loads_and_roundtrips(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            old = blueprint.from_script(_script(2)).model_dump()
            for s in old["scenes"]:
                for k in ("actual_tts_duration", "timeline_start", "speech_end", "timeline_end"):
                    s.pop(k)
            for k in ("actual_duration", "scene_gap", "tail"):
                old.pop(k)
            (job / blueprint.FILE).write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
            loaded = blueprint.load(job)
            self.assertIsNone(loaded.scenes[0].actual_tts_duration)
            aligned = blueprint.align_to_audio(loaded, _audio([1.5, 2.5]), gap=0.25)
            blueprint.save(job, aligned)
            again = blueprint.load(job)
        self.assertEqual(again.model_dump(), aligned.model_dump())

    def test_check_timeline_detects_drift(self):
        bp = blueprint.align_to_audio(blueprint.from_script(_script(2)), _audio([1.5, 2.5]), gap=0.25)
        good = {"scenes": [{"start": 0.0, "duration": 1.75}, {"start": 1.75, "duration": 3.0}]}
        blueprint.check_timeline(bp, good)
        with self.assertRaisesRegex(ValueError, "2번 장면"):
            blueprint.check_timeline(bp, {"scenes": [{"start": 0.0, "duration": 1.75},
                                                     {"start": 2.4, "duration": 3.0}]})
        with self.assertRaisesRegex(ValueError, "장면 수"):
            blueprint.check_timeline(bp, {"scenes": good["scenes"][:1]})


class SynthesizeTests(unittest.IsolatedAsyncioTestCase):
    def _cfg(self):
        return {"tts": {"voice": "v", "retries": 2, "retry_wait": 0}, "video": {"scene_gap": 0.25}}

    async def _run(self, tts, script, trim=no_trim):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(run, "get_tts", return_value=tts), \
                patch.object(run, "probe_duration", new=fake_probe), \
                patch.object(run, "trim_edge_silence", new=trim), \
                patch.object(run, "concat_audio", new=fake_concat):
            return await run._synthesize_scenes(self._cfg(), script, Path(folder), lambda *a: None)

    async def test_trimmed_lead_shifts_words_and_trim_error_keeps_original(self):
        async def cut(path):
            return 0.3
        script = Script(topic="t", titles=["t"], description="d", hashtags=[], sources=[],
                        scenes=[Scene(narration="하나 둘", image_prompt="p", on_screen_text="k"),
                                Scene(narration="셋", image_prompt="p", on_screen_text="k")])
        _, scenes = await self._run(FakeTTS(), script, trim=cut)
        self.assertEqual(scenes[0].words[0].start, 0.0)          # 0.0 - 0.3 → 0 으로
        self.assertAlmostEqual(scenes[0].words[1].start, 0.1)    # 0.4 - 0.3

        async def broken(path):
            raise RuntimeError("ffmpeg 없음")
        _, scenes = await self._run(FakeTTS(), script, trim=broken)
        self.assertEqual([s.duration for s in scenes], [0.8, 14.0])   # 원본 그대로 실측

    async def test_retry_then_success_uses_measured_length(self):
        tts = FakeTTS(fail_times=1)
        _, scenes = await self._run(tts, _script(3, [10, 60, 20]))
        self.assertEqual(tts.calls, 4)                                # 첫 장면만 한 번 더
        self.assertEqual([s.duration for s in scenes], [0.8, 14.0, 3.2])
        self.assertEqual([s.offset for s in scenes], [0.0, 1.05, 15.3])

    async def test_words_never_pass_scene_speech_end(self):
        _, scenes = await self._run(FakeTTS(), Script(
            topic="t", titles=["t"], description="d", hashtags=[], sources=[],
            scenes=[Scene(narration="하나 둘 셋", image_prompt="p", on_screen_text="k"),
                    Scene(narration="넷", image_prompt="p", on_screen_text="k")]))
        first = scenes[0]
        self.assertTrue(all(w.end <= first.offset + first.duration for w in first.words))
        lines = words_to_lines([s.words for s in scenes])
        self.assertLessEqual(lines[0]["end"], scenes[1].offset)          # 자막이 다음 장면으로 안 넘어감

    async def test_all_attempts_fail_gives_clear_error(self):
        tts = FakeTTS(fail_times=99)
        with self.assertRaises(run.TTSFailed) as ctx:
            await self._run(tts, _script(2))
        self.assertIn("1번 장면", str(ctx.exception))
        self.assertIn("3회 시도", str(ctx.exception))
        self.assertIn("연결 끊김", str(ctx.exception))
        self.assertEqual(tts.calls, 3)

    async def test_empty_audio_file_is_a_failure(self):
        with self.assertRaisesRegex(run.TTSFailed, "만들어지지 않았습니다"):
            await self._run(FakeTTS(empty=True), _script(2))

    async def test_length_measure_failure_is_not_faked(self):
        async def broken(path):
            raise RuntimeError("ffprobe 실패")
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(run, "get_tts", return_value=FakeTTS()), \
                patch.object(run, "trim_edge_silence", new=no_trim), \
                patch.object(run, "probe_duration", new=broken):
            with self.assertRaisesRegex(run.TTSFailed, "길이를 측정하지 못했습니다"):
                await run._synthesize_scenes(self._cfg(), _script(2), Path(folder), lambda *a: None)


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    """직접 대본 경로와 AI 대본 경로 모두 TTS 뒤에 실제 길이로 확정된 설계도를 저장한다."""

    def _cfg(self):
        cfg = merge_options(load_config(), load_presets(load_config())["engineering"], {})
        cfg["tts"]["retry_wait"] = 0
        return cfg

    def _patches(self):
        return (patch.object(run, "require_ffmpeg"), patch.object(run, "get_tts", return_value=FakeTTS()),
                patch.object(run, "probe_duration", new=fake_probe),
                patch.object(run, "concat_audio", new=fake_concat),
                patch.object(run, "trim_edge_silence", new=no_trim))

    async def _check(self, job: Path, result: dict, n: int):
        bp = blueprint.load(job)
        self.assertEqual(bp.timing, "tts_aligned")
        self.assertEqual(len(bp.scenes), n)
        self.assertEqual(bp.scenes[0].actual_tts_duration, 0.8)
        self.assertEqual(bp.scenes[1].actual_tts_duration, 14.0)
        self.assertEqual(result["blueprint"]["timing"], "tts_aligned")
        self.assertTrue(all(s.timeline_end >= s.speech_end for s in bp.scenes))

    async def test_direct_script_path(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            p1, p2, p3, p4, p5 = self._patches()
            with p1, p2, p3, p4, p5, patch.object(script_split, "ask_structured",
                                              new=AsyncMock(return_value=plan_for(SHORT))):
                result = await run.run_pipeline(job, "script", SHORT, self._cfg(),
                                                review=lambda s, p: _approve(s), until="tts")
            await self._check(job, result, 4)

    async def test_ai_topic_path(self):
        script = _script(5, [20, 60, 30, 25, 25])
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            seen = {}

            async def review(s, preview):
                seen.update(preview)
                return s, {}
            p1, p2, p3, p4, p5 = self._patches()
            with p1, p2, p3, p4, p5, \
                    patch.object(run.research, "research_topic", new=AsyncMock(return_value=[])), \
                    patch.object(run.script_split, "ask_structured",
                                 new=AsyncMock(side_effect=RuntimeError("테스트: AI 호출 없음"))), \
                    patch.object(run.scriptmod, "make_plan", new=AsyncMock(side_effect=RuntimeError("no plan"))), \
                    patch.object(run.scriptmod, "write_script", new=AsyncMock(return_value=script)):
                result = await run.run_pipeline(job, "topic", "경제 주제", self._cfg(), review=review, until="tts")
            self.assertEqual(seen["blueprint"]["timing"], "estimated")      # 검토 화면에는 예상치
            self.assertEqual(len(seen["blueprint"]["scenes"]), 5)
            await self._check(job, result, 5)

    async def test_tts_failure_stops_before_render(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            with patch.object(run, "require_ffmpeg"), patch.object(run, "get_tts", return_value=FakeTTS(fail_times=99)), \
                    patch.object(script_split, "ask_structured", new=AsyncMock(return_value=plan_for(ECON))):
                cfg = self._cfg()
                with self.assertRaises(run.TTSFailed):
                    await run.run_pipeline(job, "script", ECON, cfg, review=lambda s, p: _approve(s))
            self.assertFalse((job / "final.mp4").exists())
            self.assertFalse((job / timeline.FILE).exists())
            self.assertEqual(blueprint.load(job).timing, "estimated")       # 확정된 척하지 않는다


async def _approve(script):
    return script, {}


if __name__ == "__main__":
    unittest.main()
