"""단어 타임스탬프 → ASS 자막 (현재 단어 색상 하이라이트 카라오케)."""
from __future__ import annotations

from pathlib import Path

from .models import Word


def _ass_color(hex_rgb: str, alpha: int = 0) -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ts(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def group_lines(words: list[Word], max_chars: int = 14, max_words: int = 4, max_gap: float = 0.8) -> list[list[Word]]:
    lines: list[list[Word]] = []
    cur: list[Word] = []
    cur_chars = 0
    for w in words:
        new_line = False
        if cur:
            if cur_chars + len(w.text) + 1 > max_chars or len(cur) >= max_words:
                new_line = True
            elif w.start - cur[-1].end > max_gap:
                new_line = True
        if new_line:
            lines.append(cur)
            cur, cur_chars = [], 0
        cur.append(w)
        cur_chars += len(w.text) + 1
    if cur:
        lines.append(cur)
    return lines


def build_ass(
    words: list[Word] | list[list[Word]],
    out_path: Path,
    width: int,
    height: int,
    font: str = "Malgun Gothic",
    size: int = 64,
    highlight: str = "#FFD400",
    outline: str = "#000000",
    margin_v: int | None = None,
    titles: list[tuple[float, float, str]] | None = None,
    credits: list[tuple[float, float, str]] | None = None,
    comments: list[tuple[float, float, str]] | None = None,
    lines: list[dict] | None = None,
) -> Path:
    """words 로 카라오케 자막을, titles=[(start,end,text)] 로 상단 키워드 카드를 만든다.

    words 를 장면별 리스트의 리스트로 주면 자막 줄이 장면 경계를 넘지 않는다.
    lines 를 주면 words 대신 이미 묶어 둔(사용자가 고친) 자막 줄을 그대로 쓴다. 빈 목록이면 하단 자막 없음.
    """
    margin_v = margin_v or int(height * 0.30)
    title_size = int(size * 1.15)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{font},{size},{_ass_color(highlight)},{_ass_color('#FFFFFF')},{_ass_color(outline)},{_ass_color('#000000', 128)},-1,0,0,0,100,100,0,0,1,5,2,2,60,60,{margin_v},1
Style: Title,{font},{title_size},{_ass_color('#FFFFFF')},{_ass_color('#FFFFFF')},{_ass_color(outline)},{_ass_color('#000000', 96)},-1,0,0,0,100,100,0,0,1,6,3,8,60,60,{int(height * 0.14)},1
Style: Credit,{font},{int(size * 0.42)},{_ass_color('#DDDDDD', 40)},{_ass_color('#FFFFFF')},{_ass_color(outline, 60)},{_ass_color('#000000', 160)},0,0,0,0,100,100,0,0,1,2,1,2,40,40,{int(height * 0.035)},1
Style: Comment,{font},{int(size * 0.55)},{_ass_color('#FFFFFF')},{_ass_color('#FFFFFF')},{_ass_color('#12151D')},{_ass_color('#202634')},0,0,0,0,100,100,0,0,3,16,0,8,90,90,{int(height * 0.38)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []

    for t_start, t_end, text in titles or []:
        if text.strip():
            events.append(
                f"Dialogue: 0,{_ts(t_start)},{_ts(t_end)},Title,,0,0,0,,{{\\fad(200,200)}}{_esc(text.strip())}"
            )

    # 출처 크레딧 - 화면 하단에 작고 흐리게
    for t_start, t_end, text in credits or []:
        if text.strip() and t_end > t_start:
            events.append(
                f"Dialogue: 0,{_ts(t_start)},{_ts(t_end)},Credit,,0,0,0,,{{\\fad(300,300)}}{_esc(text.strip())}"
            )

    # A recreated text card, not a screenshot; source URLs are saved in meta.txt.
    for t_start, t_end, text in comments or []:
        clean = " ".join(text.split())[:108]
        if clean and t_end > t_start:
            # Keep the card narrow enough for a vertical video.
            rows = [clean[i:i + 18] for i in range(0, len(clean), 18)][:6]
            events.append(
                f"Dialogue: 2,{_ts(t_start)},{_ts(t_end)},Comment,,0,0,0,,"
                f"{{\\fad(180,180)}}💬 유튜브 댓글\\N{_esc(' '.join(rows[:1]))}"
                + "".join(f"\\N{_esc(row)}" for row in rows[1:])
            )

    if lines is None:
        lines = words_to_lines(words)
    for line in lines:
        events.append(_karaoke_event(line))

    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
    return out_path


def words_to_lines(words: list[Word] | list[list[Word]]) -> list[dict]:
    """단어 타임스탬프를 화면 자막 줄로 묶는다. 장면별 리스트면 줄이 장면 경계를 넘지 않는다.

    줄 = {"start", "end", "text", "words": [{"text","start","end"}]} (timeline.json 과 같은 모양)
    """
    groups: list[list[Word]] = words if words and isinstance(words[0], list) else [words]  # type: ignore[list-item]
    grouped: list[list[Word]] = []
    for g in groups:
        grouped.extend(group_lines(g))
    out: list[dict] = []
    for i, line in enumerate(grouped):
        start = line[0].start
        end = line[-1].end + 0.15
        if i + 1 < len(grouped):
            end = min(end, grouped[i + 1][0].start)
        out.append({"start": round(start, 3), "end": round(max(end, start + 0.1), 3),
                    "text": " ".join(w.text for w in line),
                    "words": [{"text": w.text, "start": w.start, "end": w.end} for w in line]})
    return out


def _karaoke_event(line: dict) -> str:
    start, end = float(line["start"]), float(line["end"])
    words = line.get("words") or [{"text": line["text"], "start": start, "end": end}]
    parts: list[str] = []
    t = start
    for w in words:
        gap_cs = max(0, round((float(w["start"]) - t) * 100))
        if gap_cs:
            parts.append(f"{{\\k{gap_cs}}}")
        dur_cs = max(1, round((float(w["end"]) - float(w["start"])) * 100))
        parts.append(f"{{\\k{dur_cs}}}{_esc(w['text'])} ")
        t = float(w["end"])
    return f"Dialogue: 1,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{''.join(parts).rstrip()}"


def _srt_ts(sec: float) -> str:
    ms = max(0, round(sec * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(lines: list[dict], out_path: Path) -> Path:
    """자막 줄을 SRT 로. CapCut·프리미어 등에서 '자막 가져오기'로 쓸 수 있다."""
    blocks = [f"{i}\n{_srt_ts(float(ln['start']))} --> {_srt_ts(float(ln['end']))}\n{ln['text'].strip()}\n"
              for i, ln in enumerate((ln for ln in lines if ln.get("text", "").strip()), 1)]
    out_path.write_text("\n".join(blocks), encoding="utf-8")
    return out_path
