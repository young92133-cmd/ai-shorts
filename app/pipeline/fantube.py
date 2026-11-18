"""팬튜브 편집 스킨 (benchmark source: lovelittt, docs/BENCHMARK_LOVELITT_2026-11-17.md).

구조·원칙만 옮긴다. 색·폰트·템플릿 파일은 우리 것이다.
- 아래가 뚫린 프레임: 위에만 작은 검정 제목바, 영상은 화면 아래 끝까지
- 제목바 2줄: 작은 강조색 윗줄 + 흰색 굵은 아랫줄, 영상 내내 고정
- 대사 자막: 얇은 각진 고딕 + 글자에 딱 맞는 검정 박스 + 좁은 자간, 가속도(ease-out) 팝 등장
- 자막 표시: 문장 앞 [화남] [억울] [강조] [스토리], 단어 강조는 *단어*
- 효과음: 장면이 바뀔 때·자막이 바뀔 때마다 (ffmpeg 로 합성, 외부 파일 없음)
"""
from __future__ import annotations

import re
from typing import Any

SKINS = ("default", "fantube")
ACCENT = "#FFC83D"          # 제목 윗줄·강조 단어
EMPHASIS = "#FFD84D"
MARKS = {"화남": "angry", "angry": "angry", "억울": "sad", "sad": "sad",
         "강조": "blur", "blur": "blur", "스토리": "story", "story": "story"}
_MARK_RE = re.compile(r"^\s*\[([^\]]{1,6})\]")
MAX_SFX = 80
SFX_GAP = 0.15
SFX_PRIORITY = {"hit": 3, "whoosh": 2, "drop": 1, "pop": 0}


def bar_height(height: int) -> int:
    return int(height * 0.15) // 2 * 2


# ---------- 자막 표시 ----------

def parse_marks(text: str) -> dict[str, Any]:
    """'[화남][강조] 진짜 *맛있어*' → tone/story/blur + 강조 구간. 모르는 [..] 는 글자로 둔다."""
    tone, story, blur = "normal", False, False
    rest = text
    while True:
        m = _MARK_RE.match(rest)
        if not m or m.group(1).strip().lower() not in MARKS:
            break
        kind = MARKS[m.group(1).strip().lower()]
        if kind in ("angry", "sad"):
            tone = kind
        elif kind == "story":
            story = True
        else:
            blur = True
        rest = rest[m.end():]
    rest = " ".join(rest.split())
    spans: list[tuple[str, bool]] = []
    for k, part in enumerate(rest.split("*")):
        if part:
            spans.append((part, k % 2 == 1))
    if rest.count("*") % 2:          # 짝이 안 맞는 * 는 강조 없이 그대로
        spans = [(rest, False)]
    return {"tone": tone, "story": story, "blur": blur, "spans": spans,
            "text": "".join(s for s, _ in spans)}


def strip_marks(text: str) -> str:
    """기본 스킨·SRT·CapCut 에는 표시 문법을 빼고 글자만."""
    return parse_marks(text)["text"]


# ---------- ASS ----------

def ass_styles(font: str, width: int, height: int, color) -> list[str]:
    k = width / 1080
    top = bar_height(height)
    s = lambda v: max(1, int(v * k))  # noqa: E731
    white, black = color("#FFFFFF"), color("#000000")
    return [
        f"Style: FTAccent,{font},{s(44)},{color(ACCENT)},{white},{black},{black},-1,0,0,0,100,100,-1,0,1,0,0,8,40,40,{int(top * 0.20)},1",
        f"Style: FTMain,{font},{s(68)},{white},{white},{black},{black},-1,0,0,0,100,100,-2,0,1,0,0,8,40,40,{int(top * 0.42)},1",
        f"Style: FTLine,{font},{s(58)},{white},{white},{color('#000000', 0x20)},{black},0,0,0,0,100,100,-1.5,0,3,{s(12)},0,2,70,70,{int(height * 0.20)},1",
        f"Style: FTAngry,{font},{s(92)},{color('#FF2D2D')},{white},{white},{color('#000000', 0x60)},-1,0,0,0,100,100,-2,0,1,{s(7)},{s(4)},5,60,60,0,1",
        f"Style: FTSad,{font},{s(80)},{color('#8EC9FF')},{white},{color('#1B2A4A')},{color('#000000', 0x60)},-1,0,0,0,100,100,-2,0,1,{s(6)},{s(3)},5,60,60,0,1",
    ]


def _wrap(spans: list[tuple[str, bool]], per_line: int, max_lines: int = 2) -> list[list[tuple[str, bool]]]:
    """강조 구간을 유지한 채 단어 단위로 줄을 나눈다."""
    words: list[tuple[str, bool]] = []
    for seg, emph in spans:
        words += [(w, emph) for w in seg.split(" ") if w]
    rows: list[list[tuple[str, bool]]] = [[]]
    n = 0
    for w, emph in words:
        if rows[-1] and n + 1 + len(w) > per_line:
            if len(rows) == max_lines:
                break
            rows.append([])
            n = 0
        rows[-1].append((w, emph))
        n += len(w) + (1 if n else 0)
    return [r for r in rows if r]


def _body(rows, esc, base: str) -> str:
    out = []
    for row in rows:
        parts, cur = [], False
        for k, (w, emph) in enumerate(row):
            tag = ""
            if emph != cur:
                tag = f"{{\\1c{EMPH_ASS if emph else base}}}"
                cur = emph
            parts.append(("" if k == 0 else " ") + tag + esc(w))
        if cur:
            parts.append(f"{{\\1c{base}}}")
        out.append("".join(parts))
    return "\\N".join(out)


EMPH_ASS = "&H004DD8FF&"   # #FFD84D in ASS BGR, alpha 0


def line_event(line: dict, width: int, height: int, ts, esc, color) -> str:
    start, end = float(line["start"]), float(line["end"])
    m = parse_marks(str(line.get("text", "")))
    if not m["spans"]:
        return ""
    dur_ms = int((end - start) * 1000)
    if m["tone"] == "angry":
        style, base = "FTAngry", color("#FF2D2D")
        rows = _wrap(m["spans"], 9)
        y = int(height * 0.55)
        tags = (f"\\an5\\pos({width // 2},{y})\\fad(30,100)\\fscx150\\fscy150\\t(0,140,0.4,\\fscx100\\fscy100)"
                "\\t(140,200,\\frz-4)\\t(200,260,\\frz3)\\t(260,320,\\frz0)")
    elif m["tone"] == "sad":
        style, base = "FTSad", color("#8EC9FF")
        rows = _wrap(m["spans"], 10)
        y = int(height * 0.55)
        tags = f"\\an5\\fad(80,120)\\move({width // 2},{y - 40},{width // 2},{y},0,260)"
    else:
        style, base = "FTLine", color("#FFFFFF")
        rows = _wrap(m["spans"], 16)
        if m["story"]:
            # 밀면서 나타나기: 미리 다 보이면 스포가 된다
            reveal = max(200, min(700, int(dur_ms * 0.35)))
            tags = f"\\fad(0,80)\\clip(0,0,0,{height})\\t(0,{reveal},\\clip(0,0,{width},{height}))"
        else:
            tags = "\\fad(40,80)\\fscx72\\fscy72\\t(0,170,0.45,\\fscx100\\fscy100)"
    return f"Dialogue: 4,{ts(start)},{ts(end)},{style},,0,0,0,,{{{tags}}}{_body(rows, esc, base)}"


def headline_events(headline: dict | None, total: float, width: int, height: int, ts, esc) -> list[str]:
    if not headline or total <= 0:
        return []
    out = []
    accent = " ".join(str(headline.get("accent", "")).split())[:30]
    main = " ".join(str(headline.get("main", "")).split())[:40]
    per = max(6, int((width - 80) / (68 * width / 1080)))
    if accent:
        out.append(f"Dialogue: 5,{ts(0)},{ts(total)},FTAccent,,0,0,0,,{esc(accent)}")
    if main:
        from .subtitles import wrap_title
        rows = wrap_title(main, per, max_lines=2)
        # 윗줄이 없으면 제목을 바 위쪽으로 올린다
        tag = "" if accent else f"{{\\an8\\pos({width // 2},{int(bar_height(height) * 0.22)})}}"
        out.append(f"Dialogue: 5,{ts(0)},{ts(total)},FTMain,,0,0,0,,{tag}" + "\\N".join(esc(r) for r in rows[:2]))
    return out


# ---------- 효과음 ----------

def sfx_events(scene_starts: list[float], lines: list[dict]) -> list[tuple[float, str]]:
    """장면 전환 = whoosh, 자막 등장 = pop, 화남 = hit, 억울 = drop. 너무 붙은 소리는 하나만 남긴다."""
    raw = [(float(t), "whoosh") for t in scene_starts if float(t) > 0.05]
    for ln in lines:
        tone = parse_marks(str(ln.get("text", "")))["tone"]
        raw.append((float(ln["start"]), {"angry": "hit", "sad": "drop"}.get(tone, "pop")))
    raw.sort()
    out: list[tuple[float, str]] = []
    for t, kind in raw:
        if out and t - out[-1][0] < SFX_GAP:
            if SFX_PRIORITY[kind] > SFX_PRIORITY[out[-1][1]]:
                out[-1] = (out[-1][0], kind)
            continue
        out.append((round(t, 3), kind))
    return out[:MAX_SFX]


_SFX_SRC = {
    "pop": ("sine=frequency=1250:sample_rate=44100:duration=0.08,afade=t=out:st=0.01:d=0.07", 0.30),
    "whoosh": ("anoisesrc=d=0.30:c=pink:r=44100:a=0.6,bandpass=f=1600:width_type=h:w=1400,"
               "afade=t=in:d=0.12,afade=t=out:st=0.12:d=0.18", 0.55),
    "hit": ("sine=frequency=95:sample_rate=44100:duration=0.22,afade=t=out:st=0.02:d=0.20", 0.85),
    "drop": ("sine=frequency=420:sample_rate=44100:duration=0.30,vibrato=f=7:d=0.4,afade=t=out:st=0.05:d=0.25", 0.35),
}


def sfx_filters(events: list[tuple[float, str]], total: float, gain: float = 1.0) -> list[str]:
    """효과음 트랙 [sfx] 를 만드는 filter_complex 조각. 외부 음원 없이 합성한다."""
    if not events or total <= 0:
        return []
    filters, labels = [], []
    for i, (t, kind) in enumerate(events):
        src, vol = _SFX_SRC[kind]
        ms = max(0, int(t * 1000))
        filters.append(f"{src},volume={vol * gain:.3f},aformat=sample_rates=44100:channel_layouts=stereo,"
                       f"adelay={ms}|{ms}[sfx{i}]")
        labels.append(f"[sfx{i}]")
    mix = (f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,"
           if len(labels) > 1 else f"{labels[0]}anull,")
    filters.append(f"{mix}apad=whole_dur={total:.3f},atrim=duration={total:.3f}[sfx]")
    return filters


# ---------- timeline 기본값 ----------

def default_headline(tl: dict[str, Any]) -> dict[str, str]:
    h = tl.get("headline") or {}
    main = h.get("main") or next((s.get("title", "") for s in tl.get("scenes", []) if s.get("title")), "")
    return {"accent": h.get("accent", ""), "main": main}
