"""유튜브 URL 처리: 메타데이터, 자막(단어 타임스탬프), 영상/오디오 다운로드, whisper 대체 전사."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from .models import Word


def _ydl(opts: dict[str, Any]):
    import yt_dlp

    base = {"quiet": True, "no_warnings": True, "noprogress": True, "retries": 3}
    return yt_dlp.YoutubeDL({**base, **opts})


def _info_sync(url: str) -> dict[str, Any]:
    with _ydl({"skip_download": True}) as y:
        info = y.extract_info(url, download=False)
    return {
        "id": info.get("id"),
        "title": info.get("title", ""),
        "description": info.get("description", ""),
        "duration": float(info.get("duration") or 0),
        "channel": info.get("channel") or info.get("uploader", ""),
        "webpage_url": info.get("webpage_url", url),
        "has_subs": bool(info.get("subtitles")),
        "has_auto_subs": bool(info.get("automatic_captions")),
    }


async def fetch_info(url: str) -> dict[str, Any]:
    return await asyncio.to_thread(_info_sync, url)


def _parse_json3(path: Path) -> list[Word]:
    """유튜브 json3 자막 → 단어 목록. 자동자막은 단어 단위, 수동자막은 큐 단위(균등 분배)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    words: list[Word] = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs or "tStartMs" not in ev:
            continue
        t0 = ev["tStartMs"] / 1000
        dur = ev.get("dDurationMs", 0) / 1000
        toks = []
        for s in segs:
            txt = (s.get("utf8") or "").replace("\n", " ").strip()
            if txt:
                toks.append((txt, t0 + s.get("tOffsetMs", 0) / 1000))
        if not toks:
            continue
        # 단어 끝 = 다음 단어 시작 (마지막은 큐 끝)
        for i, (txt, st) in enumerate(toks):
            en = toks[i + 1][1] if i + 1 < len(toks) else t0 + dur
            # 한 세그먼트에 여러 단어가 들어있으면 글자 비율로 쪼갬
            parts = txt.split()
            if len(parts) > 1:
                total = sum(len(p) for p in parts)
                t = st
                for p in parts:
                    d = (en - st) * len(p) / total
                    words.append(Word(text=p, start=round(t, 3), end=round(t + d, 3)))
                    t += d
            else:
                words.append(Word(text=txt, start=round(st, 3), end=round(max(en, st + 0.05), 3)))
    return words


def _download_subs_sync(url: str, workdir: Path) -> list[Word] | None:
    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["ko", "ko-orig", "en"],
        "subtitlesformat": "json3",
        "outtmpl": str(workdir / "source.%(ext)s"),
        # 유튜브가 자막 요청에 429 를 자주 준다 - 요청 사이에 쉬고 여러 번 재시도
        "sleep_interval_subtitles": 2,
        "retries": 5,
        "extractor_retries": 3,
        "ignoreerrors": True,
    }

    def collect() -> list[Word] | None:
        for lang in ("ko", "ko-orig", "en"):
            p = workdir / f"source.{lang}.json3"
            if p.exists():
                words = _parse_json3(p)
                if words:
                    return words
        return None

    for attempt in range(3):
        try:
            with _ydl(opts) as y:
                y.download([url])
        except Exception:  # noqa: BLE001 - 자막은 없어도 진행 가능
            pass
        if words := collect():
            return words
        if attempt < 2:
            time.sleep(8 * (attempt + 1))  # 429 완화
    return None


async def fetch_transcript(url: str, workdir: Path) -> list[Word] | None:
    return await asyncio.to_thread(_download_subs_sync, url, workdir)


def _download_sync(url: str, workdir: Path, audio_only: bool) -> Path:
    if audio_only:
        opts = {"format": "bestaudio/best", "outtmpl": str(workdir / "source_audio.%(ext)s"),
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}]}
        pattern = "source_audio.*"
    else:
        opts = {"format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
                "outtmpl": str(workdir / "source.%(ext)s"), "merge_output_format": "mp4"}
        pattern = "source.mp4"
    with _ydl(opts) as y:
        y.download([url])
    files = sorted(workdir.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not files:
        raise RuntimeError("다운로드한 파일을 찾을 수 없습니다.")
    return files[-1]


async def download_media(url: str, workdir: Path, audio_only: bool) -> Path:
    return await asyncio.to_thread(_download_sync, url, workdir, audio_only)


def _whisper_sync(audio: Path, model_size: str = "small") -> list[Word]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("자막이 없는 영상입니다. `pip install faster-whisper` 후 다시 시도하세요.") from e
    model = WhisperModel(model_size, device="auto", compute_type="int8")
    segments, _ = model.transcribe(str(audio), language="ko", word_timestamps=True, vad_filter=True)
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            words.append(Word(text=w.word.strip(), start=round(w.start, 3), end=round(w.end, 3)))
    return words


async def transcribe(audio: Path) -> list[Word]:
    return await asyncio.to_thread(_whisper_sync, audio)


def words_to_lines(words: list[Word], window: float = 6.0) -> list[str]:
    """[12.3s] 문장 ... 형태의 라인으로 묶어 Claude 에게 보여주기 좋게 만든다."""
    lines: list[str] = []
    buf: list[str] = []
    t0 = words[0].start if words else 0.0
    for w in words:
        if buf and (w.start - t0 >= window):
            lines.append(f"[{t0:.1f}s] " + " ".join(buf))
            buf, t0 = [], w.start
        buf.append(w.text)
    if buf:
        lines.append(f"[{t0:.1f}s] " + " ".join(buf))
    return lines


def words_to_text(words: list[Word]) -> str:
    return " ".join(w.text for w in words)
