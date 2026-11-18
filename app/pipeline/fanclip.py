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
VOICE_Y = TOP + int(VIDEO_H * 0.30)      # 괄호 속마음 대사 위치(영상 위쪽)
FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
MIN_SEG, MAX_SEG = 1.5, 10.0
MAX_LAUGH = 2                            # 영상 전체 'ㅋㅋ' 횟수 (벤치마크: 가볍게 1~2번)
_TIMECODE = re.compile(r"\d{1,2}:\d{2}(?:\s*~\s*\d{1,2}:\d{2})?\s*")
_TONE = ((re.compile(r"ㅋ{2,}"), "ㅋㅋ"), (re.compile(r"ㄷ{2,}"), ""), (re.compile(r"[ㅠㅜ]{2,}"), "ㅠㅠ"),
         (re.compile(r"!{2,}"), "!"), (re.compile(r"\?{2,}"), "?"), (re.compile(r"\.{3,}"), ".."))


class FanSegment(BaseModel):
    start: float = Field(description="원본 영상에서 시작 시각(초)")
    end: float = Field(description="원본 영상에서 끝 시각(초)")
    caption: str = Field(default="", description="이 구간에 띄울 이야기 자막(8~20자, 반말·음슴체)")
    voice: str = Field(default="", description="선택: 인물 속마음 괄호 대사 예 '(이거 맞나?)'. 대부분 빈 문자열")
    why: str = Field(default="", description="이 구간을 고른 이유(관찰 근거, 화면에는 안 나옴)")


class FanClipPlan(BaseModel):
    title_top: str = Field(description="제목 첫 줄(흰 글씨, 14자 안팎): 맥락")
    title_accent: str = Field(description="제목 둘째 줄(강조색, 14자 안팎): 핵심 포인트")
    segments: list[FanSegment] = Field(description="원본에서 고른 구간들, 보여 줄 순서대로 3~8개")
    upload_title: str = Field(description="업로드 제목(40자 이하)")
    description: str = Field(description="업로드 설명 2~3문장(숫자 시각은 0:56 처럼 표기)")
    hashtags: list[str] = Field(default_factory=list, description="해시태그 5~8개(# 포함)")


SYSTEM = """너는 구독자 대비 조회수가 높은 팬튜브·연예 이슈 쇼츠의 자막 작가 겸 편집자다.
원본은 K팝 무대뿐 아니라 예능·인터뷰·라이브 방송·시상식·공항·뉴스·이슈 영상 등 무엇이든 될 수 있다.
원본 영상 한 편에서 구간을 골라 이어 붙이고, 위 2줄 제목과 영상 위 자막만 단다(나레이션 없음, 원본 소리).
벤치마크(2026-11-18 분석: 연예소식뉴스·아이돌탐정·디테일·잠깐만아이돌 + find-shorts 인기 쇼츠)의 공통 대본 구조를 따른다. 문장은 새로 쓴다.
말소리가 있는 원본(인터뷰·예능·이슈)은 자막(타임스탬프)의 실제 발언을 근거로 구간을 고르고, 핵심 발언 구간은 말이 끊기지 않게 자른다.
자막에 발언을 옮길 때는 짧게 요약하고 발언하지 않은 말을 지어내지 않는다.

[이야기 구조] 자막은 라벨이 아니라 한 편의 짧은 이야기다.
1) 상황: 누가 어디서 무엇을 하고 있는지 (첫 구간부터 바로 핵심 장면)
2) 궁금증: 눈에 띄는 행동·차이 ("~하는데", "그런데 ~만 다름")
3) 반전·이유: "알고 보니 ~", "근데 이게 ~때문이었음", "자세히 보면 ~"
4) 마무리 한줄평: 가벼운 해석이나 감탄 ("괜히 ~가 아님", "~인가 봄", "이 정도면 ~") — 질문 카드·정리 화면 없음

[자막 쓰는 법]
- 모든 구간에 자막을 단다. 한 자막 8~20자(최대 30자), 2~4초마다 바뀐다. 긴 말은 다음 구간 자막으로 넘긴다.
- 마지막 구간 자막은 반드시 4) 한줄평으로 완결된 문장으로 끝낸다(말이 끊긴 채 끝나지 않게).
- 한 문장을 두세 자막으로 나눠 이어 말해도 좋다 (앞 자막 "~하는데" → 다음 자막 "근데 ~").
- 말투: 친구에게 말하듯 자연스러운 반말·음슴체(~임, ~였음, ~하는데, ~인가 봄). 'ㅋㅋ'는 영상 전체에서 1~2번까지, 'ㄷㄷ'·이모지·느낌표 남발 금지.
- 금지: '보라 배경', '회색 대열'처럼 명사만 나열한 라벨 자막, 설명서 같은 딱딱한 문장, 시각 표기('0:20'), 과장·낚시.
- voice(선택): 화면 속 인물의 속마음·한마디를 괄호로 짧게 ("(이거 맞나?)", "(나만 다르게 입음)"). 영상 전체에서 0~2번만.

[제목] 2줄. 첫 줄 = 상황(흰 글씨), 둘째 줄 = 결과·포인트(강조색). 각 14자 안팎.
예시 형식: '[무대/상황]에서 [인물]이' / '[한 행동·드러난 디테일]', '[A]인데' / '[B]인 이유'.

[사실]
- 확인된 정보(영상 정보·사용자 관찰)만 쓴다. 얼굴만 보고 멤버 이름을 추측하지 않는다(사용자가 준 이름만, 없으면 '멤버'·'한 명').
- 다른 방송의 조회수·순위 같은 수치는 쓰지 않는다.

[구간] 원본 길이 안에서 한 구간 2~5초, 가능하면 샷 경계에서 시작. 겹치지 않게, 같은 장면 반복 금지. 전체 길이는 목표 길이에 맞춘다."""


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
    """시각 표기를 빼고 과한 말투를 줄인다(ㅋㅋㅋㅋ→ㅋㅋ, ㄷㄷ 제거, !!→!)."""
    text = _TIMECODE.sub("", " ".join((text or "").split()))
    for pat, rep in _TONE:
        text = pat.sub(rep, text)
    return " ".join(text.split())[:limit]


def _limit_laughs(segs: list[FanSegment]) -> None:
    """영상 전체에서 'ㅋㅋ'는 MAX_LAUGH 번까지만 남긴다."""
    seen = 0
    for s in segs:
        for field in ("caption", "voice"):
            text = getattr(s, field)
            if "ㅋㅋ" in text:
                seen += 1
                if seen > MAX_LAUGH:
                    setattr(s, field, " ".join(text.replace("ㅋㅋ", "").split()))


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
        voice = _clean(s.voice, 16)
        if voice and not voice.startswith("("):
            voice = f"({voice})"
        segs.append(FanSegment(start=round(a, 2), end=round(b, 2), caption=_clean(s.caption, 44), voice=voice, why=s.why))
        taken.append((a, b))
        total += b - a
        if total >= limit - MIN_SEG:
            break
    if total < 6.0:
        raise ValueError("팬 클립으로 쓸 구간이 너무 짧습니다(6초 미만).")
    _limit_laughs(segs)
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


def split_title(title: str) -> tuple[str, str]:
    """제목 한 줄을 위 2줄(맥락 / 강조)로 나눈다. 띄어쓰기 기준, 둘째 줄이 같거나 조금 짧게."""
    words = " ".join(str(title or "").split()).split(" ")
    if len(words) < 2:
        return "", words[0] if words else ""
    total = sum(len(w) for w in words)
    best = min(range(1, len(words)),
               key=lambda k: (abs(sum(len(w) for w in words[:k]) - total / 2), -k))
    return " ".join(words[:best]), " ".join(words[best:])


def title_band(title_top: str, title_accent: str, out: Path, *, width: int = W, height: int = 330,
               accent: tuple[int, int, int] = (255, 212, 0)) -> Path:
    """쇼츠 위쪽에 영상 내내 고정하는 2줄 제목 띠(검은 바탕, 흰 줄 + 강조색 줄)."""
    img = Image.new("RGBA", (width, height), (*BG, 255))
    d = ImageDraw.Draw(img)
    f1 = _fit(d, title_top, "ExtraBold", 80, width - 90)
    f2 = _fit(d, title_accent, "ExtraBold", 92, width - 70)
    for text, font, y, fill in ((title_top, f1, 0.36, (255, 255, 255)), (title_accent, f2, 0.70, accent)):
        if text:
            d.text((width / 2, height * y), text, font=font, fill=fill, anchor="mm",
                   stroke_width=3, stroke_fill=(0, 0, 0))
    img.save(out)
    return out


def caption_overlay(text: str, out: Path, voice: str = "") -> Path:
    """영상 위 작은 검정 박스 자막 + (선택) 괄호 속마음 대사 (전체 화면 크기 투명 PNG)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if text:
        f = _font("SemiBold", 50)
        lines = [text]
        if d.textlength(text, font=f) > W - 160:   # 길면 단어 경계에서 길이가 비슷한 두 줄로 (자르지 않는다)
            words = text.split()
            if len(words) > 1:
                k = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
                lines = [" ".join(words[:k]), " ".join(words[k:])]
            longest = max(lines, key=lambda x: d.textlength(x, font=f))
            f = _fit(d, longest, "SemiBold", 50, W - 160)
        body = "\n".join(lines)
        l, t, r, b = d.multiline_textbbox((W / 2, CAPTION_Y), body, font=f, anchor="mm", align="center", spacing=10)
        d.rounded_rectangle([l - 26, t - 16, r + 26, b + 16], radius=12, fill=(0, 0, 0, 190))
        d.multiline_text((W / 2, CAPTION_Y), body, font=f, fill=(255, 255, 255), anchor="mm", align="center", spacing=10)
    if voice:
        fv = _fit(d, voice, "Bold", 56, W - 200)
        d.text((W / 2, VOICE_Y), voice, font=fv, fill=(255, 255, 255), anchor="mm", stroke_width=6, stroke_fill=(0, 0, 0))
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
        if s.caption or s.voice:
            caps.append((caption_overlay(s.caption, work / f"caption_{i:02d}.png", voice=s.voice), t + 0.1, t + dur - 0.05))
        t += dur
    audio = has_audio(src)
    cmd = build_command(src, plan, frame, caps, out, audio=audio)
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0 or not out.exists():
        raise RuntimeError(f"팬 클립 렌더 실패: {p.stderr[-800:]}")
    return {"duration": round(t, 2), "segments": len(plan.segments), "captions": len(caps), "audio": audio}
