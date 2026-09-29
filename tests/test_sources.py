"""1단계: 소스 판정과 모든 출력 전 권리 가드."""
import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException, UploadFile

from app import main
from app.jobs import JobManager
from app.pipeline import capcut, timeline
from app.pipeline import run
from app.pipeline.sources import SourceRegistry, guard_timeline


PROOF = {
    "rights_confirmed": True,
    "commercial_allowed": True,
    "adaptation_allowed": True,
    "third_party_rights_checked": True,
    "license_note": "내가 촬영했고 삽입 음악과 인물 권리를 확인함",
}


def sample_timeline() -> dict:
    return {"narration": "audio.mp3", "bgm": "", "scenes": [
        {"visual": {"kind": "image", "path": "scene.jpg"}}], "comments": []}


class SourceRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name)
        self.registry = SourceRegistry(self.job)

    def test_unknown_and_reference_urls_are_not_usable(self):
        unknown = self.registry.add(kind="image", origin="upload", path=str(self.job / "u.jpg"), title="unknown")
        article = self.registry.add(kind="article", origin="url", url="https://news.example/story", title="기사")
        video = self.registry.add(kind="video", origin="url", url="https://youtu.be/abc", title="타인 영상")
        for item in (unknown, article, video):
            self.assertFalse(item.usable_in_video)
        self.assertEqual(len(SourceRegistry(self.job).items), 3)

    def test_own_channel_needs_individual_proof_and_third_party_check(self):
        path = str(self.job / "mine.mp4")
        self.assertFalse(self.registry.add(kind="video", origin="upload", path=path,
                         rights={"license": "my_channel"}).usable_in_video)
        missing = {**PROOF, "third_party_rights_checked": False, "license": "my_channel"}
        self.assertFalse(self.registry.add(kind="video", origin="upload", path=path,
                         rights=missing).usable_in_video)
        good = self.registry.add(kind="video", origin="upload", path=path,
                                 rights={**PROOF, "license": "my_channel"})
        self.assertTrue(good.usable_in_video)
        self.assertTrue(good.license_checked_at)

    def test_stock_and_kogl_require_item_link_and_credit(self):
        for license_name in ("pexels", "pixabay", "kogl_type0", "kogl_type1"):
            with self.subTest(license_name=license_name):
                path = str(self.job / f"{license_name}.jpg")
                rights = {**PROOF, "license": license_name}
                self.assertFalse(self.registry.add(kind="image", origin="upload", path=path,
                                                  rights=rights).usable_in_video)
                rights.update(license_url="https://example.org/item/1", credit="출처: 원저작자")
                self.assertTrue(self.registry.add(kind="image", origin="upload", path=path,
                                                 rights=rights).usable_in_video)
        for license_name in ("kogl_type2", "kogl_type3", "kogl_type4"):
            rights = {**PROOF, "license": license_name, "license_url": "https://example.org/item/1",
                      "credit": "출처: 원저작자"}
            self.assertFalse(self.registry.add(kind="image", origin="upload", path=str(self.job / f"{license_name}.jpg"),
                                               rights=rights).usable_in_video)

    def test_generated_and_derived_keep_origin(self):
        original = self.registry.add(kind="image", origin="upload", path=str(self.job / "input.jpg"),
                                     rights={**PROOF, "license": "ai_generated"})
        output = self.registry.add(kind="image", origin="derived", path=str(self.job / "scene.jpg"),
                                   rights=original.model_dump(), parent_id=original.id)
        self.assertTrue(output.usable_in_video)
        self.assertEqual(output.parent_id, original.id)
        self.assertTrue(self.registry.add(kind="image", origin="generated", path=str(self.job / "card.jpg")).usable_in_video)

    def test_render_guard_rejects_unknown_visual_audio_comments_and_legacy(self):
        tl = sample_timeline()
        with self.assertRaisesRegex(ValueError, "소스 사용 권한 대장"):
            guard_timeline(self.job, tl)
        self.registry.add(kind="audio", origin="generated", path=str(self.job / "audio.mp3"))
        self.registry.add(kind="image", origin="upload", path=str(self.job / "scene.jpg"))
        with self.assertRaisesRegex(ValueError, "scene.jpg"):
            guard_timeline(self.job, tl)
        self.registry.add(kind="image", origin="generated", path=str(self.job / "scene.jpg"))
        guard_timeline(self.job, tl)
        tl["comments"] = [{"kind": "text", "text": "타인 댓글"}]
        with self.assertRaisesRegex(ValueError, "타인 댓글"):
            guard_timeline(self.job, tl)

    def test_initial_render_function_blocks_before_creating_subtitles(self):
        self.registry.add(kind="audio", origin="generated", path=str(self.job / "audio.mp3"))
        self.registry.add(kind="image", origin="upload", path=str(self.job / "scene.jpg"))
        with self.assertRaisesRegex(ValueError, "scene.jpg"):
            asyncio.run(timeline.render_timeline(sample_timeline(), self.job, self.job / "final.mp4"))
        self.assertFalse((self.job / "subs.ass").exists())
        self.assertFalse((self.job / "final.mp4").exists())

    def test_capcut_and_zip_guard_before_writing(self):
        self.registry.add(kind="audio", origin="generated", path=str(self.job / "audio.mp3"))
        self.registry.add(kind="image", origin="upload", path=str(self.job / "scene.jpg"))
        tl = sample_timeline()
        root = self.job / "drafts"
        root.mkdir()
        with self.assertRaisesRegex(ValueError, "scene.jpg"):
            asyncio.run(capcut.export_draft(tl, self.job, root, "test"))
        with self.assertRaisesRegex(ValueError, "scene.jpg"):
            asyncio.run(capcut.export_pack(tl, self.job, self.job / "pack.zip"))
        self.assertEqual(list(root.iterdir()), [])
        self.assertFalse((self.job / "pack.zip").exists())

    def test_upload_api_records_rights_and_sources_api_reads_it(self):
        fake = SimpleNamespace(output=self.job.parent,
            get=lambda job_id: SimpleNamespace(status="awaiting_review"),
            job_dir=lambda job_id: self.job)
        file = UploadFile(filename="own.jpg", file=io.BytesIO(b"image"))
        with patch.object(main, "manager", fake, create=True):
            result = asyncio.run(main.scene_visual(self.job.name, scene=0, file=file,
                rights=__import__("json").dumps({**PROOF, "license": "my_channel"})))
            items = asyncio.run(main.get_sources(self.job.name))
        self.assertTrue(result["usable_in_video"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "scene_00_own.jpg")

    def test_export_api_explains_blocked_source(self):
        timeline.save(self.job, sample_timeline())
        fake = SimpleNamespace(output=self.job.parent,
            get=lambda job_id: SimpleNamespace(status="done"),
            job_dir=lambda job_id: self.job)
        with patch.object(main, "manager", fake, create=True):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(main.export_pack(self.job.name))
        self.assertEqual(cm.exception.status_code, 409)
        self.assertIn("소스 사용 권한 대장", cm.exception.detail)

    def test_url_clip_is_rejected_before_paid_pipeline(self):
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(main.create_job(main.CreateJob(mode="url", input="https://youtu.be/example",
                preset="daily", options={"clip_mode": True})))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("권리 확인", cm.exception.detail)

    def test_rerender_rejects_unknown_source_and_keeps_original(self):
        self.registry.add(kind="audio", origin="generated", path=str(self.job / "audio.mp3"))
        self.registry.add(kind="image", origin="upload", path=str(self.job / "scene.jpg"))
        timeline.save(self.job, sample_timeline())
        (self.job / "final.mp4").write_bytes(b"original")
        with patch.object(run, "require_ffmpeg"):
            with self.assertRaisesRegex(ValueError, "scene.jpg"):
                asyncio.run(run.rerender(self.job, {"paths": {"assets": str(self.job)}}))
        self.assertEqual((self.job / "final.mp4").read_bytes(), b"original")

    def test_scene_remap_moves_rights_record(self):
        up = self.job / "uploads"
        up.mkdir()
        old = up / "scene_01_own.jpg"
        old.write_bytes(b"image")
        self.registry.add(kind="image", origin="upload", path=str(old),
                          rights={**PROOF, "license": "my_channel"})
        fake = SimpleNamespace(_job_dir=lambda job_id: self.job)
        JobManager._remap_scene_files(fake, "job", [1])
        registry = SourceRegistry(self.job)
        new = up / "scene_00_own.jpg"
        self.assertTrue(new.exists())
        self.assertTrue(registry.by_path(new).usable_in_video)
        self.assertIsNone(registry.by_path(old))


if __name__ == "__main__":
    unittest.main()
