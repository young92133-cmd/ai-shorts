"""카드뉴스 · 인스타툰 · 하이브리드 캐러셀 (app/carousel) 테스트.

Phase 1 렌더러·스키마 / 2 Character Registry / 3 만화 컷 / 4 하이브리드 계획 / 5 all·CLI·자연어,
그리고 요구 7개 경로(주제→카드뉴스, 기사→카드뉴스, 주제→인스타툰, 주제→하이브리드, 원고→하이브리드,
쇼츠 회귀, all)를 Factory 명령으로 끝까지 돌린다. AI·검색·TTS·렌더는 모두 가짜다.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.carousel import characters as charmod, master as mastermod, planner, render, visuals as cvis
from app.carousel.mascot import draw_mascot
from app.carousel.render import PageAssets, PanelArt, render_page
from app.carousel.schema import (BUBBLE_POSITIONS, CARD_TYPES, COMIC_TYPES, CardPage, ComicBeat, ComicPage,
                                 Comparison, MasterContent, MasterFact, page_from_dict)
from app.carousel.templates import list_templates, load_template
from app.factory import __main__ as cli, core, state as st
from app.factory.intent import detect_output_format
from app.pipeline import run
from app.pipeline.models import ResearchDoc
from app.pipeline.sources import SourceRegistry

from tests.test_factory import FactoryTestCase, _quiet

LONG = ("보증금 3억을 예금에 넣으면 연 4% 기준 1,200만원, 한 달 100만원의 기회비용이 생깁니다. "
        "대출로 마련했다면 대출 이자가 곧 비용이고, 전세보증보험료와 중개수수료까지 더하면 실제 주거비는 생각보다 큽니다.")


def master(story: float = 0.5, **kw) -> MasterContent:
    return MasterContent(
        topic="전세 vs 월세", title="전세 vs 월세, 뭐가 유리할까?", subtitle="금리 4%대 주거비 계산", hook="월세가 무조건 손해일까요?",
        story_score=story, key_points=["전월세 전환율로 월세를 환산한다", "보증금에도 기회비용이 있다", "보증보험은 필수다"],
        facts=[MasterFact(text="법정 전환율 상한은 기준금리+2%p", source_index=1)],
        checklist=["등기부등본 확인", "확정일자 받기", "보증보험 가입"],
        comparison=Comparison(left_label="전세", right_label="월세", left_points=["목돈 필요"], right_points=["매달 지출"]),
        story_beats=["토리가 월세 인상 문자를 받는다", "전세로 옮길지 고민한다"], summary="숫자로 비교하면 답이 보인다",
        cta="저장하고 이사 전에 다시 보세요", sources=[{"title": "주거비 기사", "url": "https://news.example/1"}], **kw)


def png_size(path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size


# ---------- Phase 1: 스키마 · 템플릿 · 카드 렌더러 ----------

class SchemaTemplateTests(unittest.TestCase):
    def test_page_from_dict_picks_card_or_comic(self):
        self.assertIsInstance(page_from_dict({"type": "info_card", "headline": "a"}), CardPage)
        comic = page_from_dict({"type": "comic_scene", "panels": [{"character_id": "tory_01", "dialogue": "안녕"}]})
        self.assertIsInstance(comic, ComicPage)
        for f in ("character_id", "scene", "emotion", "pose", "dialogue", "background", "camera", "speech_bubble_position"):
            self.assertIn(f, comic.panels[0].model_dump())
        card = CardPage(type="cover")
        for f in ("type", "headline", "body", "visual_query", "layout", "source", "emphasis"):
            self.assertIn(f, card.model_dump())

    def test_three_templates_with_regions(self):
        ids = {t["id"] for t in list_templates()}
        self.assertTrue({"clean_info", "character_info", "comic_hybrid"} <= ids)
        for tid in ids:
            tpl = load_template(tid)
            self.assertEqual((tpl.width, tpl.height), (1080, 1350))
            for name in ("title", "body", "image", "footer", "character", "panel"):
                x0, y0, x1, y1 = tpl.box("info_card", name)
                self.assertTrue(0 <= x0 < x1 <= 1080 and 0 <= y0 < y1 <= 1350)

    def test_unknown_template_rejected(self):
        with self.assertRaises(ValueError):
            load_template("nope")


class CardRenderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _pages(self):
        return [CardPage(type="cover", label="부동산", headline="전세 vs 월세", body="부제"),
                CardPage(type="hook", headline="월세가 손해일까?", body="기회비용", emphasis="기회비용"),
                CardPage(type="info_card", label="POINT 1", headline="전환율", body=LONG, emphasis="기회비용"),
                CardPage(type="checklist", headline="체크", items=["등기부등본", "확정일자", "보증보험"]),
                CardPage(type="comparison", headline="비교", compare=Comparison(left_label="전세", right_label="월세")),
                CardPage(type="quote", headline="집은 사는 곳", body="칼럼"),
                CardPage(type="summary", headline="정리", items=["a", "b"]),
                CardPage(type="cta", headline="저장하세요", items=["저장", "공유", "댓글"])]

    def test_every_card_type_renders_4x5_png(self):
        photo = self.dir / "photo.jpg"
        Image.new("RGB", (1200, 800), "skyblue").save(photo)
        pages = self._pages()
        self.assertEqual({p.type for p in pages}, set(CARD_TYPES))
        for tid in ("clean_info", "character_info", "comic_hybrid"):
            tpl = load_template(tid)
            guide = draw_mascot(charmod.TORY["mascot"], "happy", "pointing")
            for i, page in enumerate(pages, 1):
                out = self.dir / f"{tid}_{i}.png"
                info = render_page(page, tpl, out, PageAssets(image=photo if i == 3 else None, guide=guide,
                                                              index=i, total=len(pages)))
                self.assertFalse(info["fallback_used"], (tid, page.type, info.get("fallback_reason")))
                self.assertEqual(png_size(out), (1080, 1350))

    def test_long_korean_text_is_wrapped_inside_box(self):
        from PIL import ImageDraw
        d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        fnt, lines, lh = render.fit(d, LONG * 3, 800, 300, 46, 30, 6)
        self.assertLessEqual(len(lines), 6)
        self.assertTrue(all(d.textlength(l, font=fnt) <= 800 for l in lines))
        self.assertTrue(lines[-1].endswith("…"))

    def test_no_image_uses_graphic_or_text_layout(self):
        tpl = load_template("clean_info")
        info = render_page(CardPage(type="info_card", headline="h", body=LONG), tpl, self.dir / "a.png", PageAssets())
        self.assertEqual(info["image_use"], "text_only")
        info = render_page(CardPage(type="info_card", headline="h", body="b", emphasis="4%"), tpl, self.dir / "b.png",
                           PageAssets())
        self.assertEqual(info["image_use"], "graphic")

    def test_failed_page_falls_back_without_raising(self):
        tpl = load_template("clean_info")
        with patch.dict(render.RENDERERS, {"info_card": lambda *a: 1 / 0}):
            info = render_page(CardPage(type="info_card", headline="제목", body="본문"), tpl, self.dir / "x.png",
                               PageAssets())
        self.assertTrue(info["fallback_used"])
        self.assertIn("ZeroDivisionError", info["fallback_reason"])
        self.assertEqual(png_size(self.dir / "x.png"), (1080, 1350))


# ---------- Phase 2: Character Registry ----------

class CharacterRegistryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_load_and_list(self):
        charmod.ensure_default(self.root)
        tory = charmod.get_character("tory_01", self.root)
        self.assertEqual(tory.name, "토리")
        for key in ("appearance", "default_outfit", "personality", "visual_style", "reference_images"):
            self.assertIn(key, tory.model_dump())
        charmod.save_character({**charmod.TORY, "id": "mori_02", "name": "모리"}, self.root)
        self.assertEqual({c.id for c in charmod.list_characters(self.root)}, {"tory_01", "mori_02"})

    def test_ascii_id_enforced(self):
        with self.assertRaises(ValueError):
            charmod.save_character({**charmod.TORY, "id": "토리"}, self.root)
        with self.assertRaises(KeyError):
            charmod.get_character("../x", self.root)

    def test_prompt_locks_identity_and_forbids_text(self):
        tory = charmod.save_character(charmod.TORY, self.root)
        beat = ComicBeat(character_id="tory_01", emotion="happy", pose="pointing", background="office")
        prompt = charmod.character_prompt(tory, beat)
        for part in ("round black glasses", "chestnut brown", "mint green cardigan", "identical face", "No text"):
            self.assertIn(part, prompt)
        self.assertEqual(charmod.cache_key(tory, beat), charmod.cache_key(tory, beat.model_copy()))
        self.assertNotEqual(charmod.cache_key(tory, beat), charmod.cache_key(tory, beat.model_copy(update={"emotion": "sad"})))

    def test_reference_image_matched_by_emotion_pose(self):
        tory = charmod.save_character({**charmod.TORY, "reference_images": ["happy_pointing.png", "sad.png"]}, self.root)
        for name in ("happy_pointing.png", "sad.png"):
            Image.new("RGBA", (10, 10)).save(self.root / "tory_01" / name)
        self.assertEqual(charmod.reference_for(tory, "happy", "pointing", self.root).name, "happy_pointing.png")
        self.assertEqual(charmod.reference_for(tory, "sad", "standing", self.root).name, "sad.png")
        self.assertIsNone(charmod.reference_for(tory, "angry", "standing", self.root))


# ---------- Phase 3: 만화 컷 ----------

class ComicTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        charmod.ensure_default(self.dir / "chars")

    def tearDown(self):
        self._tmp.cleanup()

    def test_mascot_is_transparent_cutout(self):
        img = draw_mascot(charmod.TORY["mascot"], "surprised", "waving")
        self.assertEqual(img.mode, "RGBA")
        self.assertEqual(img.getchannel("A").getextrema()[0], 0)

    def test_comic_types_and_bubble_positions_render(self):
        tpl = load_template("comic_hybrid")
        art = PanelArt(kind="cutout", image=draw_mascot(charmod.TORY["mascot"]), source="mascot")
        for t in COMIC_TYPES:
            for pos in BUBBLE_POSITIONS:
                beats = [ComicBeat(character_id="tory_01", dialogue="이번 달 월세가 또 올랐어요… 어떡하죠?",
                                   speech_bubble_position=pos, camera=cam) for cam in ("medium", "close_up")]
                page = ComicPage(type=t, panels=beats[:2 if t == "dialogue_scene" else 1], caption="설명 문장", headline="캡션")
                info = render_page(page, tpl, self.dir / f"{t}_{pos}.png", PageAssets(panels=[art, art]))
                self.assertFalse(info["fallback_used"], (t, pos, info.get("fallback_reason")))

    async def test_ai_provider_is_cached_and_failure_falls_back_to_mascot(self):
        calls = []

        class FakeProvider:
            async def generate(self, prompt, out, w, h):
                calls.append(prompt)
                Image.new("RGB", (w, h), "pink").save(out)

        reg = SourceRegistry(self.dir)
        with patch.object(cvis, "get_images", return_value=FakeProvider()):
            artist = cvis.CharacterArtist(job_dir=self.dir, registry=reg, provider_cfg={"images": {"provider": "fake"}},
                                          default_id="tory_01", root=self.dir / "chars")
        beat = ComicBeat(character_id="tory_01", emotion="happy", pose="pointing")
        a1, a2 = await artist.art(beat, 1), await artist.art(beat, 2)
        self.assertEqual((a1.source, a2.source), ("ai_generated", "ai_generated"))
        self.assertEqual(len(calls), 1)                        # 같은 감정·자세는 캐시
        self.assertIn("No text", calls[0])

        class Broken:
            async def generate(self, *a):
                raise RuntimeError("quota")
        with patch.object(cvis, "get_images", return_value=Broken()):
            artist = cvis.CharacterArtist(job_dir=self.dir, registry=reg, provider_cfg={"images": {"provider": "x"}},
                                          default_id="tory_01", root=self.dir / "chars")
        art = await artist.art(beat.model_copy(update={"emotion": "sad"}), 3)
        self.assertEqual(art.source, "mascot")

    async def test_unknown_character_uses_default_and_pinned_upload_wins(self):
        reg = SourceRegistry(self.dir)
        up = self.dir / "uploads"
        up.mkdir()
        Image.new("RGB", (800, 1000), "white").save(up / "toon_02_flow.png")
        Image.new("RGB", (800, 1000), "white").save(up / "toon_03_norights.png")
        reg.add(kind="image", origin="upload", path=str(up / "toon_02_flow.png"), title="flow",
                rights=core._own_rights("ai_generated", "Flow 에서 직접 생성", True))
        reg.add(kind="image", origin="upload", path=str(up / "toon_03_norights.png"), title="x")
        pinned = cvis.pinned_uploads(self.dir, reg)
        self.assertEqual(list(pinned), [2])                     # 권리 확인 안 된 업로드는 쓰지 않는다
        artist = cvis.CharacterArtist(job_dir=self.dir, registry=reg, provider_cfg=None, default_id="tory_01",
                                      root=self.dir / "chars")
        art = await artist.art(ComicBeat(character_id="nobody_9"), 1)
        self.assertEqual(art.source, "mascot")
        art = await artist.art(ComicBeat(character_id="tory_01"), 2, pinned[2])
        self.assertEqual((art.source, art.kind), ("upload", "scene"))


# ---------- Phase 4: 하이브리드 계획 ----------

class PlannerTests(unittest.IsolatedAsyncioTestCase):
    def test_mix_ratio_by_content_character(self):
        self.assertEqual(planner.mix_ratio("hybrid", 0.1), {"card": 80, "comic": 20})
        self.assertEqual(planner.mix_ratio("hybrid", 0.5), {"card": 50, "comic": 50})
        self.assertEqual(planner.mix_ratio("hybrid", 0.9), {"card": 20, "comic": 80})
        self.assertEqual(planner.mix_ratio("card_news", 0.9)["comic"], 0)

    def test_hybrid_default_skeleton(self):
        types = planner.skeleton("hybrid", master(0.5), 8)
        self.assertEqual(len(types), 8)
        self.assertEqual((types[0], types[-1]), ("cover", "cta"))
        self.assertEqual(types[1], "comic_scene")
        self.assertIn("info_card", types)
        self.assertEqual(types[-2], "summary")

    def test_ratio_shifts_with_story_score(self):
        comics = lambda s: sum(t in COMIC_TYPES for t in planner.skeleton("hybrid", master(s), 8))  # noqa: E731
        self.assertLess(comics(0.1), comics(0.5))
        self.assertLess(comics(0.5), comics(0.9))
        self.assertGreaterEqual(comics(0.1), 1)
        card = planner.skeleton("card_news", master(0.9), 8)
        self.assertFalse(any(t in COMIC_TYPES for t in card))
        toon = planner.skeleton("insta_toon", master(0.2), 7)
        self.assertTrue(all(t in COMIC_TYPES for t in toon[1:-1]))

    def test_page_count_clamped(self):
        self.assertEqual(len(planner.skeleton("card_news", master(), 3)), 6)
        self.assertEqual(len(planner.skeleton("card_news", master(), 30)), 10)

    async def test_rules_when_ai_fails(self):
        with patch.object(planner, "ask_structured", new=AsyncMock(side_effect=RuntimeError("x"))):
            plan = await planner.plan_pages({"provider": "claude"}, master(0.5), "hybrid", template="comic_hybrid",
                                            character=charmod.CharacterBible.model_validate(charmod.TORY),
                                            valid_chars={"tory_01"})
        self.assertEqual(plan.method, "rules")
        kinds = {p.kind for p in plan.pages[1:-1]}
        self.assertEqual(kinds, {"card", "comic"})
        self.assertTrue(all(b.character_id == "tory_01" for p in plan.pages if p.kind == "comic" for b in p.panels))

    async def test_ai_plan_is_normalized(self):
        draft = planner.DraftPlan(pages=[
            planner.DraftPage(type="info_card", headline="커버 없이 시작", emphasis="없는 문구"),
            planner.DraftPage(type="comic_scene", panels=[ComicBeat(character_id="ghost", emotion="weird", pose="flying",
                                                                    speech_bubble_position="middle", dialogue="안녕" * 50)]),
            planner.DraftPage(type="comparison", headline="비교 데이터 없음"),
            planner.DraftPage(type="bogus_type"),
            planner.DraftPage(type="checklist", headline="항목 없는 체크리스트"),
            planner.DraftPage(type="summary", headline="정리", items=["a"]),
        ])
        with patch.object(planner, "ask_structured", new=AsyncMock(return_value=draft)):
            plan = await planner.plan_pages({"provider": "claude"}, master(), "hybrid", template="comic_hybrid",
                                            character=charmod.CharacterBible.model_validate(charmod.TORY),
                                            valid_chars={"tory_01"})
        self.assertEqual(plan.pages[0].type, "cover")
        self.assertEqual(plan.pages[-1].type, "cta")
        self.assertTrue(6 <= len(plan.pages) <= 10)
        comic = next(p for p in plan.pages if p.kind == "comic")
        b = comic.panels[0]
        self.assertEqual((b.character_id, b.emotion, b.pose, b.speech_bubble_position),
                         ("tory_01", "neutral", "standing", "top_right"))
        self.assertLessEqual(len(b.dialogue), 60)
        self.assertNotIn("comparison", [p.type for p in plan.pages])   # 비교 데이터 없는 비교 카드는 정보 카드로
        self.assertEqual(plan.pages[1].emphasis, "")

    async def test_card_news_never_has_comics(self):
        draft = planner.DraftPlan(pages=[planner.DraftPage(type="cover", headline="c"),
                                         *[planner.DraftPage(type="comic_scene", panels=[ComicBeat(character_id="tory_01",
                                                                                                   dialogue="대사")])] * 5,
                                         planner.DraftPage(type="cta", headline="e")])
        with patch.object(planner, "ask_structured", new=AsyncMock(return_value=draft)):
            plan = await planner.plan_pages({"provider": "claude"}, master(), "card_news", template="clean_info",
                                            character=None, valid_chars=set())
        self.assertTrue(all(p.kind == "card" for p in plan.pages))

    async def test_master_rules_without_ai(self):
        docs = [ResearchDoc(title="주거비 기사", url="https://n/1", text=LONG)]
        with patch.object(mastermod, "ask_structured", new=AsyncMock(side_effect=RuntimeError("x"))):
            m, how = await mastermod.build_master({}, "전세 vs 월세", docs)
        self.assertEqual(how, "rules")
        self.assertTrue(m.key_points)
        self.assertEqual(m.facts[0].source_index, 1)
        self.assertEqual(m.sources[0]["url"], "https://n/1")


# ---------- Phase 5: 자연어 · CLI ----------

class IntentCliTests(unittest.TestCase):
    def test_natural_language_formats(self):
        cases = {"이 주제로 카드뉴스 만들어줘": "card_news", "이 기사로 인스타툰 만들어줘": "insta_toon",
                 "이 주제로 카드뉴스랑 인스타툰을 섞어서 만들어줘": "hybrid", "카드뉴스랑 만화를 섞어서 만들어줘": "hybrid",
                 "이 주제로 쇼츠와 하이브리드 카드뉴스 둘 다 만들어줘": "all", "전부 만들어줘": "all",
                 "고양이 쇼츠 만들어줘": "shorts", "이 유튜브 영상으로 카드뉴스 만들어줘": "card_news",
                 "하이브리드로 만들어줘": "hybrid", "45초로 만들어줘": "shorts"}
        for text, want in cases.items():
            self.assertEqual(detect_output_format(text), want, text)

    def _cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, json.loads(out.getvalue())

    def test_format_flag_keeps_old_tone_values(self):
        with patch.object(core, "make", new=AsyncMock(return_value={"status": "render_complete"})) as make:
            self._cli("make", "--topic", "x", "--format", "story")
        self.assertEqual(make.await_args.kwargs["content_format"], "story")
        self.assertNotIn("output_format", make.await_args.kwargs)      # 쇼츠 호출 모양 그대로
        with patch.object(core, "make", new=AsyncMock(return_value={"status": "render_complete"})) as make:
            self._cli("make", "--topic", "x", "--format", "hybrid", "--tone", "issue", "--pages", "7",
                      "--template", "character_info")
        kw = make.await_args.kwargs
        self.assertEqual((kw["output_format"], kw["content_format"], kw["pages"], kw["template"]),
                         ("hybrid", "issue", 7, "character_info"))

    def test_characters_command(self):
        code, data = self._cli("characters", "list")
        self.assertEqual(code, 0)
        self.assertIn("tory_01", [c["id"] for c in data["characters"]])
        code, data = self._cli("characters", "show", "nobody_1")
        self.assertEqual(code, 2)


# ---------- 요구 7개 경로 (Factory make 끝까지) ----------

class CarouselMakeTests(FactoryTestCase):
    def setUp(self):
        super().setUp()
        self.research.return_value = [ResearchDoc(title="주거비 기사", url="https://example.com/rent", text=LONG)]
        self.fetch_articles.return_value = ([ResearchDoc(title="전세 기사", url="https://news.example/1", text=LONG)], [])
        self.master_ai = AsyncMock(side_effect=RuntimeError("테스트: AI 없음"))
        self.plan_ai = AsyncMock(side_effect=RuntimeError("테스트: AI 없음"))
        for p in (patch.object(mastermod, "ask_structured", new=self.master_ai),
                  patch.object(planner, "ask_structured", new=self.plan_ai)):
            self.stack.enter_context(p)

    def _check(self, out, fmt):
        self.assertEqual(out["status"], "render_complete", out.get("message"))
        self.assertEqual(out["output_format"], fmt)
        folder = Path(out["dir"])
        pngs = sorted(folder.glob("card_*.png"))
        self.assertTrue(6 <= len(pngs) <= 10)
        self.assertTrue(all(png_size(p) == (1080, 1350) for p in pngs))
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["page_count"], len(pngs))
        for rec in manifest["pages"]:
            for key in ("page", "file", "type", "headline", "image", "source", "fallback_used"):
                self.assertIn(key, rec)
        self.assertTrue((folder / "sources.json").is_file())
        self.assertEqual(manifest["pages"][0]["type"], "cover")
        self.assertEqual(manifest["pages"][-1]["type"], "cta")
        return manifest

    async def test_1_topic_to_card_news(self):
        with patch.object(core.runmod, "run_pipeline", new=AsyncMock()) as shorts:
            out = await core.make(topic="전세 vs 월세", output_format="card_news", log=_quiet)
        shorts.assert_not_awaited()                                    # 쇼츠 엔진은 부르지 않는다
        m = self._check(out, "card_news")
        self.assertTrue(all(p["kind"] == "card" for p in m["pages"]))
        self.research.assert_awaited_once()
        state = st.load(Path(out["project_dir"]))
        self.assertEqual(state["request"]["output_format"], "card_news")
        self.assertEqual(out["next_action"], "done")
        srcs = json.loads((Path(out["dir"]) / "sources.json").read_text(encoding="utf-8"))
        self.assertIn("https://example.com/rent", [s["url"] for s in srcs])

    async def test_2_article_url_to_card_news(self):
        out = await core.make(url="https://news.example/1", output_format="card_news", log=_quiet)
        self.fetch_articles.assert_awaited()
        self._check(out, "card_news")

    async def test_3_topic_to_insta_toon(self):
        out = await core.make(topic="월세 인상 고민", output_format="insta_toon", log=_quiet)
        m = self._check(out, "insta_toon")
        comics = [p for p in m["pages"] if p["kind"] == "comic"]
        self.assertGreaterEqual(len(comics), 4)
        self.assertTrue(all(p["characters"] == ["tory_01"] for p in comics))
        self.assertTrue(all(pn["art"] == "mascot" for p in comics for pn in p["panels"]))

    async def test_4_topic_to_hybrid_with_ai_plan(self):
        self.master_ai.side_effect = None
        self.master_ai.return_value = master(0.9)                       # 스토리형 → 만화 비중 높게
        out = await core.make(topic="전세 vs 월세", output_format="hybrid", log=_quiet)
        m = self._check(out, "hybrid")
        self.assertEqual({p["kind"] for p in m["pages"][1:-1]}, {"card", "comic"})
        self.assertGreater(m["mix"]["comic"], 50)
        self.assertEqual(m["master_method"], "ai")

    async def test_5_script_to_hybrid_without_research(self):
        out = await core.make(script_text="월세가 또 올랐다.\n" + LONG, output_format="hybrid", log=_quiet)
        self._check(out, "hybrid")
        self.research.assert_not_awaited()

    async def test_6_shorts_regression(self):
        out = await core.make(topic="고양이가 상자를 좋아하는 이유", log=_quiet)
        self.assertEqual(out["status"], "render_complete")
        self.assertEqual(out["resolution"], "1080x1920")
        job = Path(out["project_dir"])
        self.assertTrue((job / "final.mp4").is_file())
        self.assertFalse(any((job / f).exists() for f in ("card_news", "hybrid", "insta_toon", "master.json")))
        self.master_ai.assert_not_awaited()

    async def test_7_all_makes_shorts_and_hybrid_with_one_research(self):
        out = await core.make(topic="전세 vs 월세", output_format="all", log=_quiet)
        self.assertEqual(out["status"], "render_complete", out)
        self.assertEqual(out["shorts_status"], "render_complete")
        self.assertTrue(Path(out["final_video"]).is_file())
        self.assertEqual(out["carousel"]["status"], "complete")
        self.assertEqual(len(list(Path(out["carousel"]["dir"]).glob("card_*.png"))), len(out["carousel"]["pages"]))
        self.research.assert_awaited_once()                             # 조사는 한 번만
        state = st.load(Path(out["project_dir"]))
        self.assertIn("carousel_manifest", state["outputs"])
        info = core.inspect(out["project_id"], "carousel")
        self.assertEqual(info["carousel"]["format"], "hybrid")

    async def test_all_keeps_carousel_when_shorts_fails(self):
        from tests.test_tts_timeline import FakeTTS
        with patch.object(run, "get_tts", return_value=FakeTTS(fail_times=99)):
            out = await core.make(topic="전세 vs 월세", output_format="all", log=_quiet)
        self.assertEqual(out["status"], "partial_failure")
        self.assertEqual(out["carousel"]["status"], "complete")
        self.assertEqual(out["next_action"], "resume")                  # 쇼츠는 저장된 대본으로 이어서

    async def test_natural_language_request_routes_format(self):
        out = await core.make(topic="전세 vs 월세", request_text="이 주제로 인스타툰 만들어줘", log=_quiet)
        self.assertEqual(out["output_format"], "insta_toon")

    async def test_research_file_input(self):
        f = self.root / "research.json"
        f.write_text(json.dumps([{"title": "기존 조사", "url": "https://r.example/1", "text": LONG}], ensure_ascii=False),
                     encoding="utf-8")
        out = await core.make(research_file=str(f), output_format="card_news", log=_quiet)
        self._check(out, "card_news")
        self.research.assert_not_awaited()

    async def test_licensed_image_used_and_unverified_image_dropped(self):
        async def fake_resolve(*, job_dir, registry, script, **kw):
            found = {}
            for i, s in enumerate(script.scenes):
                if i in kw.get("skip", set()):
                    continue
                path = job_dir / f"img_{i}.jpg"
                Image.new("RGB", (900, 600), "green").save(path)
                if i == 0:     # 표지만 권리 확인되어 대장에 usable 로 등록
                    registry.add(kind="image", origin="resolved", path=str(path), url="https://commons.example/1",
                                 rights={"license": "cc0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                                         "rights_confirmed": True, "commercial_allowed": True, "adaptation_allowed": True,
                                         "third_party_rights_checked": True, "credit": "사진: A / CC0 / Commons"})
                found[i] = {"kind": "image", "path": str(path), "credit": "사진: A / CC0 / Commons",
                            "page_url": "https://commons.example/1"}
            return {"scenes": found, "report": {"providers": ["wikimedia_commons"]}}

        draft = planner.DraftPlan(pages=[
            planner.DraftPage(type="cover", headline="전세 vs 월세", visual_query="apartment building"),
            planner.DraftPage(type="info_card", headline="전환율", body="b", visual_query="calculator"),
            *[planner.DraftPage(type="info_card", headline=f"p{i}", body="b") for i in range(4)],
            planner.DraftPage(type="cta", headline="저장")])
        self.plan_ai.side_effect = None
        self.plan_ai.return_value = draft
        with patch.object(run.source_resolver, "resolve", new=fake_resolve):
            out = await core.make(topic="전세 vs 월세", output_format="card_news", log=_quiet)
        m = self._check(out, "card_news")
        self.assertEqual(m["pages"][0]["image"]["credit"], "사진: A / CC0 / Commons")
        self.assertIsNone(m["pages"][1]["image"])                      # 대장에 근거 없는 사진은 쓰지 않는다
        self.assertEqual(out["image_pages"], [1])
        reg = SourceRegistry(Path(out["project_dir"]))
        used = [x for x in reg.items.values() if x.url == "https://commons.example/1"][0]
        self.assertEqual((used.usage, used.scene_ids), ("visual", [1]))
        self.assertIn("CC0", (Path(out["dir"]) / "caption.txt").read_text(encoding="utf-8"))

    async def test_invalid_requests(self):
        for kwargs in ({"topic": "x", "output_format": "card_news", "review": True},
                       {"topic": "x", "output_format": "card_news", "pages": 3},
                       {"topic": "x", "output_format": "hybrid", "template": "nope"},
                       {"topic": "x", "output_format": "insta_toon", "character": "nobody_1"},
                       {"topic": "x", "output_format": "poster"}):
            with self.assertRaises(core.FactoryError, msg=str(kwargs)):
                await core.make(log=_quiet, **kwargs)

    async def test_resume_rejects_carousel_project(self):
        out = await core.make(topic="x", output_format="card_news", log=_quiet)
        with self.assertRaises(core.FactoryError):
            await core.resume(out["project_id"], log=_quiet)
        exported = await core.export(out["project_id"], log=_quiet)
        self.assertIn("carousel_dir", exported["files"])


if __name__ == "__main__":
    unittest.main()
