"""Fetch public YouTube comments for optional, user-reviewed text cards."""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx

from ..config import env


def video_id(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in ("youtu.be", "www.youtu.be"):
        return parsed.path.strip("/").split("/")[0]
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            return (parse_qs(parsed.query).get("v") or [""])[0]
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] in ("shorts", "live"):
            return parts[1]
    return ""


async def fetch_candidates(urls: list[str], limit: int = 8, log=print) -> list[dict]:
    """Use the official Data API. Empty results are explicit, never invented."""
    key = env("YOUTUBE_API_KEY")
    if not key:
        log("댓글 후보를 가져오려면 YouTube Data API 키를 등록해야 합니다")
        return []
    out: list[dict] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(timeout=20) as client:
        for url in urls[:3]:
            vid = video_id(url)
            if not vid or vid in seen:
                continue
            seen.add(vid)
            try:
                response = await client.get("https://www.googleapis.com/youtube/v3/commentThreads", params={
                    "part": "snippet", "videoId": vid, "order": "relevance",
                    "maxResults": min(20, limit), "textFormat": "plainText", "key": key,
                })
                response.raise_for_status()
                for item in response.json().get("items", []):
                    snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                    comment = item.get("snippet", {}).get("topLevelComment", {})
                    text = " ".join(str(snippet.get("textDisplay") or "").split())
                    if not (5 <= len(text) <= 108):
                        continue
                    out.append({"id": comment.get("id", ""), "text": text,
                                "url": f"https://www.youtube.com/watch?v={vid}&lc={comment.get('id', '')}",
                                "video_url": f"https://www.youtube.com/watch?v={vid}",
                                "likes": int(snippet.get("likeCount") or 0)})
                    if len(out) >= limit:
                        return out
            except Exception as exc:  # disabled comments, quota and private videos are common
                log(f"댓글을 가져오지 못했습니다 ({vid}): {type(exc).__name__}")
    return out
