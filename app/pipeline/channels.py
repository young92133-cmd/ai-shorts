"""경쟁 채널 쇼츠 벤치마킹: 공개 지표 수집 → 코드로 계산한 성과 지표 → AI 는 구성 패턴 추상화만.

- 수집은 YouTube Data API(키가 있을 때) 또는 공개 페이지 메타데이터(yt-dlp, 로그인·다운로드 없음)만 쓴다.
- 영상 파일은 내려받지 않는다. 그래서 컷 편집·자막 디자인은 '미수집'으로 남긴다(지어내지 않는다).
- 시청 지속률·클릭률·수익 같은 비공개 지표는 만들지 않는다. 일평균 조회수 등은 공개 지표로 계산한 추정이다.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import re
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from .llm import ask_structured
from ..config import env

KST = dt.timezone(dt.timedelta(hours=9))
PATTERN_TYPES = ("궁금증 유발형", "충격 사실 공개형", "근황·후속형", "사건 반전형", "비교·순위형",
                 "감동·공감형", "뉴스 요약형", "문제 제기→해결형", "기타")
# 패턴 유형 → 기존 제작 구조(benchmarks/v1/integration.yaml). AI 가 고른 값이 목록에 없을 때 쓴다.
PROFILE_FOR = {"궁금증 유발형": "curiosity_update_story", "근황·후속형": "curiosity_update_story",
               "충격 사실 공개형": "illustrated_fact_explainer", "뉴스 요약형": "illustrated_fact_explainer",
               "사건 반전형": "event_timeline_story", "감동·공감형": "event_timeline_story",
               "비교·순위형": "ranked_moments", "문제 제기→해결형": "mechanism_explainer", "기타": "curiosity_update_story"}
UNCOLLECTED = ["컷 편집·장면 전환 패턴 (영상 파일을 내려받지 않음)", "자막 디자인·위치 (영상 프레임 미수집)",
               "시청 지속률·클릭률·수익 (비공개 지표)"]
MAX_SHORTS_SECONDS = 180


# ---------- 1. 채널 주소 ----------

def channel_url(text: str) -> str:
    """@핸들 · 채널 URL → 쇼츠 탭 URL."""
    t = (text or "").strip()
    if re.fullmatch(r"@[\w.\-가-힣]{2,100}", t):
        return f"https://www.youtube.com/{t}/shorts"
    m = re.match(r"https?://(?:www\.|m\.)?youtube\.com/(@[^/?#]+|channel/UC[\w-]{20,}|c/[^/?#]+|user/[^/?#]+)", t)
    if not m:
        raise ValueError("유튜브 채널 주소(https://www.youtube.com/@이름) 또는 @채널명을 입력해 주세요.")
    return f"https://www.youtube.com/{m[1]}/shorts"


# ---------- 2. 수집 ----------

def _ydl(opts: dict[str, Any], korean: bool = True):
    """korean: 상세 조회는 한국어 제목. 목록은 기본 언어로 읽어야 조회수·구독자 수 표기를 yt-dlp 가 숫자로 읽는다."""
    from .youtube import _ydl as base
    return base({"skip_download": True, **({"extractor_args": {"youtube": {"lang": ["ko"]}}} if korean else {}), **opts})


def _date(upload_date: str | None, timestamp: float | None) -> str:
    if timestamp:
        return dt.datetime.fromtimestamp(timestamp, KST).isoformat(timespec="minutes")
    if upload_date and re.fullmatch(r"\d{8}", upload_date):
        return dt.datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=KST).date().isoformat()
    return ""


def _list_sync(url: str, n: int) -> tuple[dict, list[dict]]:
    with _ydl({"extract_flat": "in_playlist", "playlistend": n}, korean=False) as y:
        info = y.extract_info(url, download=False)
    channel = {"id": info.get("channel_id") or "", "name": info.get("channel") or info.get("uploader") or "",
               "handle": info.get("uploader_id") or "", "subscribers": info.get("channel_follower_count"),
               "url": url.removesuffix("/shorts")}
    rows = [{"id": e["id"], "title": e.get("title") or "", "listed_views": e.get("view_count")}
            for e in info.get("entries") or [] if e.get("id")]
    return channel, rows


def _detail_sync(video_id: str) -> dict:
    with _ydl({}) as y:
        i = y.extract_info(f"https://www.youtube.com/shorts/{video_id}", download=False)
    return {"id": video_id, "title": i.get("title") or "", "views": i.get("view_count"), "likes": i.get("like_count"),
            "comments": i.get("comment_count"), "duration": i.get("duration"),
            "published": _date(i.get("upload_date"), i.get("timestamp")),
            "description": (i.get("description") or "")[:200], "tags": (i.get("tags") or [])[:8],
            "has_auto_subs": bool(i.get("automatic_captions") or i.get("subtitles"))}


async def _scan_pages(channel_text: str, latest: int, popular: int, listed: int, workers: int, log) -> dict:
    url = channel_url(channel_text)
    log(f"[channel] 쇼츠 목록 수집: {url}")
    channel, rows = await asyncio.to_thread(_list_sync, url, listed)
    if not rows:
        raise ValueError("공개 쇼츠를 찾지 못했습니다. 채널 주소를 확인해 주세요.")
    pick = rows[:latest]
    rest = sorted(rows[latest:], key=lambda r: r["listed_views"] or 0, reverse=True)[:popular]
    targets = pick + rest
    log(f"[channel] 목록 {len(rows)}개 중 최신 {len(pick)} + 인기 {len(rest)}개 상세 조회")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [asyncio.get_running_loop().run_in_executor(pool, _detail_sync, r["id"]) for r in targets]
        results = await asyncio.gather(*futures, return_exceptions=True)
    videos, failed = [], 0
    for r, d in zip(targets, results):
        if isinstance(d, Exception):
            failed += 1
            continue
        if d["duration"] and d["duration"] > MAX_SHORTS_SECONDS:
            continue
        d["views"] = d["views"] if d["views"] is not None else r["listed_views"]
        d["listed_order"] = rows.index(r) + 1
        videos.append(d)
    return {"channel": channel, "source": "공개 페이지 메타데이터 (yt-dlp, 로그인·다운로드 없음)",
            "coverage": {"listed": len(rows), "detailed": len(videos), "detail_failed": failed,
                         "latest_requested": latest, "popular_requested": popular,
                         "note": "인기 쇼츠는 목록에 보이는 최근 최대 %d개 안에서 조회수 순으로 골랐다" % listed},
            "videos": videos}


def _iso_seconds(text: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


async def _scan_api(channel_text: str, key: str, listed: int, log) -> dict:
    """YouTube Data API v3 (무료 할당량). 업로드 목록의 길이 3분 이하 영상을 쇼츠로 본다."""
    url = channel_url(channel_text)
    ref = url.removeprefix("https://www.youtube.com/").removesuffix("/shorts")
    params = {"part": "snippet,statistics,contentDetails", "key": key}
    params.update({"forHandle": ref} if ref.startswith("@") else {"id": ref.split("/", 1)[1]} if ref.startswith("channel/")
                  else {"forUsername": ref.split("/", 1)[1]})
    base = "https://www.googleapis.com/youtube/v3/"
    async with httpx.AsyncClient(timeout=20) as client:
        items = (await client.get(base + "channels", params=params)).raise_for_status().json().get("items") or []
        if not items:
            raise ValueError("채널을 찾지 못했습니다.")
        ch = items[0]
        uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
        ids, token = [], None
        while len(ids) < listed:
            q = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50, "key": key, **({"pageToken": token} if token else {})}
            page = (await client.get(base + "playlistItems", params=q)).raise_for_status().json()
            ids += [x["contentDetails"]["videoId"] for x in page.get("items", [])]
            token = page.get("nextPageToken")
            if not token:
                break
        videos = []
        for i in range(0, len(ids[:listed]), 50):
            q = {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50]), "key": key}
            for v in (await client.get(base + "videos", params=q)).raise_for_status().json().get("items", []):
                sec = _iso_seconds(v["contentDetails"].get("duration", ""))
                if not 0 < sec <= MAX_SHORTS_SECONDS:
                    continue
                s = v.get("statistics", {})
                published = dt.datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00")).astimezone(KST)
                videos.append({"id": v["id"], "title": v["snippet"].get("title", ""), "views": int(s.get("viewCount", 0)),
                               "likes": int(s["likeCount"]) if "likeCount" in s else None,
                               "comments": int(s["commentCount"]) if "commentCount" in s else None, "duration": sec,
                               "published": published.isoformat(timespec="minutes"),
                               "description": v["snippet"].get("description", "")[:200], "tags": v["snippet"].get("tags", [])[:8],
                               "listed_order": len(videos) + 1, "has_auto_subs": True})
    stats = ch.get("statistics", {})
    log(f"[channel] YouTube Data API: 업로드 {len(ids)}개 중 쇼츠 길이 {len(videos)}개")
    return {"channel": {"id": ch["id"], "name": ch["snippet"]["title"], "handle": ch["snippet"].get("customUrl", ""),
                        "subscribers": None if stats.get("hiddenSubscriberCount") else int(stats.get("subscriberCount", 0)),
                        "url": url.removesuffix("/shorts")},
            "source": "YouTube Data API v3",
            "coverage": {"listed": len(ids), "detailed": len(videos), "detail_failed": 0,
                         "note": "길이 3분 이하 업로드를 쇼츠로 보았다 (API 는 쇼츠 여부를 직접 알려 주지 않음)"},
            "videos": videos}


async def scan(channel_text: str, *, latest: int = 30, popular: int = 15, listed: int = 150, workers: int = 4,
               log=print) -> dict:
    key = env("YOUTUBE_API_KEY")
    data = await (_scan_api(channel_text, key, listed, log) if key else _scan_pages(channel_text, latest, popular, listed, workers, log))
    data["scanned_at"] = dt.datetime.now(KST).isoformat(timespec="seconds")
    return data


# ---------- 3. 코드로 계산하는 지표 ----------

def _median(values: list[float]) -> float:
    values = [v for v in values if v is not None]
    return float(statistics.median(values)) if values else 0.0


def metrics(data: dict, previous: dict | None = None, now: dt.datetime | None = None) -> dict:
    """게시 후 경과일·일평균 조회수·나이 보정 배수·구독자 대비·그룹. previous 가 있으면 실제 조회수 증가량도 계산."""
    now = now or dt.datetime.now(KST)
    videos = [v for v in data["videos"] if v.get("views") is not None and v.get("published")]
    subs = data["channel"].get("subscribers")
    before = {v["id"]: v["views"] for v in (previous or {}).get("videos", [])}
    gap = 0.0
    if previous and previous.get("scanned_at"):
        gap = (now - dt.datetime.fromisoformat(previous["scanned_at"])).total_seconds() / 86400
    for v in videos:
        published = dt.datetime.fromisoformat(v["published"])
        published = published if published.tzinfo else published.replace(tzinfo=KST)
        v["age_days"] = round(max(1.0, (now - published).total_seconds() / 86400), 1)
        v["views_per_day"] = round(v["views"] / v["age_days"], 1)
        v["hour_kst"] = published.hour if "T" in v["published"] else None
        v["weekday"] = "월화수목금토일"[published.weekday()]
        v["vs_subscribers"] = round(v["views"] / subs, 2) if subs else None
        if v["id"] in before and gap >= 0.5:
            v["views_gain_per_day"] = round((v["views"] - before[v["id"]]) / gap, 1)
    med = _median([v["views"] for v in videos]) or 1
    med_vpd = _median([v["views_per_day"] for v in videos]) or 1
    # 나이 보정: 비슷한 시기에 올린 영상들의 조회수 중앙값 대비 배수 (오래된 영상이 누적 조회수로만 앞서지 않게)
    buckets = [(0, 7), (7, 30), (30, 90), (90, 10 ** 6)]
    for lo, hi in buckets:
        group = [v for v in videos if lo < v["age_days"] <= hi]
        bucket_med = _median([v["views"] for v in group]) if len(group) >= 3 else med
        for v in group:
            v["age_adjusted"] = round(v["views"] / (bucket_med or 1), 2)
    for v in videos:
        v["vs_median"] = round(v["views"] / med, 2)
        groups = []
        if v.get("listed_order", 999) <= 30:
            groups.append("최신")
        if v["age_days"] <= 14 and v["views_per_day"] >= 2 * med_vpd:
            groups.append("급상승(추정)")
        if v.get("views_gain_per_day") is not None and v["views_gain_per_day"] >= 2 * med_vpd:
            groups.append("급상승(실측)")
        if v["age_adjusted"] >= 2:
            groups.append("고성과")
        if v["vs_subscribers"] is not None and v["vs_subscribers"] >= 1:
            groups.append("구독자 초과")
        v["groups"] = groups
    for v in sorted(videos, key=lambda v: v["views"], reverse=True)[:10]:
        v["groups"].append("인기 상위")
    recent = [v for v in videos if v["age_days"] <= 28]
    hours = Counter(v["hour_kst"] for v in videos if v["hour_kst"] is not None)
    latest = [v for v in videos if "최신" in v["groups"]]
    data["videos"] = sorted(videos, key=lambda v: v.get("listed_order", 999))
    data["stats"] = {
        "videos": len(videos), "subscribers": subs, "median_views": med, "median_views_per_day": med_vpd,
        "median_views_latest": _median([v["views"] for v in latest]),
        "median_views_top10": _median([v["views"] for v in videos if "인기 상위" in v["groups"]]),
        "median_duration": _median([v["duration"] for v in videos if v.get("duration")]),
        "uploads_per_week": round(len(recent) / 4, 1), "upload_hours_kst": [f"{h}시 ({n}편)" for h, n in hours.most_common(3)],
        "weekdays": [f"{d} ({n}편)" for d, n in Counter(v["weekday"] for v in videos).most_common(3)],
        "date_range": [min(v["published"] for v in videos)[:10], max(v["published"] for v in videos)[:10]] if videos else [],
        "real_growth_measured": bool(before and gap >= 0.5),
        "notes": ["일평균 조회수·급상승(추정)은 누적 조회수 ÷ 경과일로 계산한 추정이다",
                  "급상승(실측)은 이전 분석과 비교한 실제 조회수 증가량이다" if before else "다시 분석하면 실제 조회수 증가량(실측)을 계산한다",
                  "업로드 빈도는 최근 28일, 시간대는 한국 시간 기준"],
    }
    return data


def standouts(data: dict, k: int = 6) -> list[dict]:
    """대본 구조를 볼 영상: 나이 보정 성과 상위 + 최신 2편."""
    ranked = sorted(data["videos"], key=lambda v: v.get("age_adjusted", 0), reverse=True)[:k - 2]
    for v in data["videos"][:2]:
        if v not in ranked:
            ranked.append(v)
    return ranked


async def add_transcripts(data: dict, workdir: Path, k: int = 6, log=print) -> None:
    """공개 자동 자막으로 첫 3초 문장과 말 속도만 본다. 원문은 분석 캐시에만 두고 제작 프롬프트에는 넣지 않는다."""
    from .youtube import fetch_transcript
    got = 0
    for v in standouts(data, k):
        if not v.get("has_auto_subs"):
            continue
        d = workdir / v["id"]
        d.mkdir(parents=True, exist_ok=True)
        words = await fetch_transcript(f"https://www.youtube.com/shorts/{v['id']}", d)
        if not words:
            continue
        text = " ".join(w.text for w in words).strip()
        span = max(0.1, words[-1].end - words[0].start)
        v["hook_3s"] = " ".join(w.text for w in words if w.start < 3.0).strip()
        v["chars_per_sec"] = round(len(re.sub(r"\s", "", text)) / span, 1)
        v["transcript"] = text[:1200]
        got += 1
    data["coverage"]["transcripts"] = got
    log(f"[channel] 공개 자막 {got}편 확인")


# ---------- 4. AI 패턴 추상화 ----------

class Pattern(BaseModel):
    type: Literal[PATTERN_TYPES]
    name: str = Field(description="짧은 패턴 이름 (예: '반전 근황 공개')")
    evidence_video_ids: list[str] = Field(description="이 패턴에 속하는 영상 id (표에 있는 것만)")
    observed: list[str] = Field(description="데이터에서 직접 확인한 사실 (제목·조회수·길이·자막에 근거)")
    hypotheses: list[str] = Field(description="성과가 좋은 이유에 대한 가설 (확인되지 않음)")
    hook_formula: str = Field(description="첫 3초 후킹 공식 (구체 문장 복사 금지, 형식만)")
    retention_structure: str = Field(description="중간 이탈을 줄이는 이야기 구성")
    reveal_order: list[str] = Field(description="정보 공개 순서 단계")
    twist_position: str = Field(description="반전·결말 위치 (예: 마지막 20%)")
    recommended_seconds: int = Field(ge=10, le=60)
    screen_and_subtitles: str = Field(description="화면·자막 구성 제안. 영상을 보지 않았으므로 제목·자막 근거의 제안임을 밝힌다")
    good_topics: list[str] = Field(description="이 패턴을 적용하기 좋은 주제 유형")
    profile_id: str = Field(description="제작 구조 id (목록 중 하나)")


class TopicIdea(BaseModel):
    title: str = Field(description="새 쇼츠 주제 (벤치마킹 영상 제목과 다르게)")
    angle: str = Field(description="시청 질문·관점")
    pattern_index: int = Field(ge=0, description="patterns 배열의 번호 (0부터)")
    why: str = Field(description="추천 이유 (관찰 근거 + 가설 구분)")
    needs_research: str = Field(description="제작 전에 새로 조사할 사실")
    search_query: str = Field(default="", description="자료 조사에 넣을 주제 문장. 분야·대상·시기를 넣어 혼자 검색해도 "
                                                      "다른 분야와 헷갈리지 않게 (예: '2025년 K팝 신인 걸그룹 신인상 후보들의 현재 활동')")


class ChannelAnalysis(BaseModel):
    summary: str
    recurring_topics: list[str] = Field(description="반복적으로 등장하는 인기 소재")
    narration: str = Field(description="내레이션 속도·분위기 (자막 말 속도 근거, 없으면 '미확인')")
    source_usage: str = Field(description="이미지·영상 소스 활용 (설명·태그 근거, 없으면 '미확인')")
    audience_interest: str = Field(description="댓글·반응에서 본 시청자 관심사 (자료 없으면 '미수집')")
    patterns: list[Pattern] = Field(min_length=1, max_length=5)
    topic_ideas: list[TopicIdea] = Field(min_length=5, max_length=5)


SYSTEM = """너는 유튜브 쇼츠 구성 분석가다. 공개 지표 표와 공개 자동 자막 일부만 보고 반복되는 성공 패턴을 추상화한다.
규칙:
- 관찰(observed)은 표·자막에서 확인되는 것만 쓴다. 이유는 가설(hypotheses)로 분리한다.
- 성과 판단은 '나이 보정 배수'와 일평균 조회수를 우선한다. 오래돼서 누적 조회수가 큰 영상을 과대평가하지 않는다.
- 시청 지속률·클릭률·수익 같은 비공개 지표를 추측하거나 숫자로 만들지 않는다.
- 컷 편집·자막 디자인은 영상을 보지 않았으므로 단정하지 않는다.
- 후킹 공식과 구성은 형식만 일반화한다. 원본 문장·제목·대사를 그대로 옮기지 않는다.
- 추천 주제의 search_query 에는 채널 분야(예: K팝·유튜버)와 대상을 꼭 넣는다. 제목만으로는 다른 분야로 조사될 수 있다.
- 추천 주제는 새 자료 조사로 만들 독창적인 주제다. 원본 영상과 같은 제목·같은 대본이 되면 안 된다. 조회수를 보장하는 표현을 쓰지 않는다."""


def _table(data: dict) -> str:
    rows = ["id | 게시 경과일 | 길이(초) | 조회수 | 일평균 | 나이보정배수 | 그룹 | 제목"]
    for v in data["videos"]:
        rows.append(f"{v['id']} | {v['age_days']:.0f} | {v.get('duration') or '?'} | {v['views']} | {v['views_per_day']:.0f} | "
                    f"{v.get('age_adjusted', 0)} | {','.join(v['groups'])} | {v['title'][:60]}")
    return "\n".join(rows)


async def analyze(llm: dict, data: dict, profiles: list[str], comments: list[str] | None = None) -> dict:
    s = data["stats"]
    subs = [f"- {v['id']} (나이보정 {v.get('age_adjusted')}배, 말속도 {v.get('chars_per_sec')}자/초)\n  첫 3초: {v.get('hook_3s', '')}\n"
            f"  자막 일부: {v.get('transcript', '')[:500]}" for v in data["videos"] if v.get("transcript")]
    user = (f"[채널] {data['channel'].get('name')} · 구독자 {s['subscribers'] or '비공개'}\n"
            f"[지표] 분석 {s['videos']}편 · 조회수 중앙값 {s['median_views']:.0f} · 최신 30편 중앙값 {s['median_views_latest']:.0f} · "
            f"인기 상위10 중앙값 {s['median_views_top10']:.0f} · 길이 중앙값 {s['median_duration']:.0f}초 · 주당 업로드 {s['uploads_per_week']} · "
            f"시간대 {', '.join(s['upload_hours_kst'])}\n\n[영상 표]\n{_table(data)}\n\n[공개 자동 자막]\n" + ("\n".join(subs) or "없음")
            + "\n\n[댓글 일부]\n" + ("\n".join(f"- {c}" for c in (comments or [])[:20]) or "미수집")
            + f"\n\n[제작 구조 id 목록] {', '.join(profiles)}\n패턴 1~5개와 새 주제 5개를 작성하세요.")
    result = (await ask_structured(llm, SYSTEM, user, ChannelAnalysis)).model_dump()
    return finish(result, data, profiles)


def finish(result: dict, data: dict, profiles: list[str]) -> dict:
    """AI 결과를 코드로 검증: 근거 영상 id 확인, 패턴별 실제 지표 계산, 제작 구조 보정, 원본과 비슷한 주제 표시."""
    by_id = {v["id"]: v for v in data["videos"]}
    for p in result["patterns"]:
        p["evidence_video_ids"] = [i for i in dict.fromkeys(p["evidence_video_ids"]) if i in by_id]
        ev = [by_id[i] for i in p["evidence_video_ids"]]
        p["stats"] = {"videos": len(ev), "median_views": _median([v["views"] for v in ev]),
                      "median_age_days": _median([v["age_days"] for v in ev]),
                      "median_age_adjusted": _median([v.get("age_adjusted", 0) for v in ev]),
                      "median_duration": _median([v.get("duration") or 0 for v in ev])}
        if p["profile_id"] not in profiles:
            p["profile_id"] = PROFILE_FOR[p["type"]] if PROFILE_FOR[p["type"]] in profiles else profiles[0]
    original = list(result["patterns"])
    result["patterns"].sort(key=lambda p: (p["stats"]["videos"] > 0, p["stats"]["median_age_adjusted"]), reverse=True)
    titles = [v["title"] for v in data["videos"]]
    for idea in result["topic_ideas"]:   # AI 가 매긴 패턴 번호를 성과순 정렬 뒤 번호로 옮긴다
        idea["pattern_index"] = result["patterns"].index(original[min(idea["pattern_index"], len(original) - 1)])
        similar = max((SequenceMatcher(None, idea["title"], t).ratio() for t in titles), default=0)
        idea["title_similarity"] = round(similar, 2)
        idea["too_similar"] = similar >= 0.6
    result["uncollected"] = list(UNCOLLECTED) + ([] if data["coverage"].get("comments") else ["댓글 (YouTube Data API 키 없음)"])
    return result


# ---------- 5. 제작에 반영 ----------

def make_options(analysis: dict, pattern_index: int = 0, idea: dict | None = None) -> dict:
    """make(...) 에 넘길 benchmark·seconds·instructions. 원본 대본은 넣지 않고 형식만 넣는다."""
    patterns = analysis["patterns"]
    p = patterns[min(max(pattern_index, 0), len(patterns) - 1)]
    lines = [f"[벤치마킹 패턴: {analysis.get('channel_name', '')} · {p['type']} '{p['name']}']",
             f"- 첫 3초 후킹: {p['hook_formula']}",
             f"- 이탈 방지 구성: {p['retention_structure']}",
             f"- 정보 공개 순서: {' → '.join(p['reveal_order'])}",
             f"- 반전·결말 위치: {p['twist_position']}",
             f"- 화면·자막: {p['screen_and_subtitles']}"]
    if idea:
        lines.append(f"- 시청 질문: {idea['angle']} / 새로 조사할 것: {idea['needs_research']}")
    lines.append("- 구성 기법만 참고한다. 벤치마킹 영상의 제목·문장·대사를 옮기지 말고 새 자료 조사로 독창적인 대본을 쓴다. 조회수를 보장하는 표현은 쓰지 않는다.")
    return {"benchmark": p["profile_id"], "seconds": int(p["recommended_seconds"]), "instructions": "\n".join(lines)}


def compare(analyses: list[dict]) -> dict:
    """여러 채널의 공통 패턴 (AI 추가 호출 없음): 유형별 등장 채널 수와 나이 보정 성과."""
    table: dict[str, dict] = {}
    for a in analyses:
        for i, p in enumerate(a["patterns"]):
            row = table.setdefault(p["type"], {"type": p["type"], "channels": [], "median_age_adjusted": [], "refs": []})
            if a["channel_id"] not in row["channels"]:
                row["channels"].append(a["channel_id"])
            row["median_age_adjusted"].append(p["stats"]["median_age_adjusted"])
            row["refs"].append({"channel_id": a["channel_id"], "pattern_index": i, "name": p["name"]})
    rows = []
    for row in table.values():
        row["median_age_adjusted"] = _median(row["median_age_adjusted"])
        row["common"] = len(row["channels"]) >= 2
        rows.append(row)
    rows.sort(key=lambda r: (len(r["channels"]), r["median_age_adjusted"]), reverse=True)
    best = {r["type"] for r in rows if r["common"]} or ({rows[0]["type"]} if rows else set())
    ideas = []
    for a in analyses:
        for idea in a["topic_ideas"]:
            p = a["patterns"][idea["pattern_index"]]
            if p["type"] in best and not idea.get("too_similar"):
                ideas.append({**idea, "channel_id": a["channel_id"], "type": p["type"]})
    return {"patterns": rows, "common_types": sorted(best), "topic_ideas": ideas,
            "note": "공통 유형은 2개 이상 채널에서 나온 패턴. 성과 배수는 각 채널 안에서 계산한 나이 보정 값의 중앙값이다."}


def overlap(text: str, references: list[str], n: int = 12) -> float:
    """새 대본과 원본 자막이 n글자 단위로 겹치는 비율 (복사 감시용, 0~1)."""
    def grams(s: str) -> set[str]:
        s = re.sub(r"\s", "", s or "")
        return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}
    mine = grams(text)
    if not mine:
        return 0.0
    theirs = set().union(*(grams(r) for r in references)) if references else set()
    return round(len(mine & theirs) / len(mine), 3)
