"""사진 편집형 이슈 쇼츠 (benchmark source: backsoo, docs/BENCHMARK_BACKSOO_2026-11-18.md).

영상 소스 없이 사진 + 빠른 나레이션 + 자막만으로 만든다. 구조·원칙만 옮기고 색·폰트·문장은 우리 것이다.

흐름:
  1) 채팅의 Claude 가 presets/issue_photo.md 지침으로 조사·사실 확인·대본을 써서 issue_plan.json 저장
     - 대본 한 줄 = 자막 한 줄 = 사진 한 장(같은 사진을 이어 써도 된다)
     - 사진은 두 종류: ai(Google Flow Nano Banana 로 만든 실사풍 재연 사진) / real(유튜브 프레임·뉴스 사진·화면 캡처)
  2) 브라우저 단계(.claude/skills/issue-shorts)가 Flow 에서 AI 사진을 만들고, 실제 사진을 캡처한다
  3) add_photo 가 사진을 photos/<ID>.<ext> 자리에 넣고 출처를 photo_sources.json 에 남긴다
  4) assemble 이 줄마다 Edge TTS → 위 검정 제목 · 가운데 사진 띠 · 아래 검정 레이아웃으로 final.mp4

화면 (1080x1920 기준): 0~27% 검정 + 2줄 고정 제목(흰/노랑), 27~73% 사진 띠(천천히 확대, 비율이 안 맞으면 흐린 채움),
띠 위쪽 반응 태그, 띠 아래쪽 줄별 색 박스 자막, 실제 사진은 띠 바로 아래 작은 출처 표기.
"""
from __future__ import annotations

import json
import re
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from .media import ff_path, probe_duration, run_ffmpeg
from .models import Word

PLAN_FILE = "issue_plan.json"
PROMPTS_FILE = "issue_prompts.md"
STATE_FILE = "issue_state.json"
SOURCES_FILE = "photo_sources.json"
PHOTOS_DIR = "photos"
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")

BAND_TOP = 0.27            # 사진 띠 시작(화면 높이 비율)
BAND_HEIGHT = 0.46
LINE_PAD = 0.12            # 줄 사이 숨
LINE_MAX_CHARS = 30
TITLE_MAX_CHARS = 14
TAG_MAX_CHARS = 12
TTS_CHARS_PER_SEC = 6.2    # 빠른 썰체(+20%) 추정. 길이 경고용
ZOOM_PER_SEC = 0.012       # 사진 하나에서 초당 확대량
COLORS = {"white": "#FFFFFF", "yellow": "#FFE14D", "red": "#FF4141", "green": "#5BFF6A"}
MARKS = ("", "x", "question", "exclaim")
PHOTO_ID = re.compile(r"^[A-Z][0-9]{2}$")
AI_SUFFIX = ("photorealistic", "no text", "no watermark", "no logo")


class IssueError(RuntimeError):
    pass


class PhotoSource(BaseModel):
    kind: Literal["youtube", "news", "community", "web", "other"] = "news"
    url: str = Field(description="원본 위치(유튜브 영상·기사·게시글 주소)")
    title: str = ""
    site: str = Field("", description="화면 출처 표기에 쓸 이름(예: 연합뉴스, ○○커뮤니티, 유튜브 채널명)")
    at: float | None = Field(None, description="유튜브 프레임 시각(초)")


class IssuePhoto(BaseModel):
    id: str = Field(description="P01 형식. Flow 결과 이름·파일 이름과 같게")
    kind: Literal["ai", "real"]
    desc: str = Field(description="무엇을 보여 주는 사진인지(한국어 한 줄)")
    prompt: str = Field("", description="ai: Flow Nano Banana 영문 프롬프트(실사·뉴스 사진풍)")
    refs: list[str] = Field(default_factory=list, description="ai: 인물·장소를 맞출 앞 AI 사진 id")
    source: PhotoSource | None = Field(None, description="real: 캡처할 원본")
    fit: Literal["auto", "cover", "contain"] = "auto"
    focus: Literal["center", "top", "bottom"] = Field("center", description="cover 로 자를 때 남길 쪽(글 캡처는 top)")
    hide_note: str = Field("", description="real: 가려야 할 것(닉네임·얼굴·번호판 등). 캡처할 때 가린다")


class IssueLine(BaseModel):
    text: str = Field(description="나레이션 한 문장 = 자막 한 줄")
    photo: str = Field(description="이 줄에 보일 사진 id")
    color: Literal["white", "yellow", "red", "green"] = "white"
    tag: str = Field("", description="사진 위 반응 태그. 예: (!!!) (???) (ㄷㄷ) \"좋은데??\"")
    mark: Literal["", "x", "question", "exclaim"] = Field("", description="사진 위 큰 표시: 빨간 X / 물음표 / 느낌표")


class IssuePlan(BaseModel):
    topic: str
    title_top: str = Field(description="화면 고정 제목 윗줄(흰색)")
    title_bottom: str = Field(description="화면 고정 제목 아랫줄(노랑)")
    titles: list[str] = Field(default_factory=list, description="업로드 제목 후보")
    facts: list[str] = Field(default_factory=list, description="확인한 사실(출처와 대조한 것만)")
    character_bible: str = Field("", description="AI 사진에 반복 등장하는 인물·장소 고정 묘사(영문)")
    voice_rate: str = Field("+20%", description="Edge TTS 속도")
    lines: list[IssueLine]
    photos: list[IssuePhoto]
    sources: list[str] = Field(default_factory=list, description="조사에 쓴 기사·자료 주소")


# ---------------------------------------------------------------- 기획서

def estimate_seconds(plan: IssuePlan) -> float:
    chars = sum(len(re.sub(r"\s", "", ln.text)) for ln in plan.lines)
    return round(chars / TTS_CHARS_PER_SEC + LINE_PAD * len(plan.lines), 1)


def check_plan(plan: IssuePlan) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    ids = [p.id for p in plan.photos]
    for pid in ids:
        if not PHOTO_ID.match(pid):
            errors.append(f"사진 id 는 P01 형식: {pid}")
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        errors.append(f"사진 id 중복: {dup}")
    known = set(ids)
    used = {ln.photo for ln in plan.lines}
    for i, ln in enumerate(plan.lines, 1):
        if not ln.text.strip():
            errors.append(f"{i}번 줄 문장이 비었습니다")
        if ln.photo not in known:
            errors.append(f"{i}번 줄의 사진 {ln.photo} 가 photos 에 없습니다")
        if len(ln.text) > LINE_MAX_CHARS:
            warnings.append(f"{i}번 줄이 {len(ln.text)}자 — {LINE_MAX_CHARS}자 이하로 쪼개면 리듬이 산다")
        if len(ln.tag) > TAG_MAX_CHARS:
            warnings.append(f"{i}번 줄 태그가 깁니다: {ln.tag}")
    for p in plan.photos:
        if p.id not in used:
            warnings.append(f"쓰지 않는 사진: {p.id}")
        if p.kind == "ai":
            if not p.prompt.strip():
                errors.append(f"{p.id}: AI 사진은 prompt 가 필요합니다")
            bad = [r for r in p.refs if r not in known or r == p.id]
            if bad:
                errors.append(f"{p.id}: 없는 참조 사진 {bad}")
        else:
            if not p.source or not p.source.url.strip():
                errors.append(f"{p.id}: 실제 사진은 source.url(원본 위치)이 필요합니다")
            elif p.source.kind == "community" and not p.hide_note:
                warnings.append(f"{p.id}: 커뮤니티 캡처는 hide_note 에 가릴 것(닉네임·프로필)을 적으세요")
    for label, t in (("title_top", plan.title_top), ("title_bottom", plan.title_bottom)):
        if not t.strip():
            errors.append(f"{label} 가 비었습니다")
        elif len(t) > TITLE_MAX_CHARS:
            warnings.append(f"{label} 가 {len(t)}자 — {TITLE_MAX_CHARS}자 넘으면 글씨가 작아진다")
    n = len(plan.lines)
    if n < 6:
        errors.append(f"줄이 {n}개 — 6줄 이상 필요합니다")
    elif n > 24:
        warnings.append(f"줄이 {n}개 — 많습니다(보통 10~18)")
    sec = estimate_seconds(plan)
    if sec > 58:
        warnings.append(f"예상 길이 약 {sec}초 — 쇼츠 60초를 넘을 수 있습니다")
    elif sec < 20:
        warnings.append(f"예상 길이 약 {sec}초 — 짧습니다(보통 30~45초)")
    if plan.photos and all(p.kind == "ai" for p in plan.photos):
        warnings.append("실제 사진이 하나도 없습니다 — 이슈의 근거(기사·글 캡처)를 최소 1장 넣으세요")
    if not plan.facts:
        warnings.append("facts(확인한 사실)가 비었습니다")
    return errors, warnings


def load_plan(job_dir: Path) -> IssuePlan:
    p = job_dir / PLAN_FILE
    if not p.is_file():
        raise IssueError(f"이슈 쇼츠 프로젝트가 아닙니다: {job_dir.name}")
    return IssuePlan.model_validate_json(p.read_text(encoding="utf-8"))


def save_plan(job_dir: Path, plan: IssuePlan) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / PLAN_FILE).write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    (job_dir / PROMPTS_FILE).write_text(prompts_markdown(plan), encoding="utf-8")


def flow_prompt(plan: IssuePlan, photo: IssuePhoto) -> str:
    """Flow 에이전트 창에 그대로 넣을 문장. 인물 고정 묘사와 실사·글자 금지를 빠짐없이 붙인다."""
    body = photo.prompt.strip()
    low = body.lower()
    extra = [w for w in AI_SUFFIX if w not in low]
    parts = [f"Use the prompt exactly as written. Landscape 4:3 photo. Name the result '{photo.id}'."]
    if photo.refs:
        parts.append(f"Use {', '.join(photo.refs)} as the visual reference for the same person and place.")
    parts.append(body)
    if plan.character_bible and photo.refs:
        parts.append(f"Character continuity: {plan.character_bible}")
    parts.append("Documentary news photo look, natural light, realistic skin and fabric. " + ", ".join(extra) + "."
                 if extra else "Documentary news photo look, natural light.")
    return " ".join(parts)


def prompts_markdown(plan: IssuePlan) -> str:
    out = [f"# {plan.topic}", "", f"화면 제목: {plan.title_top} / {plan.title_bottom}",
           f"예상 길이: 약 {estimate_seconds(plan)}초 · 줄 {len(plan.lines)}개 · 사진 {len(plan.photos)}장", ""]
    ai = [p for p in plan.photos if p.kind == "ai"]
    real = [p for p in plan.photos if p.kind == "real"]
    out += ["## AI 사진 (Google Flow · Nano Banana · 이미지 4:3 가로)", ""]
    if plan.character_bible:
        out += [f"인물 고정 묘사: {plan.character_bible}", ""]
    for p in ai:
        out += [f"### {p.id} — {p.desc}", "", "```", flow_prompt(plan, p), "```", ""]
    out += ["## 실제 사진 (캡처)", ""]
    for p in real:
        s = p.source
        where = f"{s.url}" + (f" · {s.at:.1f}초" if s and s.at is not None else "") if s else "(원본 없음)"
        out.append(f"- **{p.id}** {p.desc} — {s.kind if s else ''} {where}" + (f" · 가릴 것: {p.hide_note}" if p.hide_note else ""))
    out += ["", "## 대본", ""]
    for i, ln in enumerate(plan.lines, 1):
        extra = " ".join(x for x in (ln.tag, f"[{ln.mark}]" if ln.mark else "") if x)
        out.append(f"{i:02d}. [{ln.photo}·{ln.color}] {ln.text}" + (f"  {extra}" if extra else ""))
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- 사진 받기

def photo_path(job_dir: Path, pid: str) -> Path | None:
    for ext in IMAGE_EXT:
        p = job_dir / PHOTOS_DIR / f"{pid}{ext}"
        if p.is_file():
            return p
    return None


def photo_status(job_dir: Path, plan: IssuePlan | None = None) -> dict[str, Any]:
    plan = plan or load_plan(job_dir)
    have = [p.id for p in plan.photos if photo_path(job_dir, p.id)]
    missing_ai = [p.id for p in plan.photos if p.kind == "ai" and p.id not in have]
    missing_real = [p.id for p in plan.photos if p.kind == "real" and p.id not in have]
    return {"photos_total": len(plan.photos), "photos_ready": len(have),
            "missing_ai": missing_ai, "missing_real": missing_real,
            "ready": not missing_ai and not missing_real}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _record(job_dir: Path, pid: str, entry: dict[str, Any]) -> None:
    p = job_dir / SOURCES_FILE
    data = _read_json(p)
    data[pid] = {**entry, "added_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _place(job_dir: Path, pid: str, src: Path) -> Path:
    ext = src.suffix.lower()
    if ext not in IMAGE_EXT:
        raise IssueError(f"이미지 파일이 아닙니다({ext}): {src.name}")
    d = job_dir / PHOTOS_DIR
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob(f"{pid}.*"):
        old.unlink()
    dst = d / f"{pid}{'.jpg' if ext == '.jpeg' else ext}"
    shutil.copy2(src, dst)
    return dst


def _photo(plan: IssuePlan, pid: str) -> IssuePhoto:
    p = next((x for x in plan.photos if x.id == pid), None)
    if p is None:
        raise IssueError(f"기획서에 없는 사진 id: {pid} ({', '.join(x.id for x in plan.photos)})")
    return p


def _source_entry(photo: IssuePhoto, how: str, **extra: Any) -> dict[str, Any]:
    s = photo.source
    base = {"kind": photo.kind, "how": how, "desc": photo.desc}
    if photo.kind == "ai":
        base.update(origin="Google Flow (AI 생성)", rights_status="generated")
    elif s:
        base.update(origin=s.kind, url=s.url, title=s.title, site=s.site, at=s.at,
                    rights_status="transformative_quote", purpose="news/commentary")
    return {**base, **{k: v for k, v in extra.items() if v is not None}}


def add_file(job_dir: Path, pid: str, file: Path) -> dict[str, Any]:
    """Flow 에서 받은 이미지나 브라우저로 찍은 캡처 파일을 넣는다."""
    plan = load_plan(job_dir)
    photo = _photo(plan, pid)
    if not file.is_file():
        raise IssueError(f"파일이 없습니다: {file}")
    dst = _place(job_dir, pid, file)
    _record(job_dir, pid, _source_entry(photo, "file", file=file.name))
    return {"photo": pid, "file": str(dst), "kind": photo.kind}


def add_from_dir(job_dir: Path, from_dir: Path, since: float | None = None) -> dict[str, Any]:
    """다운로드 폴더에서 이름이 사진 id 로 시작하는 이미지(Flow 결과 이름 'P01…')를 찾아 넣는다."""
    plan = load_plan(job_dir)
    if not from_dir.is_dir():
        raise IssueError(f"폴더가 없습니다: {from_dir}")
    files = sorted((f for f in from_dir.iterdir() if f.suffix.lower() in IMAGE_EXT
                    and (since is None or f.stat().st_mtime >= since)), key=lambda f: f.stat().st_mtime)
    added = []
    for photo in plan.photos:
        hits = [f for f in files if re.match(rf"^{photo.id}(?![0-9])", f.name, re.I)]
        if hits:
            added.append(add_file(job_dir, photo.id, hits[-1]))
    return {"added": added, **photo_status(job_dir, plan)}


async def youtube_frame(url: str, at: float, out: Path) -> Path:
    """유튜브 영상의 한 시각 프레임을 1장 뽑는다(전체 다운로드 없이 스트림에서 바로)."""
    import yt_dlp  # 무거운 모듈이라 쓸 때만

    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "format": "bv*[height<=1080][ext=mp4]/bv*[height<=1080]/b"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    stream = info.get("url") or next((f.get("url") for f in reversed(info.get("requested_formats") or [])
                                      if f.get("vcodec") not in (None, "none")), None)
    if not stream:
        raise IssueError("유튜브 영상 주소를 얻지 못했습니다")
    out.parent.mkdir(parents=True, exist_ok=True)
    await run_ffmpeg(["-ss", f"{max(0.0, at):.2f}", "-i", stream, "-frames:v", "1", "-q:v", "2", str(out)])
    if not out.is_file():
        raise IssueError("프레임을 뽑지 못했습니다")
    return out


async def add_youtube(job_dir: Path, pid: str, url: str | None, at: float | None) -> dict[str, Any]:
    plan = load_plan(job_dir)
    photo = _photo(plan, pid)
    s = photo.source
    url = url or (s.url if s and s.kind == "youtube" else None)
    at = at if at is not None else (s.at if s else None)
    if not url or at is None:
        raise IssueError(f"{pid}: 유튜브 주소와 --at 초가 필요합니다")
    tmp = job_dir / PHOTOS_DIR / f"_{pid}_frame.jpg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    await youtube_frame(url, at, tmp)
    dst = _place(job_dir, pid, tmp)
    tmp.unlink(missing_ok=True)
    _record(job_dir, pid, _source_entry(photo, "youtube_frame", url=url, at=at))
    return {"photo": pid, "file": str(dst), "kind": photo.kind, "at": at}


def add_image_url(job_dir: Path, pid: str, image_url: str) -> dict[str, Any]:
    """기사 대표 사진처럼 이미지 주소가 따로 있을 때 그대로 받는다."""
    plan = load_plan(job_dir)
    photo = _photo(plan, pid)
    ext = Path(image_url.split("?")[0]).suffix.lower()
    ext = ext if ext in IMAGE_EXT else ".jpg"
    tmp = job_dir / PHOTOS_DIR / f"_{pid}_dl{ext}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - 사용자가 고른 사진 주소
        data = r.read(20 * 1024 * 1024)
    if len(data) < 1000:
        raise IssueError("받은 이미지가 너무 작습니다(주소 확인)")
    tmp.write_bytes(data)
    dst = _place(job_dir, pid, tmp)
    tmp.unlink(missing_ok=True)
    _record(job_dir, pid, _source_entry(photo, "image_url", image_url=image_url))
    return {"photo": pid, "file": str(dst), "kind": photo.kind}


# ---------------------------------------------------------------- 상태

def read_state(job_dir: Path) -> dict[str, Any]:
    return _read_json(job_dir / STATE_FILE)


def mark(job_dir: Path, **fields: Any) -> dict[str, Any]:
    state = {**read_state(job_dir), **fields, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    (job_dir / STATE_FILE).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


# ---------------------------------------------------------------- 편집

def segments(plan: IssuePlan, lengths: list[float]) -> list[dict[str, Any]]:
    """같은 사진이 이어지는 줄은 한 덩어리로 묶는다(끊기지 않고 계속 확대)."""
    out: list[dict[str, Any]] = []
    t = 0.0
    for ln, d in zip(plan.lines, lengths):
        if out and out[-1]["photo"] == ln.photo:
            out[-1]["duration"] = round(out[-1]["duration"] + d, 3)
        else:
            out.append({"photo": ln.photo, "start": round(t, 3), "duration": round(d, 3)})
        t += d
    return out


def _band(height: int) -> tuple[int, int]:
    top = int(height * BAND_TOP) // 2 * 2
    return top, int(height * BAND_HEIGHT) // 2 * 2


def _fit_mode(photo: IssuePhoto, w: int, h: int, bw: int, bh: int) -> str:
    if photo.fit != "auto":
        return photo.fit
    ratio = (w / h) / (bw / bh) if h else 1
    return "cover" if 0.8 <= ratio <= 1.3 else "contain"


def segment_filter(i: int, photo: IssuePhoto, mode: str, dur: float, width: int, height: int, fps: int) -> str:
    """입력 [i:v] 사진 → 사진 띠 크기로 맞추고 천천히 확대 → 1080x1920 검정 화면의 띠 자리에 [v{i}]."""
    top, bh = _band(height)
    frames = max(1, int(round(dur * fps)))
    z = f"min(1+{ZOOM_PER_SEC / fps:.6f}*on,1.25)"
    zoom = (f"scale={width * 2}:{bh * 2},zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":s={width}x{bh}:fps={fps}")
    y = {"top": "0", "bottom": "ih-oh", "center": "(ih-oh)/2"}[photo.focus]
    if mode == "cover":
        fit = (f"[{i}:v]scale={width}:{bh}:force_original_aspect_ratio=increase,"
               f"crop={width}:{bh}:(iw-ow)/2:{y},setsar=1,{zoom}[b{i}]")
    else:
        fit = (f"[{i}:v]split=2[bg{i}][fg{i}];"
               f"[bg{i}]scale={width}:{bh}:force_original_aspect_ratio=increase,crop={width}:{bh},"
               f"boxblur=24:2,eq=brightness=-0.12,setsar=1[bgb{i}];"
               f"[fg{i}]scale={width}:{bh}:force_original_aspect_ratio=decrease,setsar=1[fgs{i}];"
               f"[bgb{i}][fgs{i}]overlay=(W-w)/2:(H-h)/2,{zoom}[b{i}]")
    return (f"{fit};[b{i}]trim=end_frame={frames},setpts=PTS-STARTPTS,"
            f"pad={width}:{height}:0:{top}:black,format=yuv420p[v{i}]")


def _ass_color(hex_rgb: str, alpha: int = 0) -> str:
    h = hex_rgb.lstrip("#")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _ts(sec: float) -> str:
    sec = max(0.0, sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "＼").replace("{", "(").replace("}", ")").replace("\n", " ")


def _wrap(text: str, per_line: int) -> list[str]:
    from .subtitles import wrap_title
    return wrap_title(" ".join(text.split()), per_line, max_lines=2)


def build_ass(plan: IssuePlan, starts: list[float], lengths: list[float], credits: list[dict[str, Any]],
              out: Path, width: int, height: int, font: str) -> Path:
    k = width / 1080
    s = lambda v: max(1, int(v * k))  # noqa: E731
    top, bh = _band(height)
    white, black = _ass_color("#FFFFFF"), _ass_color("#000000")
    total = starts[-1] + lengths[-1] if starts else 0.0
    title_y = top - s(40)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ISTitle,{font},{s(86)},{white},{white},{black},{black},-1,0,0,0,100,100,-2,0,1,0,0,2,40,40,0,1
Style: ISLine,{font},{s(54)},{white},{white},{_ass_color('#000000', 0x10)},{black},-1,0,0,0,100,100,-1,0,3,{s(12)},0,2,60,60,0,1
Style: ISTag,{font},{s(54)},{_ass_color(COLORS['green'])},{white},{black},{black},-1,0,0,0,100,100,-1,0,1,{s(5)},0,8,60,60,0,1
Style: ISMark,{font},{s(300)},{_ass_color(COLORS['red'])},{white},{white},{_ass_color('#000000', 0x80)},-1,0,0,0,100,100,0,0,1,{s(6)},{s(4)},5,0,0,0,1
Style: ISCredit,{font},{s(30)},{_ass_color('#BBBBBB')},{white},{black},{black},0,0,0,0,100,100,0,0,1,0,0,9,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev: list[str] = []
    yellow = _ass_color(COLORS["yellow"])
    if total > 0:
        ev.append(f"Dialogue: 5,{_ts(0)},{_ts(total)},ISTitle,,0,0,0,,"
                  f"{{\\an2\\pos({width // 2},{title_y - s(100)})}}{_esc(plan.title_top)}")
        ev.append(f"Dialogue: 5,{_ts(0)},{_ts(total)},ISTitle,,0,0,0,,"
                  f"{{\\an2\\pos({width // 2},{title_y})\\c{yellow}}}{_esc(plan.title_bottom)}")
    per = max(8, int((width - 160) / (54 * k)))
    marks = {"question": "?", "exclaim": "!"}
    for ln, st, d in zip(plan.lines, starts, lengths):
        en = st + d
        rows = _wrap(ln.text, per)
        body = "\\N".join(_esc(r) for r in rows)
        col = _ass_color(COLORS[ln.color])
        ev.append(f"Dialogue: 4,{_ts(st)},{_ts(en)},ISLine,,0,0,0,,"
                  f"{{\\an2\\pos({width // 2},{top + bh - s(28)})\\c{col}\\fad(30,40)"
                  f"\\fscx80\\fscy80\\t(0,150,0.5,\\fscx100\\fscy100)}}{body}")
        if ln.tag.strip():
            ev.append(f"Dialogue: 4,{_ts(st)},{_ts(en)},ISTag,,0,0,0,,"
                      f"{{\\an8\\pos({width // 2},{top + s(18)})\\fad(40,40)}}{_esc(ln.tag.strip())}")
        if ln.mark:
            pop = f"\\an5\\pos({width // 2},{top + bh // 2})\\fscx140\\fscy140\\t(0,160,0.5,\\fscx100\\fscy100)"
            if ln.mark == "x":   # 글꼴마다 ✕ 크기가 달라 도형으로 그린다
                a, b, c = s(170), s(120), s(50)
                pts = [(-a, -b), (-b, -a), (0, -c), (b, -a), (a, -b), (c, 0), (a, b), (b, a), (0, c),
                       (-b, a), (-a, b), (-c, 0)]
                xy = [f"{x + a} {y + a}" for x, y in pts]   # n5 는 도형 상자 기준이라 좌표를 양수로
                shape = f"m {xy[0]} l " + " ".join(xy[1:])
                ev.append(f"Dialogue: 3,{_ts(st)},{_ts(en)},ISMark,,0,0,0,,{{{pop}\\p1}}{shape}{{\\p0}}")
            else:
                ev.append(f"Dialogue: 3,{_ts(st)},{_ts(en)},ISMark,,0,0,0,,{{{pop}}}{marks[ln.mark]}")
    for c in credits:
        if c.get("text"):
            ev.append(f"Dialogue: 2,{_ts(c['start'])},{_ts(c['start'] + c['duration'])},ISCredit,,0,0,0,,"
                      f"{{\\an9\\pos({width - s(30)},{top + bh + s(14)})}}{_esc(c['text'])}")
    out.write_text(head + "\n".join(ev) + "\n", encoding="utf-8-sig")
    return out


def credit_text(photo: IssuePhoto, recorded: dict[str, Any] | None) -> str:
    if photo.kind != "real":
        return ""
    s = photo.source
    site = (s.site if s else "") or (recorded or {}).get("site") or ""
    if not site and s:
        site = {"youtube": "유튜브", "community": "온라인 커뮤니티", "news": "언론 보도"}.get(s.kind, "")
    return f"출처: {site}" if site else ""


async def assemble(job_dir: Path, cfg: dict[str, Any], *, sfx: bool = True,
                   log: Callable[[str], None] = lambda m: None) -> dict[str, Any]:
    """photos/ + 줄별 Edge TTS → final.mp4 (사진 띠 레이아웃)."""
    from . import fantube
    from . import run as runmod   # 무거운 모듈이라 실제 편집할 때만
    from .flowshorts import pad_join_audio
    from .tts import get_tts

    plan = load_plan(job_dir)
    status = photo_status(job_dir, plan)
    if not status["ready"]:
        raise IssueError(f"아직 없는 사진: AI {status['missing_ai']} · 실제 {status['missing_real']}")

    tcfg = {**cfg, "tts": {**cfg["tts"], "rate": plan.voice_rate or cfg["tts"].get("rate", "+0%")}}
    tts = get_tts(tcfg)
    voice = cfg["tts"]["voice"]
    attempts = 1 + max(0, int(cfg["tts"].get("retries", 2)))
    wait = float(cfg["tts"].get("retry_wait", 1.5))
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    parts: list[Path] = []
    lengths: list[float] = []
    for i, ln in enumerate(plan.lines, 1):
        p = audio_dir / f"line_{i:02d}.mp3"
        _words, dur = await runmod._synthesize_one(tts, ln.text, p, voice, attempts, wait, log=log)
        parts.append(p)
        lengths.append(round(dur + LINE_PAD, 3))
        log(f"음성 {i}/{len(plan.lines)} · {dur:.2f}초")
    narration = job_dir / "narration.mp3"
    starts = await pad_join_audio(parts, lengths, narration)
    total = round(sum(lengths), 3)

    w, h, fps = int(cfg["video"]["width"]), int(cfg["video"]["height"]), int(cfg["video"]["fps"])
    _top, bh = _band(h)
    photos = {p.id: p for p in plan.photos}
    recorded = _read_json(job_dir / SOURCES_FILE)
    segs = segments(plan, lengths)
    inputs: list[str] = []
    filters: list[str] = []
    credits: list[dict[str, Any]] = []
    for i, sg in enumerate(segs):
        photo = photos[sg["photo"]]
        path = photo_path(job_dir, photo.id)
        info = await _image_size(path)
        mode = _fit_mode(photo, info[0], info[1], w, bh)
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{sg['duration'] + 0.2:.3f}", "-i", str(path)]
        filters.append(segment_filter(i, photo, mode, sg["duration"], w, h, fps))
        credits.append({**sg, "text": credit_text(photo, recorded.get(photo.id))})
    n = len(segs)
    filters.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[cat]")
    ass = build_ass(plan, starts, lengths, credits, job_dir / "subs.ass", w, h,
                    font=cfg["video"].get("font", "Malgun Gothic"))
    from .render import _subtitle_filter
    filters.append(f"[cat]{_subtitle_filter(ass, Path(cfg['paths']['assets']) / 'fonts')}[vout]")

    narr_idx = n
    inputs += ["-i", str(narration)]
    if sfx:
        events = fantube.sfx_events([sg["start"] for sg in segs],
                                    [{"text": ln.text, "start": st} for ln, st in zip(plan.lines, starts)])
        sfx_f = fantube.sfx_filters(events, total, gain=0.8)
    else:
        sfx_f = []
    if sfx_f:
        filters += sfx_f
        filters.append(f"[{narr_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[nar];"
                       f"[nar][sfx]amix=inputs=2:duration=first:normalize=0[aout]")
    else:
        filters.append(f"[{narr_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[aout]")
    final = job_dir / "final.mp4"
    log("렌더 중…")
    await run_ffmpeg([*inputs, "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
                      "-t", f"{total:.3f}", "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                      "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)])
    seconds = await probe_duration(final)
    (job_dir / "meta.txt").write_text(meta_text(plan, recorded), encoding="utf-8")
    mark(job_dir, stage="done", final=str(final), seconds=round(seconds, 2))
    return {"final_video": str(final), "seconds": round(seconds, 2), "resolution": f"{w}x{h}",
            "lines": len(plan.lines), "photo_cuts": n,
            "photos": {"ai": sum(p.kind == "ai" for p in plan.photos), "real": sum(p.kind == "real" for p in plan.photos)}}


async def _image_size(path: Path) -> tuple[int, int]:
    from .media import probe_video
    info = await probe_video(path)
    st = (info.get("streams") or [{}])[0]
    return int(st.get("width") or 1), int(st.get("height") or 1)


def meta_text(plan: IssuePlan, recorded: dict[str, Any]) -> str:
    lines = ["[제목 후보]", *(plan.titles or [f"{plan.title_top} {plan.title_bottom}"]), "", "[확인한 사실]",
             *[f"- {f}" for f in plan.facts], "", "[조사 출처]", *[f"- {u}" for u in plan.sources], "", "[사진 출처]"]
    for p in plan.photos:
        r = recorded.get(p.id, {})
        if p.kind == "ai":
            lines.append(f"- {p.id}: AI 생성 이미지(Google Flow) — {p.desc}")
        else:
            s = p.source
            lines.append(f"- {p.id}: {(s.site or s.kind) if s else ''} {s.url if s else ''}"
                         + (f" ({s.at:.1f}초)" if s and s.at is not None else "") + f" — {p.desc}")
    lines += ["", "※ AI 생성 이미지가 포함된 재연 장면입니다(업로드 시 '변경되거나 합성된 콘텐츠' 표시 권장)."]
    return "\n".join(lines) + "\n"


__all__ = ["IssuePlan", "IssueLine", "IssuePhoto", "PhotoSource", "IssueError", "check_plan", "load_plan",
           "save_plan", "photo_status", "add_file", "add_from_dir", "add_youtube", "add_image_url", "assemble",
           "segments", "build_ass", "flow_prompt", "prompts_markdown", "estimate_seconds", "Word", "ff_path"]
