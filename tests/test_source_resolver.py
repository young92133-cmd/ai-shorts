"""Source Resolver · Clip Analyzer · Rights Guard.

공개 API 는 httpx.MockTransport 로, AI 는 가짜로 바꾼다. 실제 네트워크·Claude 호출 없음.
Clip Analyzer 의 샷 검출만 실제 ffmpeg 로 짧은 테스트 영상을 만들어 확인한다.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from PIL import Image

from app.factory import core, state as st
from app.pipeline import clip_analyzer, run, source_resolver as sr, timeline, visuals as visualsmod
from app.pipeline.models import PlannedScript, Word
from app.pipeline.sources import SourceRegistry

from tests.test_factory import FactoryTestCase, cat_script

USABLE_RIGHTS = sr.classify_license("by", version="2.0", license_url="https://creativecommons.org/licenses/by/2.0/")


def cand(cid: str, media: str = "image", status_code: str = "by", **kw) -> sr.VisualCandidate:
    rights = sr.classify_license(status_code, license_url="https://creativecommons.org/licenses/by/2.0/")
    base = dict(id=cid, provider="openverse", media_type=media, title=f"{cid} title", page_url=f"https://ex/{cid}",
                file_url=f"https://files.ex/{cid}.jpg", width=1080, height=1920, creator="Kim", rights=rights)
    base.update(kw)
    return sr.VisualCandidate(**base)


def jpg_bytes() -> bytes:
    import io
    buf = io.BytesIO()
    Image.new("RGB", (1200, 1600), (30, 60, 90)).save(buf, "JPEG")
    return buf.getvalue()


class RightsTests(unittest.TestCase):
    def test_license_matrix(self):
        cases = {"cc0": ("usable", "cc0"), "pdm": ("usable", "public_domain"), "cc-by-4.0": ("usable", "cc_by"),
                 "by": ("usable", "cc_by"), "by-sa": ("reference_only", ""), "cc-by-nc-2.0": ("reference_only", ""),
                 "by-nd": ("reference_only", ""), "": ("unknown", ""), "GFDL": ("unknown", "")}
        for code, (status, key) in cases.items():
            r = sr.classify_license(code)
            self.assertEqual((r.status, r.license_key), (status, key), code)
        self.assertEqual(sr.classify_license("cc0", restrictions="personality rights").status, "reference_only")
        self.assertEqual(sr.classify_license("", provider="nasa").status, "usable")
        self.assertEqual(sr.classify_license("", provider="nasa", copyright_marker=True).status, "reference_only")

    def test_youtube_is_never_auto_usable(self):
        cc = sr.classify_youtube({"license": "Creative Commons Attribution license (reuse allowed)"})
        self.assertEqual(cc["rights_status"], "reference_only")
        self.assertIn("약관", cc["rights_basis"])
        self.assertEqual(sr.classify_youtube({"license": ""})["rights_status"], "reference_only")
        self.assertEqual(sr.classify_youtube(None)["rights_status"], "unknown")

    def test_registry_accepts_auto_licenses_only_with_basis(self):
        with tempfile.TemporaryDirectory() as d:
            reg = SourceRegistry(Path(d))
            ok = reg.add(kind="image", origin="resolved", path=str(Path(d) / "a.jpg"), source_type="openverse",
                         rights={"license": "cc_by", "license_url": "https://creativecommons.org/licenses/by/2.0/",
                                 "rights_confirmed": True, "commercial_allowed": True, "adaptation_allowed": True,
                                 "third_party_rights_checked": True, "credit": "사진: Kim / CC BY 2.0"})
            self.assertTrue(ok.usable_in_video)
            self.assertEqual(ok.rights_status, "usable")
            no_credit = reg.add(kind="image", origin="resolved", path=str(Path(d) / "b.jpg"),
                                rights={"license": "cc_by", "license_url": "https://creativecommons.org/licenses/by/2.0/",
                                        "rights_confirmed": True, "commercial_allowed": True, "adaptation_allowed": True,
                                        "third_party_rights_checked": True})
            self.assertFalse(no_credit.usable_in_video)          # CC BY 는 출처 표기가 있어야 한다
            self.assertNotEqual(no_credit.rights_status, "usable")
            ref = reg.add(kind="video", origin="url", url="https://youtube.com/watch?v=x", source_type="youtube",
                          rights_status="usable", used_for="script_research")
            self.assertEqual(ref.rights_status, "reference_only")   # 호출 쪽 주장보다 계산 결과가 우선
            self.assertEqual(ref.usage, "research")

    def test_mark_used_records_scene_and_clip_on_parent(self):
        with tempfile.TemporaryDirectory() as d:
            reg = SourceRegistry(Path(d))
            parent = reg.add(kind="video", origin="resolved", path=str(Path(d) / "v.mp4"),
                             rights={"license": "cc0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                                     "rights_confirmed": True, "commercial_allowed": True, "adaptation_allowed": True,
                                     "third_party_rights_checked": True})
            child = reg.add(kind="image", origin="derived", path=str(Path(d) / "s.jpg"), rights=parent.model_dump(),
                            parent_id=parent.id)
            reg.mark_used(child.path, 2, "00:31.0-00:37.0")
            saved = {i["id"]: i for i in json.loads((Path(d) / "sources.json").read_text(encoding="utf-8"))}
            self.assertEqual(saved[parent.id]["scene_ids"], [2])
            self.assertEqual(saved[parent.id]["clip_ranges"], ["00:31.0-00:37.0"])
            self.assertEqual(saved[child.id]["usage"], "visual")


class ScoringTests(unittest.TestCase):
    def test_score_prefers_fit_and_rights(self):
        good = cand("a")
        fit = sr.FitScore(candidate_id="a", visual_fit=9, evidence_fit=7, reason="맞음")
        weak = sr.FitScore(candidate_id="a", visual_fit=3, evidence_fit=1, reason="다름")
        self.assertGreater(sr.score_candidate(good, fit, 4)["total"], sr.score_candidate(good, weak, 4)["total"])
        nasa = cand("n", provider="nasa", rights=sr.classify_license("", provider="nasa"))
        self.assertLess(sr.score_candidate(nasa, fit, 4)["parts"]["rights_confidence"],
                        sr.score_candidate(cand("c", status_code="cc0"), fit, 4)["parts"]["rights_confidence"])
        short = cand("v", media="video", duration=1.0)
        self.assertLess(sr.score_candidate(short, fit, 6)["parts"]["editability"],
                        sr.score_candidate(cand("v2", media="video", duration=20), fit, 6)["parts"]["editability"])

    def test_choose_respects_rights_threshold_priority_and_reuse(self):
        a, b, sa, v = cand("a"), cand("b"), cand("sa", status_code="by-sa"), cand("v", media="video", duration=20)
        by_scene = {0: [a, sa, v], 1: [a, b]}
        fits = {c.id: sr.FitScore(candidate_id=c.id, visual_fit=8, evidence_fit=6, reason="") for c in (a, b, sa, v)}
        scores = {c.id: sr.score_candidate(c, fits[c.id], 4) for c in (a, b, sa, v)}
        queries = {0: sr.SceneQuery(scene_index=0, query_en="x", prefer="video", must_show=""),
                   1: sr.SceneQuery(scene_index=1, query_en="y", prefer="image", must_show="")}
        picked = sr.choose(by_scene, scores, fits, queries, ["video", "image"], min_score=50, min_visual_fit=6)
        self.assertEqual(picked[0].id, "v")                     # 구조 우선순위·장면 선호가 영상
        self.assertIn(picked[1].id, ("a", "b"))
        self.assertNotIn("sa", [c.id for c in picked.values()])  # BY-SA 는 자동 사용 안 함
        low = {k: {**v2, "total": 10} for k, v2 in scores.items()}
        self.assertEqual(sr.choose(by_scene, low, fits, queries, ["image"], min_score=50, min_visual_fit=6), {})


class ClipAnalyzerTests(unittest.TestCase):
    def test_windows_prefer_single_shot_and_keywords(self):
        words = [Word(text="the rocket launch begins", start=10.0, end=13.0)]
        cands = clip_analyzer.score_windows(30.0, 4.0, shots=[5.0, 12.0, 20.0], silences=[(4.8, 5.2)],
                                            transcript=words, keywords=["rocket launch"])
        best = cands[0]
        self.assertFalse(any(best.start + 0.15 < s < best.end - 0.15 for s in (5.0, 12.0, 20.0)))
        self.assertGreater(best.parts["stability"], 30)
        self.assertTrue(any(c.parts["relevance"] > 10 for c in cands))

    def test_parse_srt(self):
        text = "1\n00:00:01,000 --> 00:00:03,500\nHello telescope\n\n2\n00:00:04,000 --> 00:00:06,000\nMirror\n"
        words = clip_analyzer.parse_srt(text)
        self.assertEqual([(w.text, w.start, w.end) for w in words], [("Hello telescope", 1.0, 3.5), ("Mirror", 4.0, 6.0)])

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg 필요")
    def test_real_ffmpeg_shot_detection(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "two_shots.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "lavfi", "-i", "color=c=red:s=320x240:d=3",
                            "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=3",
                            "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", str(out)], check=True)
            result = clip_analyzer.analyze_sync(out, 2.0)
            self.assertTrue(any(abs(s - 3.0) < 0.2 for s in result.shots), result.shots)
            rec = result.recommended
            self.assertTrue(rec.end <= 3.05 or rec.start >= 2.95, rec)   # 컷을 가로지르지 않는 구간


class RealRenderTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg 필요")
    async def test_odd_size_source_video_and_image_concat(self):
        """2026-10-05 실제 F 렌더 실패 회귀: 가로 영상 축소 반올림으로 SAR 이 1:1 이 아니면 concat 이 실패했다."""
        from app.pipeline import render
        with tempfile.TemporaryDirectory() as d:
            vid, img, out = Path(d) / "odd.mp4", Path(d) / "a.jpg", Path(d) / "out.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                            "-i", "testsrc=s=1002x562:d=3", "-pix_fmt", "yuv420p", str(vid)], check=True)
            Image.new("RGB", (1080, 1920), (20, 40, 60)).save(img)
            await render.render_broll([{"kind": "image", "path": img, "duration": 1.0},
                                       {"kind": "video", "path": vid, "start": 0.5, "duration": 1.5, "has_audio": False}],
                                      None, out, width=360, height=640, fps=15)
            self.assertGreater(out.stat().st_size, 1000)


def mock_transport() -> httpx.MockTransport:
    img = jpg_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "api.openverse.org" in url:
            return httpx.Response(200, json={"results": [
                {"id": "ok1", "title": "Ocean liner", "license": "by", "license_version": "2.0",
                 "license_url": "https://creativecommons.org/licenses/by/2.0/", "url": "https://files.ex/ok1.jpg",
                 "foreign_landing_url": "https://flickr.ex/ok1", "creator": "Kim", "width": 1200, "height": 1600,
                 "tags": [{"name": "ship"}]},
                {"id": "sa1", "title": "Ship SA", "license": "by-sa", "license_version": "2.0",
                 "license_url": "https://creativecommons.org/licenses/by-sa/2.0/", "url": "https://files.ex/sa1.jpg",
                 "foreign_landing_url": "https://flickr.ex/sa1", "creator": "Lee", "width": 1200, "height": 1600}]})
        if "commons.wikimedia.org" in url:
            assert "AIShortsFactory" in request.headers["User-Agent"]
            return httpx.Response(200, json={"query": {"pages": {"1": {"pageid": 1, "title": "File:Ship.jpg",
                "imageinfo": [{"thumburl": "https://files.ex/wc1.jpg", "descriptionurl": "https://commons.ex/Ship",
                               "thumbwidth": 1280, "thumbheight": 900, "extmetadata": {
                                   "License": {"value": "cc-by-sa-4.0"}, "Artist": {"value": "<a>Park</a>"}}}]}}}})
        if "images-api.nasa.gov" in url:
            return httpx.Response(200, json={"collection": {"items": []}})
        if url.startswith("https://files.ex/"):
            return httpx.Response(200, content=img, headers={"content-type": "image/jpeg"})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


class ResolveTests(unittest.IsolatedAsyncioTestCase):
    async def test_discover_classifies_and_ingests_only_usable(self):
        cfg = {"sources": {"providers": ["openverse", "wikimedia_commons", "nasa"], "contact": "https://ex"}}
        async with httpx.AsyncClient(transport=mock_transport(), headers={"User-Agent": sr.user_agent(cfg)}) as client:
            disc = sr.Discoverer(client, sr.settings(cfg), print)
            ov = await disc.search("openverse", "image", "ship")
            wc = await disc.search("wikimedia_commons", "image", "ship")
            self.assertEqual([c.rights.status for c in ov], ["usable", "reference_only"])
            self.assertEqual(wc[0].rights.status, "reference_only")
            self.assertEqual(wc[0].creator, "Park")
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):
                    await sr.ingest(client, ov[1], Path(d), 10)        # BY-SA 는 내려받지 않는다
                path, _ = await sr.ingest(client, ov[0], Path(d), 10)
                self.assertTrue(path.is_file())
                with self.assertRaises(ValueError):
                    await sr.ingest(client, ov[0], Path(d), 0)          # 크기 제한

    async def test_resolve_end_to_end_with_mock_ai(self):
        script = PlannedScript.model_validate(cat_script().model_dump())
        script.scenes[-1].beat_role = "ending_question"
        queries = sr.QueryPlan(scenes=[sr.SceneQuery(scene_index=i, query_en="ship", prefer="image", must_show="배")
                                       for i in range(5)])

        async def fake_ask(llm, system, user, schema):
            if schema is sr.QueryPlan:
                return queries
            ids = [line.split("id=")[1].split(" ")[0] for line in user.splitlines() if "id=" in line]
            return sr.FitPlan(scores=[sr.FitScore(candidate_id=i, visual_fit=9, evidence_fit=7, reason="배 사진")
                                      for i in ids])
        cfg = {"sources": {"providers": ["openverse", "wikimedia_commons"], "contact": "https://ex", "min_score": 50}}
        real_client = httpx.AsyncClient

        def client_factory(**kw):
            return real_client(transport=mock_transport(), **kw)
        with tempfile.TemporaryDirectory() as d, patch.object(sr, "ask_structured", new=fake_ask), \
                patch.object(sr.httpx, "AsyncClient", side_effect=client_factory):
            job = Path(d)
            reg = SourceRegistry(job)
            out = await sr.resolve(llm={}, script=script, topic="타이타닉", durations=[4.0] * 5, job_dir=job,
                                   registry=reg, cfg=cfg, profile_spec={"visual_priority": ["image"],
                                                                        "card_roles": ["ending_question"]})
            self.assertEqual(len(out["scenes"]), 1)          # 같은 사진은 한 장면에만
            (i, picked), = out["scenes"].items()
            self.assertNotEqual(i, 4)                       # 마지막 질문 장면은 카드 유지
            self.assertIn("CC BY", picked["credit"])
            item = reg.by_path(picked["path"])
            self.assertTrue(item.usable_in_video)
            self.assertEqual((item.source_type, item.rights_status), ("openverse", "usable"))
            plan = json.loads((job / sr.PLAN_FILE).read_text(encoding="utf-8"))
            self.assertIn(4, [s - 0 for s in plan["skipped_scenes"]])
            self.assertTrue(any(r["rights_status"] == "reference_only"
                                for s in plan["scenes"] for r in s["reference_only_or_unknown"]))

    async def test_no_provider_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            out = await sr.resolve(llm={}, script=cat_script(), topic="t", durations=[3.0] * 5, job_dir=Path(d),
                                   registry=SourceRegistry(Path(d)), cfg={"sources": {"providers": ["pexels"]}})
        self.assertEqual(out["scenes"], {})


class ScenePlannerTests(unittest.TestCase):
    def test_resolved_source_is_used_before_cards(self):
        with tempfile.TemporaryDirectory() as d:
            reg = SourceRegistry(Path(d))
            path = Path(d) / "img.jpg"
            path.write_bytes(jpg_bytes())
            reg.add(kind="image", origin="resolved", path=str(path), source_type="openverse",
                    rights={"license": "cc_by", "license_url": "https://creativecommons.org/licenses/by/2.0/",
                            "rights_confirmed": True, "commercial_allowed": True, "adaptation_allowed": True,
                            "third_party_rights_checked": True, "credit": "사진: Kim / CC BY"})
            bad = Path(d) / "bad.jpg"
            reg.add(kind="image", origin="url", path=str(bad))
            scenes = cat_script().scenes
            out = visualsmod.plan_visuals(scenes, {}, reg, ai_available=False,
                                          resolved={0: {"kind": "image", "path": str(path), "reason": "배"},
                                                    1: {"kind": "image", "path": str(bad), "reason": "?"},
                                                    2: {"kind": "video", "path": str(path), "reason": "영상"}})
            self.assertEqual(out[0].resolved_visual_type, "source_image")
            self.assertEqual(out[0].asset_source, "licensed_source")
            self.assertNotIn(out[1].resolved_visual_type, ("source_image", "source_video"))   # 권리 미확인은 카드
            self.assertEqual(out[2].resolved_visual_type, "source_video")


class PipelineSourceTests(FactoryTestCase):
    def setUp(self):
        super().setUp()
        self.image = self.root / "found.jpg"
        self.image.write_bytes(jpg_bytes())

        async def fake_resolve(*, job_dir, registry, **kw):
            path = job_dir / "sources" / "found.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.image, path)
            registry.add(kind="image", origin="resolved", path=str(path), url="https://flickr.ex/ok1",
                         source_type="openverse", used_for="scene_01",
                         rights={"license": "cc_by", "license_url": "https://creativecommons.org/licenses/by/2.0/",
                                 "rights_confirmed": True, "commercial_allowed": True, "adaptation_allowed": True,
                                 "third_party_rights_checked": True, "credit": "사진: Kim / CC BY 2.0 / Openverse",
                                 "rights_basis": "CC BY 2.0"})
            return {"scenes": {1: {"kind": "image", "path": str(path), "credit": "사진: Kim / CC BY 2.0 / Openverse",
                                   "page_url": "https://flickr.ex/ok1", "reason": "배 사진", "score": 80}},
                    "report": {"providers": ["openverse"], "selected": {"2": {}}}}
        self.resolve = AsyncMock(side_effect=fake_resolve)
        self.stack.enter_context(patch.object(run.source_resolver, "resolve", new=self.resolve))

    async def test_topic_make_uses_found_image_and_records_sources(self):
        out = await core.make(topic="고양이", log=lambda m: None)
        self.assertEqual(out["status"], "render_complete")
        job = Path(out["project_dir"])
        self.resolve.assert_awaited()
        tl = timeline.load(job)
        self.assertEqual(tl["scenes"][1]["credit"], "사진: Kim / CC BY 2.0 / Openverse")
        items = json.loads((job / "sources.json").read_text(encoding="utf-8"))
        used = [i for i in items if i.get("source_type") == "openverse" and i["origin"] == "resolved"][0]
        self.assertEqual((used["usage"], used["rights_status"], used["scene_ids"]), ("visual", "usable", [2]))
        self.assertIn("flickr.ex/ok1", (job / "meta.txt").read_text(encoding="utf-8"))
        self.assertEqual(st.load(job)["request"]["visuals"], "auto")

    async def test_found_video_becomes_clip_without_source_audio(self):
        async def video_resolve(*, job_dir, registry, **kw):
            path = job_dir / "sources" / "clip.mp4"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"0" * 2048)
            registry.add(kind="video", origin="resolved", path=str(path), source_type="nasa",
                         rights={"license": "nasa_media", "license_url": "https://www.nasa.gov/",
                                 "rights_confirmed": True, "commercial_allowed": True, "adaptation_allowed": True,
                                 "third_party_rights_checked": True, "credit": "영상: GSFC / NASA",
                                 "license_note": "자동 판정"})
            return {"scenes": {2: {"kind": "video", "path": str(path), "credit": "영상: GSFC / NASA", "start": 31.0,
                                   "end": 37.0, "clip_range": "00:31.0-00:37.0", "page_url": "https://nasa.ex",
                                   "reason": "구간"}}, "report": {}}
        self.resolve.side_effect = video_resolve
        out = await core.make(topic="망원경", log=lambda m: None)
        self.assertEqual(out["status"], "render_complete")
        job = Path(out["project_dir"])
        tl = timeline.load(job)
        self.assertEqual(tl["mode"], "broll")
        vis = tl["scenes"][2]["visual"]
        self.assertEqual((vis["kind"], vis["src_start"], vis["has_audio"]), ("video", 31.0, False))
        items = json.loads((job / "sources.json").read_text(encoding="utf-8"))
        clip = [i for i in items if i.get("source_type") == "nasa"][0]
        self.assertEqual(clip["clip_ranges"], ["00:31.0-00:37.0"])

    async def test_cards_mode_skips_search(self):
        out = await core.make(topic="고양이", visuals="cards", log=lambda m: None)
        self.assertEqual(out["status"], "render_complete")
        self.resolve.assert_not_awaited()

    async def test_invalid_visuals_option(self):
        with self.assertRaises(core.FactoryError):
            await core.make(topic="고양이", visuals="youtube", log=lambda m: None)

    async def test_youtube_link_is_recorded_reference_only_and_not_downloaded(self):
        url = "https://www.youtube.com/watch?v=testvideo11"
        info = {"title": "참고", "channel": "c", "description": "d", "duration": 20, "webpage_url": url,
                "license": "Creative Commons Attribution license (reuse allowed)"}
        with patch.object(core.runmod.youtube, "fetch_info", new=AsyncMock(return_value=info)), \
             patch.object(core.runmod.youtube, "fetch_transcript", new=AsyncMock(return_value=[Word(text="a", start=0, end=1)])), \
             patch.object(core.runmod.youtube, "download_media", new=AsyncMock()) as download:
            out = await core.make(url=url, log=lambda m: None)
        self.assertEqual(out["status"], "render_complete")
        download.assert_not_awaited()
        items = json.loads((Path(out["project_dir"]) / "sources.json").read_text(encoding="utf-8"))
        yt = [i for i in items if i.get("source_type") == "youtube"][0]
        self.assertEqual((yt["rights_status"], yt["usage"]), ("reference_only", "reference_only"))
        self.assertFalse(yt["usable_in_video"])


if __name__ == "__main__":
    unittest.main()
