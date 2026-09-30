"""2D: 장면별 화면 자동 선택. 분야 무관 규칙, 권리 대장, 카드 그리기, 자동·수동 두 경로.

AI·TTS·렌더는 가짜로 바꿔 네트워크·유료 호출 없이 확인한다. 실제 영상은 scripts/verify_visuals.py.
"""
from __future__ import annotations

import json
import tempfile
from contextlib import ExitStack
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image, ImageDraw

from app.config import load_config, load_presets, merge_options
from app.pipeline import blueprint, cards, run, script_split, timeline, visuals
from app.pipeline.models import Asset, PlannedScene, Scene, Script
from app.pipeline.script_split import SceneNote, SceneNotes, analyze_scene, short_phrase
from app.pipeline.sources import SourceRegistry
from app.pipeline.subtitles import wrap_title

from tests.test_script_split import SHORT, plan_for
from tests.test_tts_timeline import FakeTTS, fake_concat, fake_probe, no_trim

OK_RIGHTS = {"license": "my_channel", "rights_confirmed": True, "commercial_allowed": True,
             "adaptation_allowed": True, "third_party_rights_checked": True, "license_note": "내가 찍은 사진"}


def planned(narr: str, kind: str, **kw) -> PlannedScene:
    return PlannedScene(narration=narr, image_prompt="p", on_screen_text=kw.pop("emph", "강조"),
                        content_kind=kind, **kw)


def ai_script() -> Script:
    return Script(topic="주제", titles=["t"], description="d", hashtags=[], sources=[], scenes=[
        Scene(narration="고양이는 왜 상자를 좋아할까요?", image_prompt="cat box", on_screen_text="고양이는 왜 상자를 좋아할까요 정말 궁금하죠"),
        Scene(narration="좁은 공간은 몸을 숨기기에 안전하다고 느끼게 합니다.", image_prompt="cat", on_screen_text="안전한 은신처"),
        Scene(narration="실제로 상자를 준 고양이의 스트레스는 3배 빨리 줄었습니다.", image_prompt="study", on_screen_text="스트레스 감소"),
        Scene(narration="큰 상자보다 작은 상자를 더 좋아하는 경우가 많습니다.", image_prompt="boxes", on_screen_text="작은 상자"),
        Scene(narration="오늘 빈 상자 하나를 바닥에 놓아 보세요.", image_prompt="box", on_screen_text="상자 하나"),
    ])


class RuleTests(unittest.TestCase):
    def test_content_kinds_are_domain_neutral(self):
        self.assertEqual(analyze_scene("고양이는 왜 상자를 좋아할까요?", 0, 5)["content_kind"], "hook")
        num = analyze_scene("회원 수가 1년 만에 3배 늘었습니다.", 2, 5)
        self.assertEqual((num["content_kind"], num["key_number"]), ("trend", "3배"))
        self.assertEqual(analyze_scene("관람객은 1200명이었습니다.", 2, 5)["key_number"], "1200명")
        cmp_ = analyze_scene("서울은 여름에 덥고, 반면 제주는 바람이 시원합니다.", 2, 5)
        self.assertEqual(cmp_["content_kind"], "comparison")
        self.assertTrue(cmp_["compare_a"] and cmp_["compare_b"])
        self.assertEqual(analyze_scene("그래서 결국 방법은 하나입니다.", 4, 5)["content_kind"], "conclusion")

    def test_short_phrase_never_whole_sentence(self):
        long = "그래서 우리가 매일 아침 마시는 커피 한 잔에는 생각보다 훨씬 많은 사연이 숨어 있습니다."
        s = short_phrase(long)
        self.assertLessEqual(len(s), script_split.EMPHASIS_MAX)
        self.assertNotIn("그래서", s)
        self.assertEqual(short_phrase("판매량이 40퍼센트 증가했습니다.", "trend", "40%"), "40% 증가")
        self.assertTrue(short_phrase("이 사람은 도대체 왜 그런 선택을 했을까요?").endswith("?"))

    def test_title_wrap_keeps_inside_screen(self):
        lines = wrap_title("아주아주긴띄어쓰기없는문장이화면밖으로나가면안됩니다", 11)
        self.assertLessEqual(len(lines), 2)
        self.assertTrue(all(len(l) <= 11 for l in lines))


class AnnotateTests(unittest.IsolatedAsyncioTestCase):
    async def test_ai_notes_are_checked(self):
        notes = SceneNotes(scenes=[SceneNote(
            index=i, scene_type="Hook" if i == 0 else "핵심", content_kind=k, visual_type="generated_image",
            visual_description="d", emphasis_text=e, key_number=n, compare_a=a, compare_b=b,
            source_requirement="internal_generated", motion="zoom_in", transition="fade")
            for i, (k, e, n, a, b) in enumerate([
                ("hook", "고양이는 왜 상자를 좋아할까요 정말로 궁금합니다", "", "", ""),
                ("number", "안전", "99%", "", ""),                     # 대본에 없는 숫자 → 버림
                ("number", "3배 빨리", "3배", "", ""),
                ("comparison", "작은 상자", "", "큰 상자", "작은 상자"),
                ("conclusion", "상자 하나", "", "", "")])])
        with patch.object(script_split, "ask_structured", new=AsyncMock(return_value=notes)):
            script, method = await script_split.annotate_script({}, ai_script())
        self.assertEqual(method, "ai")
        s = script.scenes
        self.assertEqual([x.narration for x in s], [x.narration for x in ai_script().scenes])   # 나레이션 보존
        self.assertLessEqual(len(s[0].on_screen_text), script_split.EMPHASIS_MAX)             # 긴 문구 짧게
        self.assertEqual(s[1].key_number, "")                                                 # 지어낸 숫자 제거
        self.assertNotEqual(s[1].content_kind, "number")
        self.assertEqual((s[2].content_kind, s[2].key_number), ("number", "3배"))
        self.assertEqual((s[3].compare_a, s[3].compare_b), ("큰 상자", "작은 상자"))
        self.assertTrue(all(x.subtitle == x.narration for x in s))

    async def test_ai_failure_uses_rules_and_merges_to_eight(self):
        many = Script(topic="t", titles=["t"], description="d", hashtags=[], sources=[],
                      scenes=[Scene(narration=f"{i}번째 이야기입니다.", image_prompt="p", on_screen_text="")
                              for i in range(11)])
        with patch.object(script_split, "ask_structured", new=AsyncMock(side_effect=RuntimeError("down"))):
            script, method = await script_split.annotate_script({}, many)
        self.assertEqual(method, "rules")
        self.assertEqual(len(script.scenes), 8)
        self.assertEqual(" ".join(x.narration for x in script.scenes), " ".join(x.narration for x in many.scenes))
        self.assertEqual(script.scenes[0].content_kind, "number")   # "0번째" 숫자 → 숫자 장면 (규칙 판단)
        self.assertTrue(all(x.content_kind for x in script.scenes))


class PlanTests(unittest.TestCase):
    def _registry(self, folder: Path) -> SourceRegistry:
        return SourceRegistry(folder)

    def test_priority_rights_and_data_cards(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            reg = self._registry(job)
            ok = job / "ok.jpg"
            bad = job / "bad.jpg"
            for p in (ok, bad):
                Image.new("RGB", (100, 100)).save(p)
            reg.add(kind="image", origin="upload", path=str(ok), rights=OK_RIGHTS)
            reg.add(kind="image", origin="upload", path=str(bad))                   # 권리 불명
            scenes = [planned("도입", "hook"), planned("설명", "subject", visual_type="generated_image"),
                      planned("숫자 3배", "number", key_number="3배"),
                      planned("비교", "comparison", compare_a="A", compare_b="B"), planned("정리", "conclusion"),
                      planned("영상", "subject")]
            uploads = {0: Asset(path=str(ok), kind="image", name="scene_01_ok.jpg"),
                       1: Asset(path=str(bad), kind="image", name="bad.jpg")}
            d = visuals.plan_visuals(scenes, uploads, reg, ai_available=False, broll={5: str(ok)})
            self.assertEqual(d[0].resolved_visual_type, "upload_image")
            self.assertEqual(d[0].rights_status, "allowed")
            self.assertEqual(d[1].resolved_visual_type, "statement_card")         # 권리 불명 업로드 제외
            self.assertNotEqual(d[1].asset_path, str(bad))
            self.assertTrue(d[1].fallback_used)
            self.assertEqual(d[2].resolved_visual_type, "number_card")
            self.assertEqual(d[3].resolved_visual_type, "compare_card")
            self.assertEqual(d[4].resolved_visual_type, "summary_card")
            self.assertEqual(d[5].resolved_visual_type, "upload_video")
            self.assertTrue(all(x.selection_reason for x in d))
            with_ai = visuals.plan_visuals(scenes, {}, reg, ai_available=True)
            self.assertEqual(with_ai[1].resolved_visual_type, "ai_image")         # 그림이 유리한 장면만
            self.assertEqual(with_ai[2].resolved_visual_type, "number_card")      # 숫자는 카드가 더 분명

    def test_repeats_are_varied_without_changing_content(self):
        with tempfile.TemporaryDirectory() as folder:
            reg = self._registry(Path(folder))
            scenes = [planned(f"핵심 {i}", "claim") for i in range(4)]
            d = visuals.plan_visuals(scenes, {}, reg, ai_available=False)
            kinds = [x.resolved_visual_type for x in d]
            self.assertTrue(all(a != b for a, b in zip(kinds, kinds[1:])))          # 같은 문구 카드 연속 없음
            self.assertIn("이어지지 않게", d[1].selection_reason)
            nums = [planned(f"{i}배", "number", key_number=f"{i}배") for i in range(1, 3)]
            d2 = visuals.plan_visuals(nums, {}, reg, ai_available=False)
            self.assertEqual([x.resolved_visual_type for x in d2], ["number_card", "number_card"])  # 내용이 정한 카드는 유지
            self.assertIn("다른 배치", d2[1].selection_reason)
            self.assertEqual(visuals._variants(d2), [0, 1])


class MaterializeTests(unittest.IsolatedAsyncioTestCase):
    def _cfg(self, provider="none"):
        return {"images": {"width": 1080, "height": 1920, "provider": provider, "retries": 0}, "preset": {}}

    async def test_cards_uploads_and_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            reg = SourceRegistry(job)
            wide = job / "wide.jpg"
            Image.new("RGB", (1600, 900), (200, 50, 50)).save(wide)            # 가로 사진
            reg.add(kind="image", origin="upload", path=str(wide), rights=OK_RIGHTS)
            broken = job / "broken.jpg"
            broken.write_bytes(b"not an image")
            reg.add(kind="image", origin="upload", path=str(broken), rights=OK_RIGHTS)
            long_emph = "아주 긴 강조 문구가 들어와도 화면 밖으로 나가면 안 됩니다 정말로 길게 씁니다"
            scenes = [planned("도입", "hook", emph=long_emph), planned("사진", "subject"),
                      planned("깨진 파일", "subject"), planned("숫자", "trend", key_number="40%")]
            uploads = {1: Asset(path=str(wide), kind="image", name="scene_02.jpg"),
                       2: Asset(path=str(broken), kind="image", name="scene_03.jpg")}
            d = visuals.plan_visuals(scenes, uploads, reg, ai_available=False)
            d = await visuals.materialize(d, scenes, job, self._cfg(), reg)
            for x in d:
                with Image.open(x.asset_path) as im:
                    self.assertEqual(im.size, (1080, 1920))
                self.assertEqual(x.rights_status, "allowed")
                self.assertTrue(reg.by_path(x.asset_path).usable_in_video)
            self.assertIn("흐린 배경 위 원본 전체", d[1].selection_reason)       # 가로 사진은 잘라내지 않음
            self.assertEqual(d[2].asset_source, "internal_generated")            # 깨진 파일 → 카드
            self.assertTrue(d[2].fallback_used)
            self.assertEqual(d[3].resolved_visual_type, "trend_card")
            self.assertFalse(d[0].show_title)
            self.assertTrue(d[1].show_title)

    async def test_ai_failure_falls_back_to_card(self):
        class Broken:
            async def generate(self, prompt, out, w, h):
                raise RuntimeError("quota")
        with tempfile.TemporaryDirectory() as folder, patch.object(visuals, "get_images", return_value=Broken()):
            job = Path(folder)
            scenes = [planned("설명", "subject")]
            d = visuals.plan_visuals(scenes, {}, SourceRegistry(job), ai_available=True)
            d = await visuals.materialize(d, scenes, job, self._cfg("gemini"), SourceRegistry(job))
        self.assertEqual(d[0].resolved_visual_type, "statement_card")
        self.assertTrue(d[0].fallback_used)
        self.assertIn("AI 이미지 생성 실패", d[0].selection_reason)

    def test_long_text_fits_card_width(self):
        img = Image.new("RGB", (1080, 1920))
        draw = ImageDraw.Draw(img)
        max_w = 1080 * (1 - 2 * cards.SIDE)
        font, lines, _ = cards.fit_text(draw, "띄어쓰기없이아주길게이어지는강조문구가화면을넘치려고합니다" * 2, max_w, 500, 130)
        self.assertTrue(all(cards._width(draw, line, font) <= max_w + 1 for line in lines))
        self.assertLessEqual(len(lines), 3)


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    """자동 대본(주제)·직접 대본 두 경로 모두 화면 결정이 설계도에 남고, 2C 시간은 그대로다."""

    def _cfg(self):
        cfg = merge_options(load_config(), load_presets(load_config())["engineering"], {})
        cfg["tts"]["retry_wait"] = 0
        cfg["images"]["provider"] = "none"
        return cfg

    async def _run(self, job: Path, mode: str, text: str, extra):
        seen = {}

        async def review(s, preview):
            seen.update(preview)
            return s, {}
        with ExitStack() as stack:
            for p in [patch.object(run, "require_ffmpeg"), patch.object(run, "get_tts", return_value=FakeTTS()),
                      patch.object(run, "probe_duration", new=fake_probe),
                      patch.object(run, "concat_audio", new=fake_concat),
                      patch.object(run, "trim_edge_silence", new=no_trim),
                      patch.object(run.timelinemod, "render_timeline", new=AsyncMock(return_value=job / "final.mp4")),
                      patch.object(run, "make_thumbnail", new=AsyncMock()), *extra]:
                stack.enter_context(p)
            result = await run.run_pipeline(job, mode, text, self._cfg(), review=review)
        return result, seen

    async def _check(self, job: Path, result: dict, seen: dict):
        bp = blueprint.load(job)
        self.assertEqual(bp.timing, "tts_aligned")
        self.assertTrue(all(s.visual_decision for s in bp.scenes))
        self.assertTrue(all(s.content_kind for s in bp.scenes))
        manifest = json.loads((job / visuals.MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest), len(bp.scenes))
        for key in ("scene_id", "requested_visual_type", "resolved_visual_type", "asset_path", "asset_source",
                    "rights_status", "rights_reason", "selection_reason", "fallback_used"):
            self.assertIn(key, manifest[0])
        tl = timeline.load(job)
        blueprint.check_timeline(bp, tl)                                    # 2C 시간 보존
        for s, t in zip(bp.scenes, tl["scenes"]):
            self.assertEqual(Path(t["visual"]["path"]).name, Path(s.visual_decision.asset_path).name)
            if not s.visual_decision.show_title:
                self.assertEqual(t["title"], "")                            # 카드와 상단 키워드 중복 없음
        self.assertTrue(seen.get("visual_plan"))                            # 렌더 전 검토 화면에 미리보기
        self.assertTrue(all(len(s.emphasis_text) <= script_split.EMPHASIS_MAX for s in bp.scenes))

    async def test_auto_topic_path(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            result, seen = await self._run(job, "topic", "고양이와 상자", [
                patch.object(run.research, "research_topic", new=AsyncMock(return_value=[])),
                patch.object(run.scriptmod, "make_plan", new=AsyncMock(side_effect=RuntimeError("no plan"))),
                patch.object(run.scriptmod, "write_script", new=AsyncMock(return_value=ai_script())),
                patch.object(run.script_split, "ask_structured", new=AsyncMock(side_effect=RuntimeError("테스트: AI 없음")))])
            self.assertEqual(result["plan_method"], "rules")
            await self._check(job, result, seen)
            kinds = [s["resolved_visual_type"] for s in result["visual_plan"]]
            self.assertEqual(kinds[2], "trend_card")      # "3배 빨리 줄었습니다" → 숫자 + 감소 화살표
            self.assertEqual(kinds[3], "compare_card")    # "큰 상자보다 작은 상자"
            self.assertEqual(kinds[0], "hook_card")

    async def test_direct_script_path(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            result, seen = await self._run(job, "script", SHORT, [
                patch.object(script_split, "ask_structured", new=AsyncMock(return_value=plan_for(SHORT)))])
            await self._check(job, result, seen)

    async def test_blueprint_roundtrip_keeps_decisions(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder)
            await self._run(job, "script", SHORT, [
                patch.object(script_split, "ask_structured", new=AsyncMock(return_value=plan_for(SHORT)))])
            bp = blueprint.load(job)
            blueprint.save(job, bp)
            self.assertEqual(blueprint.load(job).model_dump(), bp.model_dump())


if __name__ == "__main__":
    unittest.main()
