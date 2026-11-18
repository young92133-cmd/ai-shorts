"""find-shorts: 원본 링크 → 같은 주제 인기 쇼츠 찾기. 네트워크 없이 검색어·관련도·결과 해석만 확인한다."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.pipeline import shorts_finder as sf


class KeysTests(unittest.TestCase):
    def test_music_stage_title(self):
        k = sf.source_keys({"title": "연애의 조건 - BESTie (베스티) | SBS 261115 방송", "channel": "SBSKPOP X INKIGAYO"})
        self.assertEqual((k["kind"], k["song"], k["artist"], k["artist_latin"], k["program"], k["date_code"]),
                         ("music", "연애의 조건", "베스티", "BESTie", "인기가요", "261115"))
        self.assertIn("베스티 연애의 조건", sf.queries(k))

    def test_fan_and_issue_titles_use_topic_words(self):
        k = sf.source_keys({"title": "[단독] 장원영 공항 출국 현장, 팬들 몰려 난리 #shorts | 연예뉴스", "channel": "연예뉴스TV"})
        self.assertEqual(k["kind"], "general")
        self.assertEqual(k["topic"][:4], ["장원영", "공항", "출국", "현장"])
        qs = sf.queries(k, ["장원영 공항패션"])
        self.assertEqual(qs[0], "장원영 공항 출국 현장")
        self.assertIn("장원영 공항", qs)
        self.assertEqual(qs[-1], "장원영 공항패션")
        self.assertEqual(len(qs), len(set(qs)))

    def test_variety_with_dash_but_not_music_channel(self):
        k = sf.source_keys({"title": "유재석 - 런닝맨 레전드 모음", "channel": "예능 다시보기"})
        self.assertEqual(k["kind"], "general")
        self.assertEqual(k["topic"][:2], ["유재석", "런닝맨"])


class RelevanceTests(unittest.TestCase):
    def test_topic_overlap_and_after_source(self):
        k = sf.source_keys({"title": "장원영 공항 출국 현장 팬들 몰려", "channel": "연예뉴스TV"})
        hit = sf.relevance({"title": "공항에서 장원영이 한 행동", "upload_date": "20261120"}, k, "20261118")
        miss = sf.relevance({"title": "카리나 무대 직캠", "upload_date": "20261101"}, k, "20261118")
        self.assertEqual((hit["same_topic"], hit["after_source"]), (True, True))
        self.assertEqual((miss["same_topic"], miss["after_source"]), (False, False))

    def test_music_song_match(self):
        k = sf.source_keys({"title": "연애의 조건 - BESTie (베스티) | SBS 261115 방송", "channel": "SBSKPOP X INKIGAYO"})
        self.assertTrue(sf.relevance({"title": "베스티 연애의조건 혜연 랩"}, k, "")["same_topic"])


class SearchParseTests(unittest.TestCase):
    def test_views_and_shorts_items(self):
        self.assertEqual(sf.parse_views("조회수 27만회 · 23시간 전"), 270000)
        self.assertEqual(sf.parse_views("조회수 1.6천회"), 1600)
        data = {"a": [{"shortsLockupViewModel": {
            "onTap": {"innertubeCommand": {"reelWatchEndpoint": {"videoId": "abc"}}},
            "overlayMetadata": {"primaryText": {"content": "제목"}, "secondaryText": {"content": "조회수 3.2만회"}}}}]}
        out: list = []
        sf._walk(data, out)
        self.assertEqual(out, [{"id": "abc", "title": "제목", "views_text": "조회수 3.2만회", "views": 32000}])

    def test_find_ranks_related_after_source_first(self):
        info = {"id": "src", "title": "장원영 공항 출국 현장", "channel": "연예뉴스TV", "webpage_url": "https://y/src"}
        hits = [{"id": "old", "title": "장원영 공항 예전", "views_text": "", "views": 900000},
                {"id": "new", "title": "장원영 공항 출국 그 후", "views_text": "", "views": 50000},
                {"id": "src", "title": "원본", "views_text": "", "views": 10}]
        det = {"old": {"upload_date": "20260101", "duration": 30, "subscribers": 1000},
               "new": {"upload_date": "20261120", "duration": 20, "subscribers": 500}}

        class FakeYDL:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def extract_info(self, *a, **k): return {"upload_date": "20261118"}

        with patch("app.pipeline.youtube._info_sync", return_value=info), \
                patch.object(sf, "search_shorts", return_value=hits), \
                patch.object(sf, "_details", side_effect=lambda v: {"channel": "c", "view_count": None,
                                                                    "description": "", **det[v]}), \
                patch("yt_dlp.YoutubeDL", FakeYDL):
            out = sf.find("https://y/src", limit=5)
        self.assertEqual([c["id"] for c in out["candidates"]], ["new", "old"])   # 원본 제외, 원본 이후·같은 주제 먼저
        self.assertEqual(out["candidates"][0]["views_per_sub"], 100.0)


if __name__ == "__main__":
    unittest.main()
