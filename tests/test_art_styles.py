"""그림체(art_styles)·여러 캐릭터·참고 이미지 그림체 (2026-10-21). 모두 무료 렌더, AI·네트워크 없음."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from app.carousel import characters as charmod, render
from app.carousel.mascot import draw_mascot
from app.carousel.render import PageAssets, PanelArt, render_page
from app.carousel.schema import CardPage, ComicBeat, ComicPage, EMOTIONS
from app.carousel.style_ref import create_from_references
from app.carousel.templates import list_art_styles, load_template

STYLES = ("cute_daily", "simple_info", "pastel", "clean_webtoon")


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


class ArtStyleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _comic(self, tpl, name: str, char: str = "tory_01") -> Path:
        bible = charmod.get_character(char)
        art = PanelArt(kind="cutout", image=draw_mascot(bible.mascot, "surprised", "standing"), source="mascot")
        page = ComicPage(type="comic_scene", panels=[ComicBeat(character_id=char, emotion="surprised", background="원룸 밤",
                                                               dialogue="관리비가 또 나왔어요?", sfx="헉!")])
        out = self.dir / f"{name}.png"
        info = render_page(page, tpl, out, PageAssets(panels=[art], index=2, total=8))
        self.assertFalse(info["fallback_used"], info.get("fallback_reason"))
        return out

    def test_default_style_is_exactly_the_template(self):
        plain, default = load_template("hamtorich_toon", "insta_toon"), load_template("hamtorich_toon", "insta_toon", "default")
        self.assertEqual((plain.palette, plain.style, plain.art), (default.palette, default.style, default.art))
        self.assertEqual(_md5(self._comic(plain, "a")), _md5(self._comic(default, "b")))
        with self.assertRaises(ValueError):
            load_template("hamtorich_toon", "insta_toon", "no_such_style")

    def test_each_style_really_changes_the_picture(self):
        """이름만 바뀌는 기능이 아니라 그림(배경·선·말풍선·컷)이 달라져야 한다."""
        ids = {s["id"] for s in list_art_styles()}
        self.assertTrue(set(STYLES) <= ids)
        base = _md5(self._comic(load_template("comic_hybrid", "insta_toon"), "base"))
        seen = {base}
        for sid in STYLES:
            tpl = load_template("comic_hybrid", "insta_toon", sid)
            seen.add(_md5(self._comic(tpl, sid)))
            card = render_page(CardPage(type="info_card", headline="연체는 가장 큰 감점 요인", body="결제일 자동이체가 1순위."),
                               tpl, self.dir / f"card_{sid}.png", PageAssets(index=3, total=8))
            self.assertFalse(card["fallback_used"], card.get("fallback_reason"))
        self.assertEqual(len(seen), len(STYLES) + 1)        # 그림체마다 결과 그림이 모두 다르다

    def test_scene_modes_produce_distinct_backgrounds(self):
        from app.carousel.scenes import draw_scene
        src = draw_scene((360, 300), "원룸 밤", mood="night")
        outs = {}
        for sid in STYLES:
            outs[sid] = render.art_scene(src.copy(), load_template("comic_hybrid", "insta_toon", sid)).tobytes()
        self.assertEqual(len(set(outs.values())), len(STYLES))       # 모두 다르고, cute_daily(detailed)는 원본 배경 그대로
        self.assertEqual(outs["cute_daily"], src.tobytes())

    def test_mascot_line_and_face_options_keep_default(self):
        bible = charmod.get_character("tory_01")
        a = draw_mascot(bible.mascot, "worried", "thinking")
        self.assertEqual(a.tobytes(), draw_mascot(dict(bible.mascot), "worried", "thinking").tobytes())
        thin = draw_mascot({**bible.mascot, "line_scale": 0.6, "ink": "#3A3F4B"}, "worried", "thinking")
        simple = draw_mascot({**bible.mascot, "face": "simple"}, "worried", "thinking")
        self.assertEqual(len({a.tobytes(), thin.tobytes(), simple.tobytes()}), 3)

    def test_new_characters_draw_every_emotion_consistently(self):
        ids = {c.id for c in charmod.list_characters()}
        self.assertTrue({"hamtorich_01", "tory_01", "minji_01", "dot_01"} <= ids)
        for cid in ("minji_01", "dot_01"):
            b = charmod.get_character(cid)
            for emo in EMOTIONS:
                one = draw_mascot(b.mascot, emo, "standing")
                self.assertEqual(one.size, (600, 780))
                self.assertEqual(one.tobytes(), draw_mascot(b.mascot, emo, "standing").tobytes())   # 같은 작품에서 같은 모습
        minji, dot = (draw_mascot(charmod.get_character(c).mascot, "happy", "standing") for c in ("minji_01", "dot_01"))
        self.assertNotEqual(minji.tobytes(), dot.tobytes())

    def test_style_from_reference_images(self):
        """참고 이미지의 색·밝기·선 비율만 재서 그림체를 만든다 (이미지는 복사하지 않음)."""
        refs = []
        for k in range(2):
            im = Image.new("RGB", (400, 500), (250, 247, 240))
            d = ImageDraw.Draw(im)
            for y in range(40, 480, 60):
                d.line([(20, y), (380, y + 10)], fill=(30, 30, 40), width=3)
            d.rectangle([60, 120, 200, 300], outline=(30, 30, 40), width=4, fill=(120, 170, 230))
            p = self.dir / f"ref{k}.png"
            im.save(p)
            refs.append(p)
        out = create_from_references("my_clean", "내 깔끔한 그림체", refs, root=self.dir / "styles")
        import yaml
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        bg, ink = data["palette"]["bg"], data["palette"]["ink"]
        self.assertGreater(int(bg[1:3], 16), 200)
        self.assertLess(int(ink[1:3], 16), 90)
        self.assertIn(data["art"]["scene"], ("lineart", "pastel", "flat", "detailed"))
        self.assertEqual(data["references"], ["ref0.png", "ref1.png"])
        self.assertEqual(sorted(p.name for p in (self.dir / "styles").iterdir()), ["my_clean.yaml"])
        with self.assertRaises(ValueError):
            create_from_references("pastel", "기본과 같은 id", refs, root=self.dir / "styles")
        with self.assertRaises(ValueError):
            create_from_references("ok_id", "없는 파일", [self.dir / "nope.png"], root=self.dir / "styles")


class EditorialCharacterTests(unittest.IsolatedAsyncioTestCase):
    def test_identity_and_clothes_are_fixed_across_eight_emotions(self):
        bible = charmod.get_character("minji_01")
        self.assertEqual(bible.mascot["face"], "editorial")
        portraits = [draw_mascot(bible.mascot, e, "standing") for e in EMOTIONS]
        for box in ((190, 140, 410, 260), (260, 715, 350, 765)):
            self.assertEqual(len({im.crop(box).tobytes() for im in portraits}), 1)
        self.assertGreaterEqual(len({im.crop((190, 280, 410, 430)).tobytes() for im in portraits}), 7)
        for im in portraits:
            self.assertEqual((im.mode, im.size, im.getchannel("A").getextrema()), ("RGBA", (600, 780), (0, 255)))

    def test_pose_and_flip_do_not_redesign_the_head(self):
        bible = charmod.get_character("minji_01")
        poses = ("standing", "pointing", "thinking", "arms_crossed", "cheering", "waving")
        portraits = [draw_mascot(bible.mascot, "neutral", pose) for pose in poses]
        self.assertEqual(len({im.crop((190, 140, 410, 350)).tobytes() for im in portraits}), 1)
        self.assertEqual(len({im.tobytes() for im in portraits}), len(poses))
        flipped = draw_mascot(bible.mascot, "neutral", "standing", flip=True)
        self.assertEqual(flipped.tobytes(), portraits[0].transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes())

    async def test_guide_and_panel_use_the_same_character_configuration(self):
        from app.carousel.visuals import CharacterArtist
        from app.pipeline.sources import SourceRegistry
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            artist = CharacterArtist(job_dir=root, registry=SourceRegistry(root), provider_cfg=None, default_id="minji_01")
            artist.mascot_style = dict(load_template("comic_hybrid", "insta_toon", "clean_webtoon").art["mascot"])
            guide = artist.guide("worried", "standing")
            for i in range(1, 9):
                panel = await artist.art(ComicBeat(character_id="minji_01", emotion="worried", pose="standing"), i)
                self.assertEqual(panel.source, "mascot")
                self.assertEqual(panel.image.tobytes(), guide.tobytes())

    async def test_prepared_eight_page_deck_needs_no_ai_or_image_service(self):
        from unittest.mock import AsyncMock, patch
        from app.carousel.pipeline import run_carousel
        from app.carousel.schema import CarouselPlan, MasterContent
        import json
        pages = [CardPage(type="cover", headline="주인공 외형 검수", character_emotion="worried")]
        pages += [ComicPage(type="comic_scene", panels=[ComicBeat(character_id="minji_01", emotion=e,
                       pose="pointing", background="원룸", dialogue="같은 주인공의 장면입니다.")])
                  for e in ("happy", "surprised", "worried", "thinking", "sad", "angry")]
        pages += [CardPage(type="cta", headline="다음 장면도 같은 주인공", character_emotion="happy")]
        plan = CarouselPlan(format="insta_toon", template="comic_hybrid", art_style="clean_webtoon", pages=pages)
        master = MasterContent(topic="외형 검수", title="같은 주인공", summary="합성 테스트 원고")
        cfg = {"llm": {"provider": "claude"}, "carousel": {"image_provider": "none", "image_search": False}}
        with tempfile.TemporaryDirectory() as d, \
             patch("app.carousel.master.ask_structured", new=AsyncMock(side_effect=AssertionError("no AI"))) as ai, \
             patch("app.carousel.planner.ask_structured", new=AsyncMock(side_effect=AssertionError("no AI"))) as planner_ai, \
             patch("app.carousel.inbox.import_inbox", return_value={"added": [], "skipped": []}):
            out = await run_carousel(Path(d), fmt="insta_toon", mode="script", text=master.topic, cfg=cfg,
                      character="minji_01", image_search=False, inputs={"topic": master.topic, "docs": []},
                      prepared_master=master, prepared_plan=plan)
            self.assertEqual(len(out["pages"]), 8)
            self.assertEqual(out["fallback_pages"], [])
            manifest = json.loads(Path(out["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual([row["id"] for row in manifest["characters"]], ["minji_01"])
            for row in manifest["pages"]:
                self.assertTrue(all(p["character_id"] == "minji_01" and p["art"] == "mascot" for p in row.get("panels", [])))
            ai.assert_not_called()
            planner_ai.assert_not_called()


if __name__ == "__main__":
    unittest.main()
