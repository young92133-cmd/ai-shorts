"""카드뉴스·인스타툰 스튜디오 (2026-10-16): 만들기 → 열기 → 카드 1장 수정·장면 바꾸기 → ZIP 저장. AI·네트워크는 전부 가짜."""
from __future__ import annotations

import json
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image as PILImage

from app.carousel import master as mastermod, planner
from app.factory.core import FactoryError
from app.pipeline.models import ResearchDoc
from app.pipeline.sources import SourceRegistry
from app.studio import project as studio
from app.studio.api import router
from tests.test_carousel import LONG
from tests.test_factory import FactoryTestCase


def _quiet(_msg: str) -> None:
    pass


class StudioTests(FactoryTestCase):
    def setUp(self):
        super().setUp()
        self.research.return_value = [ResearchDoc(title="주거비 기사", url="https://example.com/rent", text=LONG)]
        for p in (patch.object(mastermod, "ask_structured", new=AsyncMock(side_effect=RuntimeError("AI 없음"))),
                  patch.object(planner, "ask_structured", new=AsyncMock(side_effect=RuntimeError("AI 없음")))):
            self.stack.enter_context(p)

    async def _make(self, fmt: str = "card_news") -> str:
        out = await studio.create("전세 vs 월세", fmt=fmt, pages=7, log=_quiet)
        self.assertEqual(out["status"], "render_complete", out.get("message"))
        return out["project_id"]

    async def test_create_list_and_load(self):
        pid = await self._make()
        listed = studio.list_projects()
        self.assertEqual([p["project_id"] for p in listed], [pid])
        self.assertEqual(listed[0]["thumb"], "card_news/card_01.png")
        data = studio.load(pid)
        self.assertEqual(len(data["pages"]), 7)
        self.assertEqual(data["pages"][0]["type"], "cover")
        self.assertTrue(all(p["file"].startswith("card_news/card_") for p in data["pages"]))
        self.assertIn("emotions", data["options"])
        with self.assertRaises(FactoryError):
            await studio.create("  ", fmt="card_news")
        with self.assertRaises(FactoryError):
            await studio.create("주제", fmt="shorts")

    async def test_edit_one_card_rerenders_only_that_page(self):
        pid = await self._make()
        folder = studio.core.output_root() / pid / "card_news"
        before = {p.name: p.stat().st_mtime_ns for p in folder.glob("card_*.png")}
        page = studio.load(pid)["pages"][2]
        rec = await studio.update_page(pid, 3, {"headline": "바꾼 제목", "body": "바꾼 본문", "type": "cta", "kind": "comic"})
        self.assertEqual(rec["headline"], "바꾼 제목")
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["pages"][2]["headline"], "바꾼 제목")
        self.assertEqual(plan["pages"][2]["type"], page["type"])               # 허용한 칸만 바뀐다
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["pages"][2]["headline"], "바꾼 제목")
        self.assertEqual(len(manifest["pages"]), 7)
        after = {p.name: p.stat().st_mtime_ns for p in folder.glob("card_*.png")}
        self.assertEqual([n for n in before if before[n] != after[n]], ["card_03.png"])
        with self.assertRaises(FactoryError):
            await studio.update_page(pid, 99, {"headline": "x"})

    async def test_comic_dialogue_edit_and_vary_scene(self):
        pid = await self._make("insta_toon")
        data = studio.load(pid)
        n = next(p["page"] for p in data["pages"] if p["kind"] == "comic")
        beat = data["pages"][n - 1]["data"]["panels"][0]
        await studio.update_page(pid, n, {"panels": [{"dialogue": "새 대사예요", "emotion": "sad", "character_id": "evil"}]})
        new = studio.load(pid)["pages"][n - 1]["data"]["panels"][0]
        self.assertEqual((new["dialogue"], new["emotion"], new["character_id"]), ("새 대사예요", "sad", beat["character_id"]))
        rec = await studio.vary_scene(pid, n)
        varied = studio.load(pid)["pages"][n - 1]["data"]["panels"][0]
        self.assertNotEqual((varied["emotion"], varied["background"]), (new["emotion"], new["background"]))
        self.assertEqual(rec["page"], n)
        self.assertIsInstance(studio.load(pid)["pose_gaps"], list)

    def _state(self, pid: str):
        """plan 문구 순서 · manifest 기록 · 실제 PNG 파일이 서로 맞는지 한 번에 본다."""
        folder = studio.core.output_root() / pid / "card_news"
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        heads = [pg["headline"] for pg in plan["pages"]]
        self.assertEqual([r["page"] for r in manifest["pages"]], list(range(1, len(heads) + 1)))
        self.assertEqual([r["headline"] for r in manifest["pages"]], heads)
        self.assertEqual([r["file"] for r in manifest["pages"]], [f"card_{i:02d}.png" for i in range(1, len(heads) + 1)])
        self.assertEqual(sorted(p.name for p in folder.glob("card_*.png")), [r["file"] for r in manifest["pages"]])
        self.assertEqual(manifest["page_count"], len(heads))
        return folder, heads, manifest

    async def test_move_add_delete_keep_text_image_files_in_sync(self):
        pid = await self._make()
        folder, heads, manifest = self._state(pid)
        # 2장에 권리 확인된 사진이 있다고 가정 → 순서를 바꾸면 사진·출처 표기도 같이 움직여야 한다
        photo = folder / "photo.png"
        PILImage.new("RGB", (400, 300), (120, 160, 200)).save(photo)
        reg = SourceRegistry(folder.parent)
        reg.add(kind="image", origin="generated", path=str(photo), title="테스트 사진")
        manifest["pages"][1]["image"] = {"path": str(photo), "credit": "테스트 크레딧", "page_url": "https://x.test/p"}
        (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

        out = await studio.move_page(pid, 2, 5)
        _, moved, manifest = self._state(pid)
        self.assertEqual(moved, heads[:1] + heads[2:5] + [heads[1]] + heads[5:])
        self.assertEqual(manifest["pages"][4]["image"]["path"], str(photo))
        self.assertTrue(all(r["image"] is None for k, r in enumerate(manifest["pages"]) if k != 4))
        self.assertIn("5장 테스트 크레딧", (folder / "caption.txt").read_text(encoding="utf-8"))
        self.assertNotIn("2장 테스트 크레딧", (folder / "caption.txt").read_text(encoding="utf-8"))
        self.assertEqual(len(out["pages"]), 7)

        await studio.add_page(pid, 2, "card")
        _, added, _ = self._state(pid)
        self.assertEqual(added[2], "새 카드 제목")
        self.assertEqual(added[:2] + added[3:], moved)
        with self.assertRaises(FactoryError):
            await studio.add_page(pid, 1, "comic")          # 카드뉴스에는 만화 컷을 넣지 않는다

        await studio.delete_page(pid, 3)
        _, deleted, manifest = self._state(pid)
        self.assertEqual(deleted, moved)
        self.assertFalse((folder / "card_08.png").exists())   # 줄어든 번호의 옛 파일은 남지 않는다
        self.assertTrue(list((folder / "history").glob("*_plan.json")))   # 바꾸기 전 구성은 보존
        with zipfile.ZipFile(studio.export_zip(pid)) as z:
            self.assertEqual(len([n for n in z.namelist() if n.startswith("card_")]), 7)
        for _ in range(4):
            await studio.delete_page(pid, 1)
        with self.assertRaises(FactoryError):                # 최소 장수 아래로는 지우지 않는다
            await studio.delete_page(pid, 1)
        with self.assertRaises(FactoryError):
            await studio.move_page(pid, 1, 9)

    async def test_add_comic_page_to_insta_toon(self):
        pid = await self._make("insta_toon")
        before = studio.load(pid)
        after = await studio.add_page(pid, 0, "comic")
        self.assertEqual(len(after["pages"]), len(before["pages"]) + 1)
        first = after["pages"][0]
        self.assertEqual(first["kind"], "comic")
        self.assertEqual(first["data"]["panels"][0]["character_id"], "hamtorich_01")
        self.assertEqual([p["data"]["headline"] for p in after["pages"][1:]], [p["data"]["headline"] for p in before["pages"]])

    async def test_export_zip(self):
        pid = await self._make()
        path = studio.export_zip(pid)
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        self.assertEqual(len([x for x in names if x.startswith("card_")]), 7)
        self.assertIn("caption.txt", names)

    async def test_api_routes(self):
        pid = await self._make()
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        self.assertIn("card_news", client.get("/api/studio/choices").json()["formats"])
        self.assertEqual(client.get("/studio").status_code, 200)
        self.assertEqual(client.get(f"/api/studio/projects/{pid}").json()["project_id"], pid)
        r = client.post(f"/api/studio/projects/{pid}/pages/2", json={"fields": {"headline": "API 수정"}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["headline"], "API 수정")
        self.assertEqual(client.get(f"/api/studio/files/{pid}/card_news/card_02.png").status_code, 200)
        self.assertEqual(client.get(f"/api/studio/files/{pid}/card_news/plan.json").status_code, 404)
        self.assertEqual(client.get(f"/api/studio/files/{pid}/card_news/..%5Cproject_state.json").status_code, 404)
        self.assertEqual(client.get("/api/studio/projects/nope_404").status_code, 404)
        self.assertEqual(client.post("/api/studio/projects", json={"topic": "", "format": "card_news"}).status_code, 400)
        z = client.post(f"/api/studio/projects/{pid}/export").json()
        self.assertEqual(client.get(f"/api/studio/files/{pid}/{z['file']}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
