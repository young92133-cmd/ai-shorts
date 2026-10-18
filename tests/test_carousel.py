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
        # 기본 캐릭터는 브랜드 캐릭터 햄토리치, 등록된 포즈 그림(reference)을 쓴다 (2026-10-08)
        self.assertTrue(all(p["characters"] == ["hamtorich_01"] for p in comics))
        self.assertTrue(all(pn["art"] == "reference" for p in comics for pn in p["panels"]))
        out = await core.make(topic="월세 인상 고민", output_format="insta_toon", character="tory_01", log=_quiet)
        m = self._check(out, "insta_toon")                          # 토리는 그대로 쓸 수 있다
        self.assertTrue(all(pn["art"] == "mascot" for p in m["pages"] if p["kind"] == "comic" for pn in p["panels"]))

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


class BrandCharacterTests(unittest.TestCase):
    """햄토리치: 마스터 시트 + 투명 포즈 8장. 컷의 감정·자세에 맞는 그림을 고르고, 다른 모습으로 대체하지 않는다."""

    def setUp(self):
        self.bible = charmod.get_character("hamtorich_01")

    def test_bible_links_master_sheet_and_eight_transparent_poses(self):
        self.assertEqual(charmod.BRAND_DEFAULT, "hamtorich_01")
        self.assertTrue(charmod.master_reference(self.bible).is_file())
        self.assertEqual(len(self.bible.poses), 8)
        self.assertFalse(self.bible.mascot_fallback)
        for pose in self.bible.poses:
            img = Image.open(charmod.character_dir(self.bible.id) / pose.file)
            self.assertEqual(img.mode, "RGBA")
            self.assertEqual(img.getchannel("A").getextrema()[0], 0)    # 배경 투명
        self.assertIn("master/design_sheet.png", charmod.lock_text(self.bible))
        self.assertTrue(charmod.get_character("tory_01"))                # 토리는 남아 있다

    def test_pose_matches_emotion_then_pose(self):
        pick = lambda e, p: charmod.reference_for(self.bible, e, p).name  # noqa: E731
        self.assertEqual(pick("happy", "pointing"), "happy_pointing.png")
        self.assertEqual(pick("worried", "thinking"), "worried_hands.png")
        self.assertEqual(pick("thinking", "explaining"), "thinking_document.png")
        self.assertEqual(pick("surprised", "waving"), "happy_cheering.png")
        self.assertEqual(pick("confident", "arms_crossed"), "happy_thumbs_up.png")
        self.assertEqual(pick("neutral", "unknown_pose"), "happy_front.png")

    def test_close_up_stays_inside_panel(self):
        tpl = load_template("comic_hybrid")
        art = PanelArt(kind="cutout", image=Image.open(charmod.reference_for(self.bible, "thinking", "explaining")).convert("RGBA"))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "p.png"
            page = ComicPage(type="dialogue_scene", panels=[ComicBeat(character_id="hamtorich_01", dialogue="a"),
                                                            ComicBeat(character_id="hamtorich_01", camera="close_up", dialogue="b")])
            render_page(page, tpl, out, PageAssets(panels=[art, art]))
            img = Image.open(out).convert("RGB")
            x0, y0, x1, y1 = tpl.box("dialogue_scene", "panel")
            below = img.crop((x0, y1 + 8, x1, min(tpl.height, y1 + 40)))
            self.assertLess(len(set(below.getdata())), 6)                 # 패널 아래로 그림이 새지 않는다


class BenchmarkVisualTests(unittest.TestCase):
    """2026-10-08 인스타툰 벤치마크 반영: 훅 표지, 만화 효과, 의인화 이름표 캐릭터, 두 인물 컷, 배경 라이브러리, 그림 생성."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_hook_cover_and_two_character_panel_render(self):
        from app.carousel import nametag
        tpl = load_template("hamtorich_toon")
        bible = charmod.get_character("hamtorich_01")
        guide = Image.open(charmod.reference_for(bible, "worried", "standing")).convert("RGBA")
        cover = CardPage(type="cover", headline="월급은 그대로인데 장바구니만 2.9% 올랐다?!", emphasis="2.9%", part="1화",
                         character_emotion="worried")
        info = render_page(cover, tpl, self.dir / "c.png", PageAssets(guide=guide))
        self.assertEqual((info["fallback_used"], info["image_use"]), (False, "character"))
        tag = PanelArt(kind="cutout", image=nametag.draw_tag_character("물가", "confident"), source="nametag")
        main = PanelArt(kind="cutout", image=guide, source="reference", partner=tag)
        page = ComicPage(type="comic_scene", panels=[ComicBeat(character_id="hamtorich_01", emotion="surprised", dialogue="너 때문이지?!",
                                                               partner="tag:물가", partner_dialogue="나만 오른 건 아닌데~")])
        info = render_page(page, tpl, self.dir / "p.png", PageAssets(panels=[main]))
        self.assertFalse(info["fallback_used"], info.get("fallback_reason"))

    def test_effects_and_moods_for_every_emotion(self):
        from app.carousel.effects import apply_mood, draw_effects, mood_for
        img = Image.new("RGB", (400, 400), "white")
        for emo in ("neutral", "happy", "surprised", "worried", "thinking", "confident", "sad", "angry"):
            draw_effects(img, (0, 0, 400, 400), (200, 200), emo)
        self.assertEqual(mood_for("원룸 밤", "happy"), "night")
        self.assertEqual(mood_for("", "angry"), "crisis")
        self.assertNotEqual(apply_mood(img, "night").getpixel((5, 5)), img.getpixel((5, 5)))

    def test_nametag_character_and_partner_lookup(self):
        import asyncio
        from app.carousel import nametag
        self.assertTrue(nametag.is_tag("tag:금리"))
        self.assertEqual(nametag.label_of("tag:한국은행입니다"), "한국은행입니")
        art_dir = self.dir
        artist = cvis.CharacterArtist(job_dir=art_dir, registry=SourceRegistry(art_dir), provider_cfg=None, default_id="hamtorich_01")
        beat = ComicBeat(character_id="hamtorich_01", emotion="worried", partner="tag:물가", partner_emotion="angry")
        art = asyncio.run(artist.art(beat, 1))
        self.assertEqual((art.source, art.partner.source), ("reference", "nametag"))
        missing = asyncio.run(artist.art(beat.model_copy(update={"partner": "nobody_99"}), 1))
        self.assertIsNone(missing.partner)                    # 없는 상대를 기본 캐릭터로 바꿔 두 번 그리지 않는다

    def test_background_library_uses_only_approved_matching_scenes(self):
        from app.carousel import backgrounds
        Image.new("RGB", (100, 125), "blue").save(self.dir / "night.png")
        Image.new("RGB", (100, 125), "yellow").save(self.dir / "day.png")
        backgrounds.save_index([{"id": "n", "file": "night.png", "tags": ["원룸"], "mood": "night", "approved": True},
                                {"id": "d", "file": "day.png", "tags": ["원룸"], "mood": "day", "approved": True},
                                {"id": "x", "file": "day.png", "tags": ["은행"], "mood": "day", "approved": False}], self.dir)
        self.assertEqual(backgrounds.pick("원룸 밤", root=self.dir).name, "night.png")
        self.assertEqual(backgrounds.pick("원룸", root=self.dir).name, "day.png")
        self.assertIsNone(backgrounds.pick("은행 창구", root=self.dir))      # 승인 전 배경은 쓰지 않는다
        self.assertIsNone(backgrounds.pick("우주", root=self.dir))

    def test_asset_generation_with_fake_provider_registers_unapproved(self):
        import asyncio
        import shutil
        from app.carousel import asset_gen
        root, bg = self.dir / "chars", self.dir / "bg"
        shutil.copytree(charmod.character_dir("hamtorich_01"), root / "hamtorich_01")
        calls = []

        class Fake:
            async def generate(self, prompt, out, w, h, **kw):
                calls.append(kw)
                img = Image.new("RGB", (800, 800), "white")
                from PIL import ImageDraw
                ImageDraw.Draw(img).ellipse([250, 200, 550, 700], fill=(218, 148, 85), outline=(60, 40, 30), width=8)
                img.save(out)
        plan = asset_gen.load_plan("brand_v1")
        todo = asset_gen.jobs(plan, root=root, bg_root=bg)
        quote = asset_gen.estimate(todo)
        self.assertEqual((quote["images"], quote["won_estimate"]), (54, 54 * 49))
        self.assertEqual([j["kind"] for j in todo[:1]] + [j["kind"] for j in todo[-1:]], ["background", "persona"])  # 우선순위
        result = asyncio.run(asset_gen.generate("brand_v1", provider=Fake(), root=root, bg_root=bg,
                                                items=["surprised_round_mouth", "studio_room_day"], log=lambda m: None))
        self.assertEqual(sorted(result["generated"]), ["studio_room_day", "surprised_round_mouth"])
        self.assertTrue(all(c["references"] for c in calls))          # 마스터 시트를 참조로 보낸다
        self.assertEqual(Image.open(bg / "studio_room_day.png").size, (1080, 1350))
        pose = Image.open(root / "hamtorich_01" / "poses" / "surprised_round_mouth.png")
        self.assertEqual(pose.mode, "RGBA")
        self.assertEqual(pose.getpixel((5, 5))[3], 0)                 # 흰 배경이 지워졌다
        bible = charmod.get_character("hamtorich_01", root)
        new = [p for p in bible.poses if p.file == "poses/surprised_round_mouth.png"][0]
        self.assertFalse(new.approved)
        self.assertNotEqual(charmod.reference_for(bible, "surprised", "standing", root).name, "surprised_round_mouth.png")
        asset_gen.approve(["hamtorich_01/poses/surprised_round_mouth.png"], root=root)
        bible = charmod.get_character("hamtorich_01", root)
        self.assertEqual(charmod.reference_for(bible, "surprised", "standing", root).name, "surprised_round_mouth.png")

    def test_generate_cli_quotes_cost_without_calling_api(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch("app.pipeline.images.gemini.GeminiImages.generate") as gen:
            code = cli.main(["characters", "generate", "--pick", "surprised_round_mouth"])
        data = json.loads(out.getvalue())
        self.assertEqual((code, data["status"], data["images"], data["items"]), (0, "estimate", 1, ["surprised_round_mouth"]))
        gen.assert_not_called()


class FreeRenderingTests(unittest.TestCase):
    """무료 렌더링 강화 (2026-10-09): 코드로 그린 원근 장면, 사용자 그림 받은편지함."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_every_scene_type_draws_with_depth(self):
        from app.carousel import scenes
        for text in ("원룸 밤", "거실", "마트 계산대", "은행 창구", "부동산", "회사 사무실", "카페", "퇴근길 골목 노을",
                     "아파트 단지", "지하철 출근길", "뉴스 스튜디오", ""):
            img = scenes.draw_scene((400, 450), text)
            self.assertEqual(img.size, (400, 450))
            self.assertGreater(len(set(img.resize((40, 45)).getdata())), 12, text)    # 단색 배경이 아니다
        self.assertEqual(scenes.scene_type("마트 계산대"), "mart")
        self.assertEqual(scenes.time_of("원룸 밤"), "night")

    def test_inbox_registers_backgrounds_and_poses_and_keeps_unknown_files(self):
        from app.carousel import backgrounds, inbox
        import shutil
        box, root, bg = self.dir / "inbox", self.dir / "chars", self.dir / "bg"
        box.mkdir()
        shutil.copytree(charmod.character_dir("hamtorich_01"), root / "hamtorich_01")
        Image.new("RGB", (1600, 900), (120, 160, 200)).save(box / "bg_원룸_밤.png")
        pose = Image.new("RGB", (800, 800), "white")
        from PIL import ImageDraw
        ImageDraw.Draw(pose).ellipse([250, 200, 550, 700], fill=(218, 148, 85), outline=(60, 40, 30), width=8)
        pose.save(box / "햄토리치_놀람_서있음.png")
        pose.save(box / "다람_걱정_지갑.png")
        Image.new("RGB", (100, 100), "red").save(box / "아무거나.png")
        result = inbox.import_inbox(inbox=box, root=root, bg_root=bg)
        kinds = sorted(a["kind"] for a in result["added"])
        self.assertEqual(kinds, ["background", "pose", "pose"])
        self.assertEqual([s["file"] for s in result["skipped"]], ["아무거나.png"])
        self.assertTrue((box / "아무거나.png").exists())                         # 분류 못 한 파일은 지우지 않는다
        self.assertEqual(Image.open(backgrounds.pick("원룸 밤", root=bg)).size, (1080, 1350))
        ham = charmod.get_character("hamtorich_01", root)
        self.assertTrue(charmod.reference_for(ham, "surprised", "standing", root).name.startswith("user_surprised"))
        daram = next(c for c in charmod.list_characters(root) if c.name == "다람")
        self.assertEqual(daram.poses[0].emotion, "worried")
        self.assertEqual(Image.open(charmod.character_dir(daram.id, root) / daram.poses[0].file).getpixel((3, 3))[3], 0)


class StoryRenderingQualityTests(unittest.TestCase):
    """2026-10-09 품질 개선: 흰 배경 제거가 캐릭터 안쪽 흰색을 지우지 않는지, 카메라·효과음·3컷·장면 표지."""

    def test_white_background_removal_keeps_shirt_eyes_and_fur(self):
        from app.carousel.asset_gen import remove_white_background
        for name in ("happy_front.png", "thinking_document.png"):
            orig = Image.open(charmod.character_dir("hamtorich_01") / "poses" / name).convert("RGBA")
            white = Image.new("RGBA", orig.size, (255, 255, 255, 255))
            white.alpha_composite(orig)
            out = remove_white_background(white.convert("RGB"), size=orig.width)
            o = orig.crop(orig.getchannel("A").point(lambda v: 255 if v > 128 else 0).getbbox())
            r = out.crop(out.getchannel("A").point(lambda v: 255 if v > 128 else 0).getbbox()).resize(o.size)
            ao, ar = o.getchannel("A").load(), r.getchannel("A").load()
            rgb = o.convert("RGB").load()
            inner_white = lost = 0
            for y in range(0, o.height, 3):
                for x in range(0, o.width, 3):
                    if ao[x, y] > 128 and min(rgb[x, y]) > 225:
                        inner_white += 1
                        lost += ar[x, y] <= 128
            self.assertGreater(inner_white, 1000, name)
            self.assertLess(lost / inner_white, 0.01, name)            # 셔츠·눈 하이라이트·크림 털은 남는다

    def test_story_page_with_three_panels_cameras_sfx_and_scene_cover(self):
        tpl = load_template("hamtorich_toon")
        bible = charmod.get_character("hamtorich_01")
        art = lambda e, p: PanelArt(kind="cutout", image=Image.open(charmod.reference_for(bible, e, p)).convert("RGBA"))  # noqa: E731
        page = ComicPage(type="comic_scene", panels=[
            ComicBeat(character_id="hamtorich_01", emotion="happy", dialogue="월급 들어왔다!", sfx="띠링!", camera="wide",
                      background="퇴근길 골목 노을"),
            ComicBeat(character_id="hamtorich_01", emotion="worried", dialogue="빠듯하다…", camera="extreme_close_up",
                      background="원룸 밤", sfx="털썩"),
            ComicBeat(character_id="hamtorich_01", emotion="thinking", dialogue="정말 다 올랐을까?", background="원룸 밤")])
        with tempfile.TemporaryDirectory() as d:
            info = render_page(page, tpl, Path(d) / "p.png", PageAssets(panels=[art("happy", "phone"), art("worried", "standing"),
                                                                               art("thinking", "chin")]))
            self.assertEqual((info["fallback_used"], info["panels"]), (False, 3))
            cover = CardPage(type="cover", layout="scene:마트 계산대", headline="몇 개 안 샀는데 계산대에서 얼어붙었다",
                             body="범인은 9월 물가?", part="1화", character_emotion="worried")
            info = render_page(cover, tpl, Path(d) / "c.png", PageAssets(guide=art("worried", "standing").image))
            self.assertFalse(info["fallback_used"], info.get("fallback_reason"))


class StoryWriterTests(unittest.IsolatedAsyncioTestCase):
    """자동 스토리 작가 (2026-10-09): 무료 규칙 기본, Claude 선택, 검증 실패 시 자동 채택 금지."""

    FACTS = [
        {"fact_id": "f1", "claim": "9월 소비자물가지수는 전월대비 0.3%, 전년동월대비 2.9% 각각 상승", "source_title": "국가데이터처 「9월 소비자물가동향」", "source_url": "https://mods.go.kr/x"},
        {"fact_id": "f2", "claim": "생활물가지수는 전월대비 0.7%, 전년동월대비 2.5% 각각 상승", "source_title": "국가데이터처 「9월 소비자물가동향」", "source_url": "https://mods.go.kr/x"},
        {"fact_id": "f4", "claim": "신선식품지수는 전월대비 2.7% 상승, 전년동월대비 3.3% 하락", "source_title": "국가데이터처 「9월 소비자물가동향」", "source_url": "https://mods.go.kr/x"},
    ]

    def facts(self):
        from app.carousel.story_writer import VerifiedFact
        return [VerifiedFact.model_validate(f) for f in self.FACTS]

    async def test_rule_writer_follows_story_structure_and_facts_only(self):
        from app.carousel import story_writer as sw
        plan, master, draft, report = await sw.write_story("9월 소비자물가와 내 장바구니", self.facts())
        self.assertEqual([s.role for s in draft.scenes], list(sw.ROLES))
        self.assertEqual(len(plan.pages), 8)
        self.assertEqual((plan.pages[0].type, plan.pages[-1].type), ("cover", "cta"))
        self.assertEqual(report["facts_used"], ["f1", "f2", "f4"])                     # 반전(하락) 사실이 해결 장면에
        captions = [p.caption for p in plan.pages if isinstance(p, ComicPage) and p.caption]
        claims = {f["claim"] for f in self.FACTS}
        self.assertTrue(captions and all(set(c.split(". ")) <= claims for c in captions))   # 사실 상자는 원문 그대로
        comics = [p for p in plan.pages if isinstance(p, ComicPage)]
        self.assertGreaterEqual(sum(1 for p in comics for b in p.panels if b.partner), 3)   # 상대역이 여러 장면에
        self.assertGreaterEqual(len({b.camera for p in comics for b in p.panels}), 3)       # 구도가 다양
        self.assertGreaterEqual(len({b.background for p in comics for b in p.panels}), 4)   # 장소 전환
        self.assertFalse([p for p in comics if p.type == "explanation_scene" and not any(b.partner or b.sfx for b in p.panels)][1:])

    async def test_rule_writer_profiles_for_other_topics(self):
        from app.carousel import story_writer as sw
        cases = {"기준금리 인상과 내 대출 이자": "금리", "전세 재계약 앞둔 직장인": "전세", "월급날 통장 관리": "월급"}
        for topic, tag in cases.items():
            facts = [sw.VerifiedFact(fact_id="a", claim=f"{topic} 관련 지표는 전년동월대비 1.5% 상승"),
                     sw.VerifiedFact(fact_id="b", claim="관련 지수는 전월대비 0.4% 하락")]
            plan, _, draft, _ = await sw.write_story(topic, facts)
            self.assertEqual(draft.rival_tag, tag, topic)
            self.assertEqual(sw.validate_story(draft, facts), [])

    async def test_claude_writer_is_optional_and_rejected_drafts_are_not_used(self):
        from app.carousel import story_writer as sw
        good = sw.rule_draft("9월 소비자물가", self.facts())
        with patch("app.pipeline.llm.ask_structured", new=AsyncMock(return_value=good)) as ask:
            plan, *_ = await sw.write_story("9월 소비자물가", self.facts(), writer="claude", llm={"provider": "claude"})
        ask.assert_awaited_once()
        self.assertEqual(len(plan.pages), 8)
        bad = good.model_copy(deep=True)
        bad.scenes[1].panels[0].line = "물가가 15% 올랐대!"                               # 근거 없는 숫자
        bad.scenes[3].fact_ids = ["f9"]                                                  # 검증되지 않은 id
        with patch("app.pipeline.llm.ask_structured", new=AsyncMock(return_value=bad)):
            with self.assertRaises(sw.StoryRejected) as e:
                await sw.write_story("9월 소비자물가", self.facts(), writer="claude", llm={"provider": "claude"})
        self.assertTrue(any("15" in r for r in e.exception.reasons))
        self.assertTrue(any("f9" in r for r in e.exception.reasons))
        with patch("app.pipeline.llm.ask_structured", new=AsyncMock(side_effect=AssertionError("규칙 모드는 AI 를 부르지 않는다"))):
            await sw.write_story("9월 소비자물가", self.facts(), writer="rules")

    def test_toon_cli_rejected_story_makes_no_png(self):
        from app.carousel import story_writer as sw
        good = sw.rule_draft("9월 소비자물가", self.facts())
        bad = good.model_copy(deep=True)
        bad.title = "물가 99% 폭등"
        with tempfile.TemporaryDirectory() as d:
            facts = Path(d) / "facts.json"
            facts.write_text(json.dumps(self.FACTS, ensure_ascii=False), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with patch.object(core, "output_root", return_value=Path(d)), \
                 patch("app.pipeline.llm.ask_structured", new=AsyncMock(return_value=bad)), \
                 redirect_stdout(out), redirect_stderr(err):
                code = cli.main(["toon", "--topic", "9월 소비자물가", "--facts", str(facts), "--writer", "claude"])
            data = json.loads(out.getvalue())
            self.assertEqual((code, data["status"]), (1, "rejected"))
            self.assertFalse(list(Path(d).rglob("card_*.png")))
            self.assertTrue(list(Path(d).rglob("story_rejected.json")))


class CarouselPreservationTests(unittest.TestCase):
    def test_unapproved_default_and_legacy_reference_require_approval(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            folder = root / "pending_01" / "poses"
            folder.mkdir(parents=True)
            image = folder / "happy_standing.png"
            Image.new("RGBA", (40, 40), (200, 100, 50, 255)).save(image)
            for legacy in (False, True):
                with self.subTest(legacy=legacy):
                    bible = charmod.CharacterBible(
                        id="pending_01", name="검토 전 캐릭터", default_pose="poses/happy_standing.png",
                        reference_images=["poses/happy_standing.png"] if legacy else [],
                        poses=[charmod.PoseAsset(file="poses/happy_standing.png", emotion="happy",
                                                pose="standing", approved=False)])
                    self.assertIsNone(charmod.reference_for(bible, "happy", "standing", root))
                    self.assertIsNone(charmod.reference_for(bible, "neutral", "unknown", root))
                    bible.poses[0].approved = True
                    self.assertEqual(charmod.reference_for(bible, "happy", "standing", root), image)
                    self.assertEqual(charmod.reference_for(bible, "neutral", "unknown", root), image)

    def test_inbox_preserves_originals_with_the_same_name(self):
        import datetime
        from app.carousel import inbox
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            box = root / "inbox"
            box.mkdir()
            incoming = box / "bg_원룸_밤.png"
            originals = []
            for color in ("red", "blue"):
                Image.new("RGB", (40, 50), color).save(incoming)
                originals.append(incoming.read_bytes())
                result = inbox.import_inbox(inbox=box, root=root / "characters", bg_root=root / "backgrounds")
                self.assertEqual(len(result["added"]), 1)
                self.assertEqual(result["skipped"], [])
                self.assertFalse(incoming.exists())
            archive = box / "_done" / datetime.date.today().isoformat()
            self.assertCountEqual([p.read_bytes() for p in archive.iterdir()], originals)

    def test_generic_source_is_not_labeled_as_official_original(self):
        with tempfile.TemporaryDirectory() as d:
            page = ComicPage(type="explanation_scene", panels=[ComicBeat(character_id="")],
                             caption="개인 블로그의 설명", source="개인 블로그")
            with patch.object(render, "pill", wraps=render.pill) as label:
                info = render_page(page, load_template("hamtorich_toon"), Path(d) / "page.png", PageAssets())
            self.assertFalse(info["fallback_used"])
            labels = [call.args[2] for call in label.call_args_list]
            self.assertIn("근거 자료", labels)
            self.assertNotIn("공식 통계 원문", labels)


class BalancedWrapTests(unittest.TestCase):
    """2026-10-16 실제 제작 점검: 말풍선·제목의 마지막 줄에 한 단어만 남지 않게 (예: '…보는 / 거죠', '…출근은 / 29일')."""

    def test_same_line_count_without_orphan_word(self):
        d = Image.new("RGB", (10, 10))
        draw = render.ImageDraw.Draw(d)
        fnt = render.font(48)
        text = "이 사진, 오늘만 보는 거죠"
        width = draw.textlength("이 사진, 오늘만 보는", font=fnt) + 4
        greedy = render._wrap(draw, text, fnt, width)
        self.assertEqual(greedy[-1], "거죠")
        lines = render.balanced(draw, text, fnt, width, greedy)
        self.assertEqual(len(lines), len(greedy))
        self.assertGreater(len(lines[-1].split()), 1)
        self.assertEqual(" ".join(lines), text)
        cut = ["가나다", "라마…"]
        self.assertEqual(render.balanced(draw, "가나다 라마바사", fnt, width, cut), cut)   # 말줄임 줄은 그대로


class ToonQualityTests(unittest.TestCase):
    """2026-10-18 인스타툰 품질: 상대역 모양 구별 · 장면 시간대 · 표정 그림 일치 기록 · 말풍선 높이 측정."""

    def test_partner_shapes_are_distinct(self):
        from app.carousel import nametag
        self.assertEqual([nametag.shape_for(x) for x in ("월급", "잔액", "자동이체", "물가")], ["bill", "coin", "card", "egg"])
        imgs = [nametag.draw_tag_character(x, "happy") for x in ("월급", "잔액", "자동이체")]
        self.assertTrue(all(im.size == (600, 780) and im.mode == "RGBA" for im in imgs))
        self.assertEqual(len({im.tobytes() for im in imgs}), 3)
        self.assertNotEqual(nametag.color_for("월급"), nametag.color_for("잔액"))

    def test_scene_time_matches_story(self):
        from app.carousel import scenes
        from PIL import ImageStat
        self.assertEqual(scenes.time_of("원룸 침실 아침, 햇빛"), "morning")
        self.assertEqual(scenes.time_of("원룸 밤, 불 꺼진 방"), "night")
        lum = lambda t: ImageStat.Stat(scenes.draw_scene((300, 300), t, mood="night").convert("L")).mean[0]
        self.assertLess(lum("원룸 밤, 불 꺼진 방"), lum("원룸 밤, 작은 조명") - 15)
        self.assertNotEqual(scenes.draw_scene((300, 300), "출근길 지하철").tobytes(),
                            scenes.draw_scene((300, 300), "회사 사무실").tobytes())

    def test_pose_match_marks_substitutes(self):
        bible = charmod.get_character("hamtorich_01")
        for emotion, want in (("happy", "exact"), ("sad", "similar"), ("angry", "similar")):
            ref = charmod.reference_for(bible, emotion, "standing")
            self.assertEqual(charmod.pose_match(bible, emotion, ref), want, emotion)
        self.assertEqual(charmod.pose_match(bible, "happy", None), "none")
        from app.carousel.pipeline import pose_gaps
        recs = [{"page": 2, "panels": [{"character_id": "hamtorich_01", "emotion": "sad", "pose_match": "similar"}]},
                {"page": 5, "panels": [{"character_id": "hamtorich_01", "emotion": "sad", "pose_match": "substitute"},
                                       {"character_id": "hamtorich_01", "emotion": "happy", "pose_match": "exact"}]}]
        self.assertEqual(pose_gaps(recs), [{"character": "hamtorich_01", "emotion": "sad", "pages": [2, 5]}])

    def test_bubble_height_is_measured_before_drawing(self):
        tpl = load_template("hamtorich_toon", "insta_toon")
        canvas = Image.new("RGB", (1080, 600), "white")
        box = (40, 40, 600, 220)
        self.assertEqual(render.bubble_bottom(canvas, tpl, "", box), 40)
        short = render.bubble_bottom(canvas, tpl, "네!", box)
        long = render.bubble_bottom(canvas, tpl, "이번 달은 정말 꼭 모아 보려고 했는데 벌써 다 나갔어요", box)
        self.assertLess(short, long)
        self.assertLessEqual(long, 220)


if __name__ == "__main__":
    unittest.main()
