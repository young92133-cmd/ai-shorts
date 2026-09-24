"""참고 영상 화면에서 댓글 캡처가 언제·어디에 뜨는지 찾는다 (레퍼런스 보고 댓글 자동 배치).

스타일 분석 때 사용자가 켠 경우에만 돈다. 참고 영상을 받아 일정 간격으로 화면을 뽑고,
화면 분석(Gemini 또는 GPT 비전)으로 "댓글 캡처·댓글 카드가 떠 있는가 / 위·가운데·아래 중 어디인가"를 판별한다.
결과는 영상 길이 대비 비율(at_ratio)로 저장해 길이가 다른 새 영상에도 같은 흐름으로 배치한다.

비용: 영상당 최대 MAX_FRAMES 장의 화면 분석 요청이 나간다 (키가 없으면 실행하지 않는다).
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .media import probe_duration, run_ffmpeg
from .vision import describe_all, vision_available
from .youtube import download_media

MAX_FRAMES = 24
FRAME_EVERY = 2.5        # 초
POS_Y = {"top": 0.25, "middle": 0.42, "bottom": 0.6}
MAX_SLOTS = 3

COMMENT_PROMPT = (
    "이 세로 영상 화면에 유튜브·커뮤니티 댓글을 캡처한 이미지나 댓글 카드(프로필 사진, 작성자, 좋아요 수, "
    "댓글 말풍선 등)가 영상 위에 겹쳐 보이는지 판단하세요. 일반 자막이나 제목 글자는 댓글이 아닙니다. "
    "description 에는 화면에 보이는 것을 한 문장으로 쓰세요. 댓글이 보이면 keywords 에 'comment' 와 "
    "그 위치('top', 'middle', 'bottom' 중 하나)를 넣고, 보이지 않으면 keywords 를 빈 목록으로 두세요.\n"
    '반드시 JSON 만 출력: {"description": "...", "keywords": []}'
)


def frame_times(duration: float, count: int) -> list[float]:
    """영상 전체를 고르게 덮는 시점 (각 구간의 가운데)."""
    return [duration * (k + 0.5) / count for k in range(count)]


def slots_from_hits(hits: list[str | None], duration: float) -> list[dict[str, Any]]:
    """프레임별 판별 결과(None 또는 위치) → 연속 구간별 슬롯 {at_ratio, seconds, y}."""
    if not hits or duration <= 0:
        return []
    step = duration / len(hits)
    slots: list[dict[str, Any]] = []
    k = 0
    while k < len(hits):
        if hits[k] is None:
            k += 1
            continue
        start = k
        while k < len(hits) and hits[k] is not None:
            k += 1
        pos = Counter(h for h in hits[start:k]).most_common(1)[0][0]
        slots.append({"at_ratio": round(start * step / duration, 3),
                      "seconds": round(max(2.0, min(6.0, (k - start) * step)), 1),
                      "y": POS_Y.get(pos, POS_Y["middle"])})
    return slots


def merge_slots(per_video: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """여러 참고 영상의 슬롯을 하나의 배치 규칙으로. 댓글을 쓴 영상들의 평균 개수만큼, 순서별로 평균낸다."""
    used = [s for s in per_video if s]
    if not used:
        return []
    n = min(MAX_SLOTS, max(1, round(sum(len(s) for s in used) / len(used))))
    out = []
    for k in range(n):
        group = [s[k] for s in used if len(s) > k]
        if not group:
            break
        out.append({"at_ratio": round(sum(g["at_ratio"] for g in group) / len(group), 3),
                    "seconds": round(sum(g["seconds"] for g in group) / len(group), 1),
                    "y": Counter(g["y"] for g in group).most_common(1)[0][0]})
    return sorted(out, key=lambda s: s["at_ratio"])


def describe_pattern(slots: list[dict[str, Any]], n_with: int, n_total: int) -> str:
    if not slots:
        return f"참고 영상 {n_total}개에서 댓글 캡처를 찾지 못했습니다."
    where = {v: k for k, v in {"위": POS_Y["top"], "가운데": POS_Y["middle"], "아래": POS_Y["bottom"]}.items()}
    spots = ", ".join(f"{s['at_ratio'] * 100:.0f}% 지점 {s['seconds']:.0f}초 ({where.get(s['y'], '가운데')})"
                      for s in slots)
    return f"참고 영상 {n_total}개 중 {n_with}개에서 댓글 캡처 사용 · 댓글 {len(slots)}개: {spots}"


def pick_provider(llm_provider: str) -> str | None:
    """GPT 로 분석 중이면 OpenAI 비전, 아니면 Gemini. 키가 없으면 None."""
    if llm_provider == "openai" and vision_available("openai"):
        return "openai"
    if vision_available("gemini"):
        return "gemini"
    if vision_available("openai"):
        return "openai"
    return None


async def _sample_frames(video: Path, out_dir: Path) -> tuple[list[Path], float]:
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = await probe_duration(video)
    count = max(4, min(MAX_FRAMES, int(duration / FRAME_EVERY)))
    frames = []
    for k, t in enumerate(frame_times(duration, count)):
        p = out_dir / f"f{k:02d}.jpg"
        try:
            await run_ffmpeg(["-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                              "-vf", "scale=480:-2", "-q:v", "5", str(p)])
        except RuntimeError:
            pass
        frames.append(p)   # 실패한 칸도 자리를 지켜야 시간이 어긋나지 않는다
    return frames, duration


async def analyze_comment_layout(urls: list[str], workdir: Path, llm_provider: str = "",
                                 log=print) -> dict[str, Any]:
    """반환: {"comment_slots": [...], "comment_pattern": "...", "findings": [...]}"""
    provider = pick_provider(llm_provider)
    if not provider:
        raise RuntimeError("댓글 배치 분석에는 화면 분석 키(Gemini 또는 OpenAI)가 필요합니다. ⚙ 설정에서 등록하세요.")
    per_video: list[list[dict[str, Any]]] = []
    findings: list[str] = []
    for i, url in enumerate(urls, 1):
        sub = workdir / f"ref{i}" / "layout"
        log(f"댓글 배치 분석: 참고 영상 {i}/{len(urls)} 내려받는 중")
        video = await download_media(url, sub, audio_only=False)
        frames, duration = await _sample_frames(video, sub / "frames")
        log(f"댓글 배치 분석: 화면 {len(frames)}장 확인 중 ({provider})")
        ok = [f for f in frames if f.is_file()]
        found = dict(zip(ok, await describe_all(ok, provider=provider, prompt=COMMENT_PROMPT, log=log)))
        descs = [found.get(f) for f in frames]
        hits: list[str | None] = []
        for d in descs:
            kw = [k.lower() for k in (d.keywords if d else [])]
            hits.append(next((p for p in POS_Y if p in kw), "middle") if "comment" in kw else None)
        slots = slots_from_hits(hits, duration)
        per_video.append(slots)
        findings.append(f"참고 영상 {i}: 화면 {len(frames)}장 중 {sum(h is not None for h in hits)}장에서 댓글 캡처 확인"
                        + (f" → {len(slots)}번 등장" if slots else ""))
        video.unlink(missing_ok=True)   # 분석이 끝난 원본은 지운다
    merged = merge_slots(per_video)
    return {"comment_slots": merged,
            "comment_pattern": describe_pattern(merged, sum(1 for s in per_video if s), len(urls)),
            "findings": findings}


def clean_slots(raw: Any) -> list[dict[str, Any]]:
    """저장·API 입력용 검증: 비율·길이·위치를 범위 안으로 자른다."""
    out = []
    for s in raw if isinstance(raw, list) else []:
        try:
            out.append({"at_ratio": round(min(0.95, max(0.0, float(s["at_ratio"]))), 3),
                        "seconds": round(min(8.0, max(1.0, float(s.get("seconds", 3.5)))), 1),
                        "y": round(min(0.9, max(0.1, float(s.get("y", POS_Y["middle"])))), 3)})
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out, key=lambda s: s["at_ratio"])[:MAX_SLOTS]


def place(slots: list[dict[str, Any]], index: int, total: float) -> tuple[float, float, float] | None:
    """index 번째 댓글을 놓을 (시작, 끝, y). 슬롯이 모자라면 None."""
    if index >= len(slots) or total <= 0:
        return None
    s = slots[index]
    start = min(max(0.0, s["at_ratio"] * total), max(0.0, total - 1.0))
    return round(start, 3), round(min(total, start + s["seconds"]), 3), s["y"]
