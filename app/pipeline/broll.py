"""영상 짜깁기(broll): 여러 소스 영상에서 장면별 구간을 골라 이어 붙인다.

정치·연예처럼 실제 화면이 있어야 설득되는 소재용. 대본을 먼저 쓰고, 각 장면의 나레이션 길이에
맞는 구간을 소스에서 찾는다. 원본 소리는 작게 깔고 나레이션을 위에 얹는다.

저작권: 소스당 사용 길이에 상한을 두고 모든 출처를 설명란에 기재하지만, 이는 완화 장치일 뿐
면책이 아니다. 인용 범위를 넘지 않도록 사용자가 최종 판단해야 한다.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .llm import ask_structured
from .models import BrollPick, BrollPlan, Script, SourceVideo
from .youtube import _ydl, download_media, fetch_transcript, words_to_lines

MIN_SOURCE_SEC = 30       # 너무 짧으면 쓸 구간이 없다
MAX_SOURCE_SEC = 20 * 60  # 너무 길면 다운로드·자막이 무겁다


# ---------- 1. 소스 수집 ----------

def _search_sync(query: str, n: int) -> list[SourceVideo]:
    """yt-dlp 검색. 메타만 받아오고 다운로드는 하지 않는다."""
    with _ydl({"skip_download": True, "extract_flat": True, "ignoreerrors": True}) as y:
        info = y.extract_info(f"ytsearch{n}:{query}", download=False)
    out: list[SourceVideo] = []
    for e in (info or {}).get("entries") or []:
        if not e:
            continue
        dur = float(e.get("duration") or 0)
        if not (MIN_SOURCE_SEC <= dur <= MAX_SOURCE_SEC):
            continue
        url = e.get("url") or e.get("webpage_url") or ""
        if not url:
            continue
        out.append(SourceVideo(url=url, title=e.get("title", ""), duration=dur,
                               channel=e.get("channel") or e.get("uploader") or ""))
    return out


def _info_sync(url: str) -> SourceVideo | None:
    with _ydl({"skip_download": True, "ignoreerrors": True}) as y:
        e = y.extract_info(url, download=False)
    if not e:
        return None
    return SourceVideo(url=e.get("webpage_url", url), title=e.get("title", ""),
                       duration=float(e.get("duration") or 0),
                       channel=e.get("channel") or e.get("uploader") or "")


async def gather_sources(urls: list[str], query: str, want: int = 4, log=print) -> list[SourceVideo]:
    """사용자가 준 URL 을 우선 쓰고, 모자라면 검색으로 채운다."""
    sources: list[SourceVideo] = []
    seen: set[str] = set()

    for u in urls:
        try:
            sv = await asyncio.to_thread(_info_sync, u)
        except Exception as e:  # noqa: BLE001
            log(f"소스 정보를 못 읽었습니다 ({u}): {e}")
            continue
        if sv and sv.url not in seen:
            seen.add(sv.url)
            sources.append(sv)
            log(f"소스 추가: {sv.title[:40]} ({sv.duration:.0f}초)")

    if len(sources) < want and query.strip():
        log(f"'{query}' 로 영상 검색 중")
        try:
            found = await asyncio.to_thread(_search_sync, query, want * 3)
        except Exception as e:  # noqa: BLE001
            log(f"검색 실패: {e}")
            found = []
        for sv in found:
            if len(sources) >= want:
                break
            if sv.url in seen:
                continue
            seen.add(sv.url)
            sources.append(sv)
            log(f"검색 결과 추가: {sv.title[:40]} ({sv.duration:.0f}초)")

    return sources[:want]


# ---------- 2. 소스 이해 ----------

async def load_timelines(sources: list[SourceVideo], workdir: Path, log=print) -> list[list[str]]:
    """소스별 자막 타임라인. 자막이 없으면 빈 목록.

    유튜브가 자막 요청에 429 를 잘 주므로 순차로 받는다.
    """
    out: list[list[str]] = []
    for i, sv in enumerate(sources):
        sub = workdir / f"src{i}"
        sub.mkdir(parents=True, exist_ok=True)
        try:
            words = await fetch_transcript(sv.url, sub)
        except Exception as e:  # noqa: BLE001
            log(f"소스 {i + 1} 자막 실패: {e}")
            words = None
        lines = words_to_lines(words) if words else []
        out.append(lines)
        log(f"소스 {i + 1}/{len(sources)} 자막 {'있음' if lines else '없음'}")
        if i < len(sources) - 1:
            await asyncio.sleep(1.5)
    return out


# ---------- 3. 장면 매칭 ----------

BROLL_SYSTEM = """당신은 뉴스 쇼츠 편집자입니다. 나레이션 대본에 맞춰 넣을 화면(B롤)을 소스 영상에서 고릅니다.

규칙:
- 각 장면의 나레이션 내용과 실제로 관련 있는 화면을 고른다. 억지로 끼워 맞추지 말 것.
- 맞는 화면이 없으면 source_index 를 -1 로 둔다. 그 장면은 이미지로 대체된다.
- 요청된 길이보다 2~3초 길게 잡는다. 편집에서 잘라 쓴다.
- 한 소스에서 쓰는 구간의 합이 상한을 넘지 않게 한다. 여러 소스에 고르게 분산한다.
- 같은 구간을 두 장면에 쓰지 않는다.
- 자막이 없는 소스는 영상 제목으로만 판단해야 하므로, 확신이 없으면 고르지 않는다.
- 영상 시작 직후 3초와 끝 3초는 인트로·아웃트로일 가능성이 높아 피한다."""


async def match_broll(llm: dict[str, Any], script: Script, durations: list[float],
                      sources: list[SourceVideo], timelines: list[list[str]],
                      max_per_source: float = 15.0) -> BrollPlan:
    scene_lines = [
        f"[장면 {i}] 필요 길이 {durations[i]:.1f}초\n  나레이션: {s.narration}\n  키워드: {s.on_screen_text}"
        for i, s in enumerate(script.scenes)
    ]
    src_blocks = []
    for i, (sv, lines) in enumerate(zip(sources, timelines)):
        body = "\n".join(lines[:80]) if lines else "(자막 없음 - 제목으로만 판단)"
        src_blocks.append(
            f"### 소스 {i}: {sv.title}\n채널: {sv.channel} / 길이: {sv.duration:.0f}초\n{body}")

    user = (
        f"[주제] {script.topic}\n"
        f"[소스당 사용 상한] {max_per_source:.0f}초\n\n"
        "## 대본 장면\n" + "\n".join(scene_lines)
        + "\n\n## 소스 영상 (초 단위 타임스탬프)\n" + "\n\n".join(src_blocks)
        + "\n\n각 장면에 넣을 화면 구간을 고르세요."
    )
    return await ask_structured(llm, BROLL_SYSTEM, user, BrollPlan)


# ---------- 4. 정규화 ----------

def normalize_picks(plan: BrollPlan, sources: list[SourceVideo], durations: list[float],
                    max_per_source: float = 15.0, log=print) -> list[BrollPick | None]:
    """장면 수만큼의 목록. 쓸 수 없는 장면은 None (이미지로 대체된다).

    - 소스 범위·시간 범위를 벗어나면 버린다
    - 소스당 누적 사용 시간 상한을 강제한다
    - 구간 길이는 렌더 단계에서 정확히 맞추므로 여기서는 시작점만 유효하게 만든다
    """
    out: list[BrollPick | None] = [None] * len(durations)
    used: dict[int, float] = {}

    for p in plan.picks:
        i = p.scene_index
        if not (0 <= i < len(durations)) or out[i] is not None:
            continue
        if not (0 <= p.source_index < len(sources)):
            continue
        sv = sources[p.source_index]
        need = durations[i]

        start = max(0.0, min(p.start, max(0.0, sv.duration - 1.0)))
        end = max(start + 0.5, p.end)
        # 소스 끝을 넘지 않게
        if sv.duration:
            end = min(end, sv.duration)
            if end - start < 0.5:
                start = max(0.0, end - need)

        if used.get(p.source_index, 0.0) + need > max_per_source:
            log(f"장면 {i + 1}: 소스 {p.source_index + 1} 사용 상한 초과 → 건너뜀")
            continue

        used[p.source_index] = used.get(p.source_index, 0.0) + need
        out[i] = BrollPick(scene_index=i, source_index=p.source_index,
                           start=round(start, 3), end=round(end, 3), reason=p.reason)

    for idx, total in used.items():
        sources[idx].used = round(total, 2)
    got = sum(1 for p in out if p)
    log(f"장면 {len(durations)}개 중 {got}개에 실제 영상 배치")
    return out


# ---------- 5. 다운로드 ----------

async def download_sources(sources: list[SourceVideo], picks: list[BrollPick | None],
                           workdir: Path, log=print) -> None:
    """실제로 쓰이는 소스만 내려받아 SourceVideo.path 를 채운다."""
    need = sorted({p.source_index for p in picks if p})
    for n, idx in enumerate(need, 1):
        sv = sources[idx]
        sub = workdir / f"src{idx}"
        sub.mkdir(parents=True, exist_ok=True)
        log(f"소스 영상 {n}/{len(need)} 내려받는 중: {sv.title[:40]}")
        try:
            sv.path = str(await download_media(sv.url, sub, audio_only=False))
        except Exception as e:  # noqa: BLE001
            log(f"다운로드 실패 - 이 소스의 장면은 이미지로 대체됩니다: {e}")
            sv.path = ""


def drop_failed(picks: list[BrollPick | None], sources: list[SourceVideo]) -> list[BrollPick | None]:
    """다운로드에 실패한 소스를 쓰는 장면은 None 으로 되돌린다."""
    return [p if (p and sources[p.source_index].path) else None for p in picks]


def source_urls(sources: list[SourceVideo], picks: list[BrollPick | None]) -> list[str]:
    """설명란에 넣을 출처 URL (실제로 쓴 소스만)."""
    used = sorted({p.source_index for p in picks if p})
    return [sources[i].url for i in used]


def credit_for(pick: BrollPick | None, sources: list[SourceVideo]) -> str:
    if not pick:
        return ""
    sv = sources[pick.source_index]
    return f"영상 출처: {sv.channel}" if sv.channel else "영상 출처: YouTube"
