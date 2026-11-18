"""팬 클립(팬튜브) 렌더 — 원본 영상만으로 만드는 9:16 쇼츠.

벤치마크(돌토리 @doltori, 2026-11-18 다시 확인)의 화면 구조를 우리 디자인으로 만든다:
- 위쪽 띠: 2줄 제목(흰 줄 + 강조색 줄)이 영상 내내 고정
- 가운데: 처음부터 끝까지 원본 영상(정지 화면·카드·정리 화면 없음), 원본 소리
- 영상 위: 작은 검정 박스 자막(담백한 관찰 문장)
- 아래쪽 띠: '출처 - 채널 · 제목' (출처 표기는 빠지면 렌더하지 않는다)
글꼴은 Pretendard(assets/fonts, OFL). 벤치마크의 로고·그리드·색은 따라 하지 않는다.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

W, H = 1080, 1920
TOP = 470                 # 제목 띠 높이
VIDEO_H = 1250            # 영상 영역 높이 (TOP ~ TOP+VIDEO_H)
BG = (14, 14, 16)
ACCENT = (255, 111, 181)  # 우리 강조색(분홍)
CAPTION_Y = TOP + int(VIDEO_H * 0.80)
FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
MIN_SEG, MAX_SEG = 1.5, 10.0
_TIMECODE = re.compile(r"\d{1,2}:\d{2}(?:\s*~\s*\d{1,2}:\d{2})?\s*")
_SLANG = re.compile(r"(ㅋ{2,}|ㄷ{2,}|ㅠ{2,}|ㅜ{2,}|!{2,}|\?{2,})")


class FanSegment(BaseModel):
    start: float = Field(description="원본 영상에서 시작 시각(초)")
    end: float = Field(description="원본 영상에서 끝 시각(초)")
    caption: str = Field(default="", description="이 구간에 띄울 짧은 자막(20자 안팎). 없으면 빈 문자열")
    why: str = Field(default="", description="이 구간을 고른 이유(관찰 근거, 화면에는 안 나옴)")


class FanClipPlan(BaseModel):
    title_top: str = Field(description="제목 첫 줄(흰 글씨, 14자 안팎): 맥락")
    title_accent: str = Field(description="제목 둘째 줄(강조색, 14자 안팎): 핵심 포인트")
    segments: list[FanSegment] = Field(description="원본에서 고른 구간들, 보여 줄 순서대로 3~8개")
    upload_title: str = Field(description="업로드 제목(40자 이하)")
    description: str = Field(description="업로드 설명 2~3문장(숫자 시각은 0:56 처럼 표기)")
    hashtags: list[str] = Field(default_factory=list, description="해시태그 5~8개(# 포함)")


SYSTEM = """너는 K팝 팬 클립(팬튜브) 쇼츠 편집자다. 원본 영상 한 편에서 구간을 골라 이어 붙이고, 위 제목과 짧은 자막만 단다.
구조(벤치마크): 볼 이유가 첫 장면부터 보이게 → 그 이유를 보여 주는 장면 근거 → 짧은 해설 → (선택) 가벼운 질문.
규칙:
- 첫 구간부터 바로 핵심 장면. 인트로·정리 화면 없음. 나레이션 없음(원본 소리 사용).
- 제목은 2줄: 첫 줄은 맥락(예: '인기가요 엔딩에서 보인'), 둘째 줄은 핵심(예: '베스티 회색 의상 디테일'). 낚시·과장 금지.
- 자막은 담백하고 자연스럽게. 해요체나 짧은 관찰 문장. 감탄사·'ㄷㄷ'·'ㅋㅋ'·이모지·느낌표 남발 금지. 모든 구간에 자막을 달 필요는 없다. 자막에 '0:20' 같은 시각을 넣지 않는다.
- 확인된 정보(영상 정보·사용자 관찰)만 쓴다. 얼굴만 보고 멤버 이름을 추측하지 않는다(확인 안 되면 '멤버').
- 다른 방송의 조회수·순위 같은 수치는 쓰지 않는다.
- 구간은 원본 길이 안에서, 한 구간 2~8초, 가능하면 샷 경계에서 시작. 겹치지 않게. 같은 장면 반복 금지.
- 전체 길이는 목표 길이에 맞춘다."""


def build_prompt(info: dict[str, Any], seconds: int, shots: list[float], transcript: list[str], instructions: str) -> str:
    shot_txt = ", ".join(f"{t:.1f}" for t in shots[:160]) or "(없음)"
    lines = [f"영상 제목: {info.get('title', '')}", f"채널: {info.get('channel', '')}",
             f"원본 길이: {float(info.get('duration') or 0):.0f}초", f"목표 길이: {seconds}초",
             f"설명란(앞부분): {(info.get('description') or '')[:400]}", f"샷 경계(초): {shot_txt}"]
    if transcript:
        lines.append("자막(타임스탬프):\n" + "\n".join(transcript[:80]))
    if instructions:
        lines.append(f"사용자 지시·관찰:\n{instructions}")
    return "\n".join(lines)


def _clean(text: str, limit: int) -> str:
    text = _SLANG.sub("", _TIMECODE.sub("", " ".join((text or "").split()))).strip()
    return text[:limit]


def normalize(plan: FanClipPlan, duration: float, seconds: int) -> FanClipPlan:
    """구간을 원본 길이 안으로 자르고, 겹침·너무 짧은 구간을 빼고, 목표 길이에 맞춘다."""
    segs: list[FanSegment] = []
    taken: list[tuple[float, float]] = []
    total = 0.0
    limit = seconds + 3.0
    for s in plan.segments:
        a = max(0.0, float(s.start))
        b = min(float(s.end), duration - 0.05, a + MAX_SEG)
        if any(a < y and x < b for x, y in taken):
            continue
        b = min(b, a + (limit - total))
        if b - a < MIN_SEG:
            continue
        segs.append(FanSegment(start=round(a, 2), end=round(b, 2), caption=_clean(s.caption, 28), why=s.why))
        taken.append((a, b))
        total += b - a
        if total >= limit - MIN_SEG:
            break
    if total < 6.0:
        raise ValueError("팬 클립으로 쓸 구간이 너무 짧습니다(6초 미만).")
    return plan.model_copy(update={"segments": segs, "title_top": _clean(plan.title_top, 20),
                                   "title_accent": _clean(plan.title_accent, 20)})


# ---------- 그림 (Pillow) ----------

def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / f"Pretendard-{weight}.otf"
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        from .fonts import font
        return font(size)


def _fit(draw: ImageDraw.ImageDraw, text: str, weight: str, size: int, max_w: int) -> ImageFont.FreeTypeFont:
    while size > 28:
        f = _font(weight, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return _font(weight, size)


def frame_overlay(title_top: str, title_accent: str, credit: str, out: Path) -> Path:
    """위 제목 띠 + 아래 출처 띠. 가운데(영상 영역)는 투명."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, TOP], fill=(*BG, 255))
    d.rectangle([0, TOP + VIDEO_H, W, H], fill=(*BG, 255))
    f1 = _fit(d, title_top, "Bold", 70, W - 100)
    f2 = _fit(d, title_accent, "ExtraBold", 92, W - 80)
    d.text((W / 2, TOP * 0.42), title_top, font=f1, fill=(255, 255, 255), anchor="mm")
    d.text((W / 2, TOP * 0.70), title_accent, font=f2, fill=ACCENT, anchor="mm")
    fc = _fit(d, credit, "SemiBold", 34, W - 120)
    d.text((W / 2, TOP + VIDEO_H + (H - TOP - VIDEO_H) * 0.42), credit, font=fc, fill=(205, 205, 210), anchor="mm")
    img.save(out)
    return out


def caption_overlay(text: str, out: Path) -> Path:
    """영상 위 작은 검정 박스 자막 (전체 화면 크기 투명 PNG)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = _fit(d, text, "SemiBold", 50, W - 160)
    l, t, r, b = d.textbbox((W / 2, CAPTION_Y), text, font=f, anchor="mm")
    d.rounded_rectangle([l - 26, t - 16, r + 26, b + 16], radius=12, fill=(0, 0, 0, 190))
    d.text((W / 2, CAPTION_Y), text, font=f, fill=(255, 255, 255), anchor="mm")
    img.save(out)
    return out


# ---------- 렌더 (ffmpeg) ----------

def has_audio(path: Path) -> bool:
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return bool(p.stdout.strip())


def build_command(src: Path, plan: FanClipPlan, frame_png: Path, captions: list[tuple[Path, float, float]],
                  out: Path, audio: bool = True) -> list[str]:
    segs = plan.segments
    total = sum(s.end - s.start for s in segs)
    parts: list[str] = []
    for i, s in enumerate(segs):
        dur = s.end - s.start
        parts.append(f"[0:v]trim=start={s.start:.3f}:end={s.end:.3f},setpts=PTS-STARTPTS,"
                     f"scale={W}:{VIDEO_H}:force_original_aspect_ratio=increase,crop={W}:{VIDEO_H},setsar=1,fps=30[v{i}]")
        if audio:
            parts.append(f"[0:a]atrim=start={s.start:.3f}:end={s.end:.3f},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:d=0.04,afade=t=out:st={max(0.0, dur - 0.06):.3f}:d=0.06[a{i}]")
    n = len(segs)
    if audio:
        parts.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac0]")
        parts.append(f"[ac0]afade=t=out:st={max(0.0, total - 0.4):.3f}:d=0.4[ac]")
    else:
        parts.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
    parts.append(f"[vc]pad={W}:{H}:0:{TOP}:color=0x{BG[0]:02x}{BG[1]:02x}{BG[2]:02x}[bg]")
    parts.append("[bg][1:v]overlay=0:0[o0]")
    last = "o0"
    for k, (_, a, b) in enumerate(captions):
        parts.append(f"[{last}][{k + 2}:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[o{k + 1}]")
        last = f"o{k + 1}"
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-loop", "1", "-i", str(frame_png)]
    for p, _, _ in captions:
        cmd += ["-loop", "1", "-i", str(p)]
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{last}]"]
    cmd += ["-map", "[ac]", "-c:a", "aac", "-b:a", "160k"] if audio else []
    cmd += ["-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-r", "30", "-movflags", "+faststart", str(out)]
    return cmd


def render(src: Path, plan: FanClipPlan, credit: str, work: Path, out: Path) -> dict[str, Any]:
    if not credit.strip():
        raise ValueError("출처 표기가 없어 팬 클립을 만들지 않습니다.")
    work.mkdir(parents=True, exist_ok=True)
    frame = frame_overlay(plan.title_top, plan.title_accent, credit, work / "frame.png")
    caps: list[tuple[Path, float, float]] = []
    t = 0.0
    for i, s in enumerate(plan.segments):
        dur = s.end - s.start
        if s.caption:
            caps.append((caption_overlay(s.caption, work / f"caption_{i:02d}.png"), t + 0.15, t + dur - 0.1))
        t += dur
    audio = has_audio(src)
    cmd = build_command(src, plan, frame, caps, out, audio=audio)
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0 or not out.exists():
        raise RuntimeError(f"팬 클립 렌더 실패: {p.stderr[-800:]}")
    return {"duration": round(t, 2), "segments": len(plan.segments), "captions": len(caps), "audio": audio}
