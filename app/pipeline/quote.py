"""transformative_quote: 분석·비평·비교·해설을 위한 인용 자료 처리.

외부 자료의 직접 재업로드를 기본 동작으로 하지 않는다. 재사용 라이선스가 없는 외부 영상·캡처라도
분석·비평·비교·해설·근황 설명·장면 관찰·사실 검증에 필요한 범위라면 인용 후보로 쓴다.

- 근거 역할 장면(benchmark profile evidence_roles)에만 배치한다. 훅·마지막 질문 장면은 자체 카드.
- 영상은 Clip Analyzer 로 필요한 최소 구간만 고르고(benchmark 가 찾은 근거 시각 우선), 장면의 나머지는 정지 화면 + 해설.
- 캡처 2장 이상이 비교 장면에 오면 전/후 비교 레이아웃으로 합성한다.
- 렌더 전 guard 가 비중·해설·출처·중복·질문 연결을 검사해 인용을 줄이거나 정지 화면/카드로 바꾼다.
고정 초 규칙("3초면 안전")은 두지 않는다. 비율은 영상 길이·장면 길이·원본 길이에 대한 상대값이다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import clip_analyzer
from .assets import kind_of, pinned_scene
from .models import Word
from .sources import QUOTE_LICENSE, SourceRegistry

PLAN_FILE = "quote_plan.json"
CONTEXT_FILE = "source_context.json"   # 분석한 링크(제목·채널·주소). resume 때 인용 출처·근거 시각 연결에 쓴다
PURPOSE = "분석·비평·비교·해설"
# 상대 비율 (고정 초가 아님)
SCENE_MOTION_SHARE = 0.6      # 인용 영상이 움직이는 시간은 장면 길이의 60%까지, 나머지는 정지 화면 + 해설
VIDEO_MOTION_SHARE = 0.4      # 완성 영상 전체에서 인용 영상이 움직이는 시간 비중 상한
SOURCE_USE_SHARE = 0.3        # 한 원본에서 가져오는 총 길이는 원본 길이의 30%까지 (원본 대체 방지)
QUOTE_SCENE_SHARE = 0.75      # 인용 장면 비중 상한 (나머지는 자체 해설 화면)
MIN_COMMENTARY_CHARS = 8      # 인용 장면의 해설(나레이션) 최소 글자
COMPARE_ROLES = ("comparison", "change", "trials", "ranked")
Progress = Callable[[str, int, str], None]


def quote_rights(*, title: str = "", channel: str = "", url: str = "", purpose: str = PURPOSE,
                 basis: str = "사용자가 제공한 분석·해설용 인용 자료") -> dict[str, Any]:
    """factory/웹이 인용 파일을 등록할 때 쓰는 rights 사전. 라이선스 확인이 아니라 목적·출처 기록이다."""
    who = channel.strip() or title.strip() or url.strip()
    label = " · ".join(x for x in (channel.strip(), title.strip()[:40]) if x) or url.strip()
    return {"license": QUOTE_LICENSE, "purpose": purpose, "media_status": "local_file",
            "attribution": {"title": title.strip(), "channel": channel.strip(), "url": url.strip()},
            "credit": f"인용: {label}"[:80] if who else "", "rights_basis": basis, "license_note": basis}


def enrich_attribution(registry: SourceRegistry, url: str, info: dict[str, Any]) -> None:
    """URL 분석에서 얻은 제목·채널로, 같은 URL 을 출처로 단 인용 파일의 출처 기록을 채운다."""
    for item in list(registry.items.values()):
        if item.license != QUOTE_LICENSE or not item.path or item.attribution.get("url") != url:
            continue
        if item.attribution.get("title") and item.attribution.get("channel"):
            continue
        r = quote_rights(title=info.get("title", ""), channel=info.get("channel", ""), url=url,
                         purpose=item.purpose or PURPOSE)
        registry.add(kind=item.kind, origin=item.origin, path=item.path, title=item.title,
                     source_type=item.source_type or "external_video", rights=r)


def load_context(job_dir: Path) -> dict[str, Any]:
    path = job_dir / CONTEXT_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def load_transcript(job_dir: Path) -> list[Word] | None:
    path = job_dir / "transcript.json"
    if not path.is_file():
        return None
    return [Word.model_validate(w) for w in json.loads(path.read_text(encoding="utf-8"))]


def quote_items(registry: SourceRegistry) -> list[Any]:
    """화면 후보가 될 수 있는 사용자 제공 인용 자료 (목적·출처가 기록된 것)."""
    out = [i for i in registry.items.values()
           if i.license == QUOTE_LICENSE and i.origin == "upload" and i.path and Path(i.path).is_file()
           and i.usable_in_video and kind_of(Path(i.path))]
    return sorted(out, key=lambda i: Path(i.path).name.lower())


def has_quote_video(registry: SourceRegistry) -> bool:
    return any(i.kind == "video" for i in quote_items(registry))


def target_scenes(script: Any, spec: dict[str, Any] | None) -> list[int]:
    roles = set((spec or {}).get("evidence_roles") or [])
    card_roles = set((spec or {}).get("card_roles") or [])
    n = len(script.scenes)
    if roles:
        found = [i for i, s in enumerate(script.scenes) if getattr(s, "beat_role", "") in roles]
        if found:
            return found
    # 구조 정보가 없으면 첫 장면(훅)과 마지막 장면을 빼고 순서대로
    return [i for i, s in enumerate(script.scenes) if 0 < i < n - 1 and getattr(s, "beat_role", "") not in card_roles]


# ---------- 비교 레이아웃 ----------

def _font(size: int) -> ImageFont.ImageFont:
    for name in ("malgunbd.ttf", "malgun.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def compose_compare(a: Path, b: Path, out: Path, *, labels: tuple[str, str] = ("A", "B"),
                    width: int = 1080, height: int = 1920) -> Path:
    """캡처 두 장을 위·아래 비교 화면으로 합성한다 (상단 키워드 아래 ~ 자막 위 영역). 라벨은 앱이 그린다."""
    top, bottom = int(height * 0.23), int(height * 0.62)
    gap = int(height * 0.012)
    cell_h = (bottom - top - gap) // 2
    with Image.open(a) as im:
        base = im.convert("RGB")
    bg = base.resize((width, int(base.height * width / base.width))).resize((width, height)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (width, height), (0, 0, 0)), 0.45)
    draw = ImageDraw.Draw(bg)
    font = _font(int(height * 0.024))
    for k, (src, label) in enumerate(((a, labels[0]), (b, labels[1]))):
        with Image.open(src) as im:
            img = im.convert("RGB")
        scale = min((width - 80) / img.width, cell_h / img.height)
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
        y = top + k * (cell_h + gap) + (cell_h - img.height) // 2
        x = (width - img.width) // 2
        bg.paste(img, (x, y))
        draw.rectangle((x, y, x + img.width - 1, y + img.height - 1), outline=(255, 212, 0), width=4)
        tw = draw.textlength(label, font=font)
        draw.rectangle((x, y, x + tw + 28, y + font.size + 18), fill=(255, 212, 0))
        draw.text((x + 14, y + 8), label, fill=(20, 20, 20), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    bg.save(out, quality=92)
    return out


# ---------- 배치 ----------

def _overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


async def plan_quotes(*, job_dir: Path, registry: SourceRegistry, script: Any, durations: list[float],
                      spec: dict[str, Any] | None, decision: dict[str, Any] | None,
                      transcript: list[Word] | None = None, transcript_url: str = "", transcript_path: str = "",
                      skip: set[int] | None = None, progress: Progress = lambda *a: None) -> dict[int, dict[str, Any]]:
    """사용자가 준 인용 영상·캡처를 근거 역할 장면에 배치한다. 반환: 장면 번호 → resolved 항목."""
    items = quote_items(registry)
    if not items:
        return {}
    skip = set(skip or set())
    scenes = [i for i in target_scenes(script, spec) if i not in skip]
    pinned: dict[int, Any] = {}
    rest: list[Any] = []
    for it in items:
        k = pinned_scene(Path(it.path).name)
        if k is not None and 0 <= k < len(script.scenes) and k not in pinned:
            pinned[k] = it
        else:
            rest.append(it)
    moments = list((decision or {}).get("evidence_moments") or [])
    used_ranges: dict[str, list[tuple[float, float]]] = {}
    out: dict[int, dict[str, Any]] = {}
    images = [it for it in rest if it.kind == "image"]
    videos = [it for it in rest if it.kind == "video"]
    order = sorted(set(scenes) | set(pinned))
    vid_cycle = 0
    for i in order:
        role = getattr(script.scenes[i], "beat_role", "")
        need = durations[i] if i < len(durations) else 4.0
        it = pinned.get(i)
        if it is None:
            compare = any(r in role for r in COMPARE_ROLES)
            if compare and len(images) >= 2:
                a, b = images.pop(0), images.pop(0)
                path = compose_compare(Path(a.path), Path(b.path), job_dir / "scenes" / f"quote_compare_{i:02d}.jpg",
                                       labels=("앞", "뒤") if "change" in role else ("A", "B"))
                registry.add(kind="image", origin="derived", path=str(path), title=f"장면 {i + 1} 비교",
                             parent_id=a.id, rights={**a.model_dump(), "credit": a.credit or b.credit})
                registry.mark_used(b.path, i + 1)
                out[i] = {"kind": "image", "path": str(path), "credit": a.credit, "quote": True,
                          "asset_source": "quote_source", "layout": "compare", "rights_status": QUOTE_LICENSE,
                          "page_url": a.attribution.get("url", ""), "parents": [a.path, b.path],
                          "reason": "인용 캡처 2장을 전/후 비교 레이아웃으로 합성 (해설 자막·나레이션과 함께)"}
                continue
            if videos:
                it = videos[vid_cycle % len(videos)]
                vid_cycle += 1
            elif images:
                it = images.pop(0)
            else:
                continue
        if it.kind == "image":
            out[i] = {"kind": "image", "path": it.path, "credit": it.credit, "quote": True,
                      "asset_source": "quote_source", "layout": "single", "rights_status": QUOTE_LICENSE,
                      "page_url": it.attribution.get("url", ""),
                      "reason": "사용자 제공 인용 캡처 — 확대·정지 화면 위에 해설"}
            continue
        # 영상: 필요한 최소 구간. benchmark 가 찾은 근거 시각(같은 원본일 때)을 우선한다.
        play = max(0.5, need * SCENE_MOTION_SHARE)
        same_source = ((bool(transcript_url) and it.attribution.get("url") == transcript_url)
                       or (bool(transcript_path) and Path(it.path) == Path(transcript_path)))
        prefer = [(float(m.get("start_sec", 0)), float(m.get("end_sec", 0))) for m in moments
                  if float(m.get("end_sec", 0)) > float(m.get("start_sec", 0))] if same_source else []
        keywords = [getattr(script.scenes[i], "on_screen_text", ""), script.scenes[i].narration]
        try:
            analysis = await clip_analyzer.analyze(Path(it.path), play, keywords=keywords,
                                                   transcript=transcript if same_source else None,
                                                   prefer=prefer, avoid=list(used_ranges.get(it.path, [])), top=5)
        except Exception as e:  # noqa: BLE001 - 분석 실패 장면은 인용하지 않는다
            progress("images", 30, f"장면 {i + 1} 인용 구간 분석 실패: {e}")
            continue
        rec = analysis.recommended
        if not rec:
            continue
        used_ranges.setdefault(it.path, []).append((rec.start, rec.end))
        out[i] = {"kind": "video", "path": it.path, "start": rec.start, "end": rec.end, "play": round(rec.end - rec.start, 2),
                  "clip_range": rec.label, "source_duration": analysis.duration, "credit": it.credit, "quote": True,
                  "asset_source": "quote_source", "layout": "single", "rights_status": QUOTE_LICENSE,
                  "page_url": it.attribution.get("url", ""),
                  "clip_candidates": [{"range": c.label, "score": c.score, "reason": c.reason} for c in analysis.candidates],
                  "reason": f"사용자 제공 인용 영상 구간 {rec.label} ({rec.reason}) — 나머지는 정지 화면 + 해설"}
    return out


# ---------- 렌더 전 안전 검사 ----------

def guard(entries: dict[int, dict[str, Any]], script: Any, durations: list[float],
          decision: dict[str, Any] | None, registry: SourceRegistry,
          spec: dict[str, Any] | None = None) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    """인용이 콘텐츠의 주목적이 되지 않게 한다. 문제가 있으면 구간을 줄이거나(정지 화면) 카드로 되돌린다."""
    actions: list[str] = []
    warnings: list[str] = []
    out = {i: dict(e) for i, e in entries.items()}
    quotes = {i: e for i, e in out.items() if e.get("quote")}
    total = sum(durations) or 1.0
    roles = set((spec or {}).get("evidence_roles") or [])
    vq = (decision or {}).get("viewer_question", "")

    for i in sorted(quotes):
        e = quotes[i]
        narration = " ".join(script.scenes[i].narration.split()) if i < len(script.scenes) else ""
        if len(narration) < MIN_COMMENTARY_CHARS:
            actions.append(f"장면 {i + 1}: 해설(나레이션)이 없어 인용을 빼고 자체 카드로 대체")
            out.pop(i)
            continue
        item = registry.by_path(e["path"])
        parent_ok = all((registry.by_path(p) and registry.by_path(p).credit) for p in e.get("parents", []))
        if not (e.get("credit") and item and item.credit and parent_ok):
            actions.append(f"장면 {i + 1}: 원본 출처 표기가 없어 인용 제외")
            out.pop(i)
            continue
        role = getattr(script.scenes[i], "beat_role", "")
        if roles and role not in roles:
            warnings.append(f"장면 {i + 1}: 근거 역할({', '.join(sorted(roles))}) 밖의 인용")
        if not vq:
            warnings.append(f"장면 {i + 1}: viewer_question 이 없어 인용과 질문의 연결을 확인할 수 없음")
        if e["kind"] == "video":
            cap = durations[i] * SCENE_MOTION_SHARE
            if e.get("play", 0) > cap:
                actions.append(f"장면 {i + 1}: 인용 구간을 장면의 {int(SCENE_MOTION_SHARE * 100)}% 로 줄이고 나머지는 정지 화면")
                e["play"] = round(cap, 2)

    quotes = {i: e for i, e in out.items() if e.get("quote")}
    # 같은 원본의 같은 구간 반복 금지
    seen: dict[str, list[tuple[float, float, int]]] = {}
    for i in sorted(quotes):
        e = quotes[i]
        if e["kind"] != "video":
            continue
        rng = (e["start"], e["start"] + e["play"])
        for s0, s1, j in seen.get(e["path"], []):
            if _overlaps(rng, (s0, s1)):
                actions.append(f"장면 {i + 1}: 장면 {j + 1}과 같은 원본 구간이라 인용 제외")
                out.pop(i)
                break
        else:
            seen.setdefault(e["path"], []).append((rng[0], rng[1], i))

    quotes = {i: e for i, e in out.items() if e.get("quote")}
    # 인용 장면 비중: 자체 해설 화면이 남도록
    limit = max(1, int(len(script.scenes) * QUOTE_SCENE_SHARE))
    for i in sorted(quotes)[limit:]:
        actions.append(f"장면 {i + 1}: 인용 장면이 너무 많아(상한 {limit}개) 자체 카드로 대체")
        out.pop(i)

    quotes = {i: e for i, e in out.items() if e.get("quote")}
    # 원본 대체 방지: 한 원본에서 쓰는 총 길이
    by_src: dict[str, list[int]] = {}
    for i, e in quotes.items():
        if e["kind"] == "video":
            by_src.setdefault(e["path"], []).append(i)
    for path, idx in by_src.items():
        src_dur = float(quotes[idx[0]].get("source_duration") or 0)
        used = sum(quotes[i]["play"] for i in idx)
        if src_dur and used > src_dur * SOURCE_USE_SHARE:
            k = src_dur * SOURCE_USE_SHARE / used
            for i in idx:
                quotes[i]["play"] = round(max(0.3, quotes[i]["play"] * k), 2)
            actions.append(f"{Path(path).name}: 원본 길이의 {int(SOURCE_USE_SHARE * 100)}% 를 넘지 않게 구간 축소")

    # 완성 영상에서 인용 영상이 움직이는 시간 비중
    motion = sum(e["play"] for e in quotes.values() if e["kind"] == "video")
    if motion > total * VIDEO_MOTION_SHARE:
        k = total * VIDEO_MOTION_SHARE / motion
        for e in quotes.values():
            if e["kind"] == "video":
                e["play"] = round(max(0.3, e["play"] * k), 2)
        actions.append(f"인용 영상 비중을 전체의 {int(VIDEO_MOTION_SHARE * 100)}% 이하로 줄임 (정지 화면 + 해설로 대체)")
        motion = sum(e["play"] for e in quotes.values() if e["kind"] == "video")
    for e in quotes.values():
        if e["kind"] == "video":
            e["end"] = round(e["start"] + e["play"], 2)
            e["clip_range"] = f"{clip_analyzer.fmt(e['start'])}-{clip_analyzer.fmt(e['end'])}"

    report = {"quote_scenes": sorted(i + 1 for i in quotes), "quote_motion_seconds": round(motion, 2),
              "video_seconds": round(total, 2), "quote_motion_share": round(motion / total, 3),
              "limits": {"scene_motion_share": SCENE_MOTION_SHARE, "video_motion_share": VIDEO_MOTION_SHARE,
                         "source_use_share": SOURCE_USE_SHARE, "quote_scene_share": QUOTE_SCENE_SHARE},
              "commentary_present": all(len(script.scenes[i].narration.strip()) >= MIN_COMMENTARY_CHARS for i in quotes),
              "attribution_present": all(bool(e.get("credit")) for e in quotes.values()),
              "viewer_question": vq, "actions": actions, "warnings": warnings,
              "scenes": {str(i + 1): {k: v for k, v in e.items() if k in ("kind", "layout", "clip_range", "play", "credit", "reason")}
                         for i, e in sorted(quotes.items())}}
    return out, report


def save_report(job_dir: Path, report: dict[str, Any]) -> None:
    (job_dir / PLAN_FILE).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
