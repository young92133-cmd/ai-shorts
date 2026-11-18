"""원본 영상 링크 → 그 영상(같은 곡·무대)으로 만든 쇼츠 중 조회수 높은 것 찾기 + 분석용 장면 모음 이미지.

흐름: 원본 정보(제목·채널·업로드일) → 검색어 여러 개로 YouTube 쇼츠 검색(쇼츠 필터) → 조회수 순 →
상위 후보의 상세 정보(채널 구독자·업로드일·길이) → 원본 이후 올라온 같은 곡 쇼츠 우선 → 저화질로 받아
장면 모음 이미지(시각 표시)를 만든다. 자막·구성 판독은 채팅의 AI 가 이 이미지를 보고 한다(프로그램은 비전 API 를 쓰지 않는다).
팬 클립은 고른 쇼츠의 구조·말투만 따라 하고 문장은 새로 쓴다(fanclip --follow).
"""
from __future__ import annotations

import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SHORTS_FILTER = "EgIYAQ%253D%253D"
PROGRAMS = {  # 방송사 무대 채널 → 프로그램 이름 (검색어·같은 방송 추정에 사용)
    "inkigayo": "인기가요", "sbskpop": "인기가요", "mbckpop": "음악중심", "kbs kpop": "뮤직뱅크",
    "mnet k-pop": "엠카운트다운", "m2": "엠카운트다운", "the show": "더쇼", "show champion": "쇼챔피언",
}
_NUM = {"천": 1e3, "만": 1e4, "억": 1e8}


def parse_views(text: str) -> int:
    m = re.search(r"([\d.,]+)\s*(천|만|억)?", (text or "").replace("조회수", ""))
    if not m:
        return 0
    return int(float(m.group(1).replace(",", "")) * _NUM.get(m.group(2) or "", 1))


def _walk(obj: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        s = obj.get("shortsLockupViewModel")
        if s:
            vid = (s.get("onTap", {}).get("innertubeCommand", {}).get("reelWatchEndpoint", {}) or {}).get("videoId")
            meta = s.get("overlayMetadata", {})
            if vid:
                views = (meta.get("secondaryText") or {}).get("content", "")
                out.append({"id": vid, "title": (meta.get("primaryText") or {}).get("content", ""),
                            "views_text": views, "views": parse_views(views)})
        for v in obj.values():
            _walk(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, out)


def search_shorts(query: str, timeout: int = 20) -> list[dict[str, Any]]:
    """YouTube 검색 결과 페이지(쇼츠 필터)를 읽는다. 로그인·API 키 없음."""
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}&sp={SHORTS_FILTER}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"})
    html = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    if not m:
        return []
    out: list[dict[str, Any]] = []
    _walk(json.loads(m.group(1)), out)
    return out


_STOP = {"영상", "공식", "풀버전", "full", "official", "video", "shorts", "쇼츠", "ep", "회", "방송", "최초", "공개", "단독",
         "클립", "clip", "하이라이트", "highlight", "다시보기", "레전드", "모음", "the", "and", "with", "feat", "mv", "live"}
_MUSIC_CHAN = re.compile(r"kpop|k-pop|music|inkigayo|뮤직|음악|mbckpop|kbs kpop|mnet|m2|1thek|dingo", re.I)


def topic_words(text: str, limit: int = 6) -> list[str]:
    """제목에서 검색에 쓸 핵심 단어(한글 2자+, 영문 3자+). 괄호·해시태그·'|' 뒤 채널 표기는 뺀다."""
    head = re.sub(r"#\S+", " ", text.split("|")[0])
    head = re.sub(r"[\[\]【】()「」『』<>“”\"'’‘·…!?~,.:;/]", " ", head)
    words: list[str] = []
    for w in re.findall(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9]{2,}", head):
        if w.lower() not in _STOP and w not in words:
            words.append(w)
    return words[:limit]


def source_keys(info: dict[str, Any]) -> dict[str, Any]:
    """원본 제목에서 검색 열쇠를 뽑는다.
    음악 무대(예: '연애의 조건 - BESTie (베스티) | SBS 261115 방송'): 곡·가수·프로그램·날짜 코드.
    그 밖(예능·인터뷰·뉴스·이슈·팬 영상): 핵심 단어·채널 이름. kind 로 구분한다."""
    title = info.get("title", "")
    chan_raw = info.get("channel") or ""
    head = title.split("|")[0]
    parts = [p.strip() for p in re.split(r"\s[-–]\s", head) if p.strip()]
    chan = chan_raw.lower()
    program = next((v for k, v in PROGRAMS.items() if k in chan), "")
    date = (re.search(r"\b(\d{6})\b", title) or [None, ""])[1]
    words = topic_words(title)
    music = len(parts) >= 2 and bool(program or _MUSIC_CHAN.search(chan_raw))
    if not music:
        return {"kind": "general", "song": "", "artist": "", "artist_latin": "", "program": program,
                "date_code": date, "topic": words, "channel": chan_raw}
    song = re.sub(r"[\[\]()]", " ", parts[0]).strip()
    artist_raw = parts[1]
    korean = re.findall(r"[가-힣]{2,}", artist_raw)
    artist = korean[0] if korean else re.sub(r"\(.*?\)", "", artist_raw).strip()
    latin = re.sub(r"\(.*?\)", "", artist_raw).strip()
    return {"kind": "music", "song": song, "artist": artist, "artist_latin": latin if latin != artist else "",
            "program": program, "date_code": date, "topic": words, "channel": chan_raw}


def queries(keys: dict[str, Any], extra: list[str] | None = None) -> list[str]:
    if keys.get("kind") == "music":
        a, s, p = keys["artist"], keys["song"], keys["program"]
        qs = [f"{a} {s}", f"{a} {p}" if p else "", f"{keys['artist_latin']} {s}" if keys["artist_latin"] else "",
              f"{a} {s} {p}" if p else "", f"{a} 무대"]
    else:   # 팬튜브·이슈: 핵심 단어 조합 + 앞 두 단어(보통 인물·프로그램)
        w = keys.get("topic") or []
        qs = [" ".join(w[:4]), " ".join(w[:2]), " ".join(w[:3]),
              f"{w[0]} {w[2]}" if len(w) > 2 else "", f"{w[0]} 쇼츠" if w else ""]
    out: list[str] = []
    for q in [*qs, *(extra or [])]:
        q = " ".join(q.split())
        if q and q not in out:
            out.append(q)
    return out


def _details(vid: str) -> dict[str, Any]:
    from .youtube import _ydl

    with _ydl({"skip_download": True}) as y:
        i = y.extract_info(f"https://www.youtube.com/shorts/{vid}", download=False)
    return {"channel": i.get("channel") or i.get("uploader", ""), "channel_url": i.get("channel_url", ""),
            "subscribers": i.get("channel_follower_count"), "upload_date": i.get("upload_date", ""),
            "duration": float(i.get("duration") or 0), "view_count": i.get("view_count"),
            "description": (i.get("description") or "")[:300]}


def relevance(c: dict[str, Any], keys: dict[str, Any], source_date: str) -> dict[str, Any]:
    text = f"{c.get('title', '')} {c.get('description', '')}"
    if keys.get("kind") == "music":
        same_song = keys["song"].replace(" ", "") in text.replace(" ", "")
    else:   # 같은 주제: 원본 핵심 단어가 2개 이상(단어가 적으면 1개) 겹침
        words = keys.get("topic") or []
        hits = sum(1 for w in words if w.lower() in text.lower())
        same_song = hits >= (2 if len(words) >= 3 else 1)
    same_program = bool(keys["program"] and keys["program"] in text) or bool(
        keys["date_code"] and (keys["date_code"] in text or f"{keys['date_code'][2:4]}/{keys['date_code'][4:]}" in text))
    after = bool(source_date and c.get("upload_date") and c["upload_date"] >= source_date)
    return {"same_topic": same_song, "same_program_guess": same_program, "after_source": after}


def find(url: str, limit: int = 10, extra_queries: list[str] | None = None, pool: int = 25,
         log=lambda m: None) -> dict[str, Any]:
    from .youtube import _info_sync

    info = _info_sync(url)
    with __import__("yt_dlp").YoutubeDL({"quiet": True, "skip_download": True, "noplaylist": True}) as y:
        full = y.extract_info(info.get("webpage_url") or url, download=False)
    source_date = full.get("upload_date", "")
    keys = source_keys(info)
    seen: dict[str, dict[str, Any]] = {}
    qs = queries(keys, extra_queries)
    for q in qs:
        log(f"[search] {q}")
        try:
            for c in search_shorts(q):
                if c["id"] != info.get("id") and (c["id"] not in seen or c["views"] > seen[c["id"]]["views"]):
                    seen[c["id"]] = {**c, "query": q}
        except Exception as e:  # noqa: BLE001 - 검색어 하나 실패해도 계속
            log(f"[search] 실패: {q} ({e})")
    ranked = sorted(seen.values(), key=lambda c: c["views"], reverse=True)[:pool]
    out = []
    for c in ranked:
        try:
            c = {**c, **_details(c["id"])}
        except Exception as e:  # noqa: BLE001 - 비공개·삭제 등은 건너뛴다
            log(f"[detail] 건너뜀 {c['id']}: {e}")
            continue
        if c["duration"] and c["duration"] > 180:
            continue
        c["views"] = int(c.get("view_count") or c["views"])
        c["url"] = f"https://www.youtube.com/shorts/{c['id']}"
        c["relevance"] = relevance(c, keys, source_date)
        subs = c.get("subscribers") or 0
        c["views_per_sub"] = round(c["views"] / subs, 1) if subs else None
        out.append(c)
    # 원본 이후 + 같은 곡을 먼저, 그 안에서 조회수 순
    out.sort(key=lambda c: (c["relevance"]["after_source"] and c["relevance"]["same_topic"], c["views"]), reverse=True)
    return {"source": {"url": info.get("webpage_url", url), "title": info.get("title", ""),
                       "channel": info.get("channel", ""), "upload_date": source_date, "keys": keys},
            "queries": qs, "candidates": out[:limit]}


# ---------- 분석용 장면 모음 ----------

def download_short(url: str, dest: Path) -> Path:
    from .youtube import _ydl

    dest.mkdir(parents=True, exist_ok=True)
    vid = url.rstrip("/").split("/")[-1]
    opts = {"format": "best[height<=720][ext=mp4]/bestvideo[height<=720]+bestaudio/best",
            "outtmpl": str(dest / f"{vid}.%(ext)s"), "merge_output_format": "mp4"}
    with _ydl(opts) as y:
        y.download([url])
    return next(dest.glob(f"{vid}.*"))


def contact_sheets(video: Path, out_dir: Path, frames: int = 16, per_sheet: int = 8) -> list[Path]:
    """자막을 읽을 수 있는 크기로 장면을 뽑아 시각을 찍은 모음 이미지(4x2)를 만든다."""
    from PIL import Image, ImageDraw

    from .clip_analyzer import _ff  # noqa: F401 - ffmpeg 경로 확인용
    from .fanclip import _font

    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True)
    dur = float(p.stdout.strip() or 0)
    out_dir.mkdir(parents=True, exist_ok=True)
    times = [round(0.3 + i * max(0.1, dur - 0.6) / max(1, frames - 1), 2) for i in range(frames)]
    shots: list[tuple[float, Path]] = []
    for t in times:
        f = out_dir / f"_f{t:06.2f}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=360:-2", str(f)], check=False)
        if f.exists():
            shots.append((t, f))
    sheets = []
    font = _font("Bold", 22)
    for k in range(0, len(shots), per_sheet):
        chunk = shots[k:k + per_sheet]
        ims = [Image.open(f).convert("RGB") for _, f in chunk]
        w, h = ims[0].size
        sheet = Image.new("RGB", (w * 4, h * 2), (0, 0, 0))
        for n, (im, (t, _)) in enumerate(zip(ims, chunk)):
            x, y = (n % 4) * w, (n // 4) * h
            sheet.paste(im.resize((w, h)), (x, y))
            ImageDraw.Draw(sheet).text((x + 6, y + 4), f"{t:.1f}s", font=font, fill=(255, 230, 0),
                                       stroke_width=3, stroke_fill=(0, 0, 0))
        path = out_dir / f"sheet_{k // per_sheet + 1}.jpg"
        sheet.save(path, quality=88)
        sheets.append(path)
    for _, f in shots:
        f.unlink(missing_ok=True)
    return sheets
