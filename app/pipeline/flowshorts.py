"""Google Flow 공학 쇼츠: 기획서(flow_plan.json) 검증 · 프롬프트 문서 · Flow 클립 받기 · 최종 편집.

흐름 (docs/FLOW_SHORTS.md):
  1) 채팅의 Claude 가 presets/flow_engineering.md 지침으로 조사·대본·프롬프트를 써서 flow_plan.json 저장
  2) 브라우저 자동화(.claude/skills/flow-shorts)가 Flow 에서 CLEAN/INFO 이미지 → Omni 8초 영상을 만들고 내려받음
  3) import_clips 가 내려받은 영상을 clips/scene_NN.mp4 자리에 넣음
  4) assemble 이 장면별 Edge TTS 내레이션 + 카라오케 자막 + 클립을 이어 final.mp4 로 렌더

Flow 공개 API 는 없으므로 이 모듈은 Flow 를 직접 부르지 않는다(생성은 브라우저 단계의 몫).
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from .media import has_audio, probe_duration, run_ffmpeg
from .models import Word

PLAN_FILE = "flow_plan.json"
PROMPTS_FILE = "flow_prompts.md"
STATE_FILE = "flow_state.json"
CLIPS_DIR = "clips"
VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")
SHOT_IDS = ("A", "B", "C")
CLEAN_NEGATIVE = ("no text", "no watermark", "no logo", "no arrows", "no hud")
CONTINUITY = "maintain exact structural continuity"
SHOW_TAIL = 2.0      # 내레이션이 짧아도 클립 끝에서 최대 이만큼만 잘라낸다 (마지막 컷이 보이도록)
NARR_PAD = 0.35      # 장면 내레이션 뒤 숨 쉴 틈
TTS_CHARS_PER_SEC = 5.3   # Edge TTS 한국어 실측 50글자=9.4초 (2026-11-18)


class FlowError(RuntimeError):
    pass


class FlowShot(BaseModel):
    shot: Literal["A", "B", "C"]
    role: str = Field(description="이 컷이 보여주는 것(한국어 한 줄)")
    clean_prompt: str = Field(description="Nano Banana 2 CLEAN 이미지 프롬프트(영문 완전체)")
    info_prompt: str = Field("", description="같은 CLEAN 을 편집하는 INFO 프롬프트. 비우면 CLEAN 유지")
    graphic: str = Field("", description="핵심 그래픽 요약(구성표용)")


class FlowScene(BaseModel):
    index: int = Field(description="1부터")
    narration: str = Field(description="이 8초 장면의 내레이션(한국어)")
    shots: list[FlowShot]
    video_prompt: str = Field(description="Gemini Omni Flash 8초·3컷 영상 프롬프트(영문 완전체)")


class FlowSource(BaseModel):
    url: str
    supports: str = Field(description="이 출처가 뒷받침하는 내용")


class FlowPlan(BaseModel):
    topic: str
    angle: str = Field(description="핵심 각도: 중심 질문·모순·답 2~3문장")
    factcheck: list[str] = Field(default_factory=list, description="확정 사실·핵심 수치·주의할 주장")
    titles: list[str] = Field(default_factory=list)
    visual_bible: str = Field(description="비주얼 바이블(영문 또는 한영 혼용)")
    clip_seconds: float = Field(8.0, ge=4, le=15, description="Omni 클립 길이(초). Omni 1.2 는 15초까지")
    scenes: list[FlowScene]
    sources: list[FlowSource] = Field(default_factory=list)


# ---------------------------------------------------------------- 기획서

def max_chars(clip_seconds: float) -> int:
    """클립 길이 안에 읽히는 내레이션 글자 수(공백·문장부호 제외)."""
    return int((clip_seconds - NARR_PAD) * TTS_CHARS_PER_SEC)


def check_plan(plan: FlowPlan) -> tuple[list[str], list[str]]:
    """(errors, warnings). errors 가 있으면 Flow 단계로 넘어가지 않는다."""
    errors: list[str] = []
    warnings: list[str] = []
    if not plan.scenes:
        errors.append("장면이 없습니다")
    for pos, sc in enumerate(plan.scenes, 1):
        tag = f"Scene {pos}"
        if sc.index != pos:
            errors.append(f"{tag}: index 가 {sc.index} 입니다 (1부터 차례대로)")
        if not sc.narration.strip():
            errors.append(f"{tag}: 내레이션이 비었습니다")
        syl = len(re.sub(r"[^가-힣A-Za-z0-9]", "", sc.narration))
        if syl > max_chars(plan.clip_seconds):
            warnings.append(f"{tag}: 내레이션 {syl}글자 — {plan.clip_seconds:g}초 클립보다 길어 끝 화면이 멈춥니다 "
                            f"(권장 {max_chars(plan.clip_seconds)}글자 이하)")
        if [s.shot for s in sc.shots] != list(SHOT_IDS):
            errors.append(f"{tag}: 컷은 정확히 A·B·C 순서 3개여야 합니다")
        for s in sc.shots:
            low = s.clean_prompt.lower()
            if not low.strip():
                errors.append(f"{tag}/{s.shot}: CLEAN 프롬프트가 비었습니다")
                continue
            miss = [n for n in CLEAN_NEGATIVE if n not in low]
            if miss:
                errors.append(f"{tag}/{s.shot}: CLEAN 네거티브 누락 {miss}")
            if "9:16" not in low and "vertical" not in low:
                warnings.append(f"{tag}/{s.shot}: CLEAN 에 9:16(vertical) 표기가 없습니다")
        if sum(bool(s.info_prompt.strip()) for s in sc.shots) == 3:
            warnings.append(f"{tag}: 3컷 모두 INFO 입니다 (기본 1~2컷)")
        if CONTINUITY not in sc.video_prompt.lower():
            errors.append(f"{tag}: 영상 프롬프트에 'Maintain exact structural continuity' 가 없습니다")
    n = len(plan.scenes)
    if n and not 10 <= n <= 13:
        warnings.append(f"장면 {n}개 (권장 11~12개)")
    text = " ".join(sc.narration for sc in plan.scenes)
    words = len(text.split())
    sentences = len([s for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s])
    if text and not 200 <= words <= 280:
        warnings.append(f"내레이션 {words}어절 (권장 220~260)")
    if text and not 22 <= sentences <= 35:
        warnings.append(f"내레이션 {sentences}문장 (권장 25~32)")
    if len(plan.sources) < 2:
        warnings.append("출처가 2개 미만입니다 (핵심 수치 교차 확인 권장)")
    if len(plan.titles) < 3:
        warnings.append("제목 후보가 3개 미만입니다")
    return errors, warnings


def load_plan(job_dir: Path) -> FlowPlan:
    p = job_dir / PLAN_FILE
    if not p.is_file():
        raise FlowError(f"{PLAN_FILE} 이 없습니다: {job_dir}")
    return FlowPlan.model_validate_json(p.read_text(encoding="utf-8"))


def save_plan(job_dir: Path, plan: FlowPlan) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / PLAN_FILE).write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    (job_dir / PROMPTS_FILE).write_text(prompts_markdown(plan), encoding="utf-8")


def prompts_markdown(plan: FlowPlan) -> str:
    """사람이 보고 Flow 에 복사할 수 있는 문서 (브라우저 자동화도 같은 순서로 쓴다)."""
    out = [f"# {plan.topic}", "", "## 🎯 핵심 각도", plan.angle, ""]
    if plan.titles:
        out += ["## 🧲 제목 후보", *[f"- {t}" for t in plan.titles], ""]
    out += ["## 📝 최종 내레이션 대본", *[sc.narration for sc in plan.scenes], ""]
    out += ["## ⏱️ 8초 Scene 구성표", "", "| Scene | 내레이션 | A | B | C |", "|---|---|---|---|---|"]
    for sc in plan.scenes:
        cells = [f"{s.role} ({'INFO' if s.info_prompt.strip() else 'CLEAN'})" for s in sc.shots]
        out.append(f"| {sc.index} | {sc.narration} | " + " | ".join(cells) + " |")
    out += ["", "## 🎨 비주얼 바이블", plan.visual_bible, ""]
    for sc in plan.scenes:
        out.append(f"## Scene {sc.index}")
        for s in sc.shots:
            out += [f"🖼️ CLEAN 이미지(Flow·Nano Banana 2): [Scene {sc.index} / Shot {s.shot}]", "```", s.clean_prompt, "```"]
        for s in sc.shots:
            if s.info_prompt.strip():
                out += [f"📊 INFO 편집(Flow·Nano Banana 2): [Scene {sc.index} / Shot {s.shot} | edit the CLEAN image]",
                        "```", s.info_prompt, "```"]
            else:
                out.append(f"Shot {s.shot}: INFO 사용 안 함 — CLEAN 유지")
        out += [f"🎬 영상(Flow·Gemini Omni Flash): [Scene {sc.index} | {plan.clip_seconds:g}s | 3 Shots]", "```", sc.video_prompt, "```", ""]
    if plan.factcheck or plan.sources:
        out.append("## ✅ 팩트체크·출처")
        out += [f"- {f}" for f in plan.factcheck]
        out += [f"- {s.url} — {s.supports}" for s in plan.sources]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- 클립 자리

def clip_path(job_dir: Path, index: int) -> Path:
    return job_dir / CLIPS_DIR / f"scene_{index:02d}.mp4"


def clip_status(job_dir: Path, plan: FlowPlan | None = None) -> dict[str, Any]:
    plan = plan or load_plan(job_dir)
    have = [sc.index for sc in plan.scenes if clip_path(job_dir, sc.index).is_file()]
    missing = [sc.index for sc in plan.scenes if sc.index not in have]
    return {"scenes": len(plan.scenes), "have": have, "missing": missing,
            "next_scene": missing[0] if missing else None, "ready": not missing}


def import_clips(job_dir: Path, *, scene: int | None = None, file: Path | None = None,
                 from_dir: Path | None = None, since: float | None = None) -> dict[str, Any]:
    """영상을 장면 자리에 복사한다(원본은 그대로 둔다).

    - scene+file: 그 장면 자리에 넣는다(덮어씀).
    - from_dir(+since 에포크 초): 그 폴더에서 since 이후 생긴 영상을 오래된 순으로 비어 있는 장면에 차례로 넣는다.
      브라우저 자동화가 장면 순서대로 하나씩 내려받는다는 전제다.
    """
    plan = load_plan(job_dir)
    valid = {sc.index for sc in plan.scenes}
    (job_dir / CLIPS_DIR).mkdir(exist_ok=True)
    placed: list[dict[str, Any]] = []
    if file is not None:
        if scene not in valid:
            raise FlowError(f"없는 장면 번호입니다: {scene} (1~{len(plan.scenes)})")
        if not file.is_file() or file.suffix.lower() not in VIDEO_EXT:
            raise FlowError(f"영상 파일이 아닙니다: {file}")
        shutil.copy2(file, clip_path(job_dir, scene))
        placed.append({"scene": scene, "file": str(file)})
    elif from_dir is not None:
        if not from_dir.is_dir():
            raise FlowError(f"폴더가 없습니다: {from_dir}")
        used = {_read_state(job_dir).get("imported", {}).get(str(i)) for i in valid}
        found = sorted((p for p in from_dir.iterdir()
                        if p.is_file() and p.suffix.lower() in VIDEO_EXT
                        and (since is None or p.stat().st_mtime >= since) and str(p) not in used
                        and not p.name.endswith((".crdownload", ".part"))),
                       key=lambda p: p.stat().st_mtime)
        missing = clip_status(job_dir, plan)["missing"]
        for idx, src in zip(missing, found):
            shutil.copy2(src, clip_path(job_dir, idx))
            placed.append({"scene": idx, "file": str(src)})
    else:
        raise FlowError("--file(+--scene) 또는 --from 폴더 중 하나가 필요합니다")
    state = _read_state(job_dir)
    imported = state.setdefault("imported", {})
    for p in placed:
        imported[str(p["scene"])] = p["file"]
    _write_state(job_dir, state)
    return {"placed": placed, **clip_status(job_dir, plan)}


def _read_state(job_dir: Path) -> dict[str, Any]:
    p = job_dir / STATE_FILE
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def _write_state(job_dir: Path, state: dict[str, Any]) -> None:
    (job_dir / STATE_FILE).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def mark(job_dir: Path, **fields: Any) -> dict[str, Any]:
    state = _read_state(job_dir)
    state.update(fields, updated_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    _write_state(job_dir, state)
    return state


# ---------------------------------------------------------------- 편집

def scene_lengths(narr: list[float], clips: list[float]) -> list[float]:
    """장면 길이 = 내레이션+여유. 짧아도 클립 끝 SHOW_TAIL 초 이상은 자르지 않고, 클립보다 길면 마지막 프레임을 유지한다."""
    return [round(max(n + NARR_PAD, c - SHOW_TAIL), 3) for n, c in zip(narr, clips)]


async def pad_join_audio(parts: list[Path], lengths: list[float], out: Path, sample_rate: int = 24000) -> list[float]:
    """장면 음성을 각 장면 길이에 맞춰 뒤를 무음으로 채워 잇는다. 장면 시작 오프셋을 돌려준다."""
    inputs: list[str] = []
    filters: list[str] = []
    for i, (p, ln) in enumerate(zip(parts, lengths)):
        inputs += ["-i", str(p)]
        filters.append(f"[{i}:a]aformat=sample_rates={sample_rate}:channel_layouts=mono,"
                       f"apad,atrim=0:{ln:.3f},asetpts=PTS-STARTPTS[a{i}]")
    filters.append("".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[out]")
    await run_ffmpeg([*inputs, "-filter_complex", ";".join(filters), "-map", "[out]",
                      "-c:a", "libmp3lame", "-q:a", "2", str(out)])
    offsets, t = [], 0.0
    for ln in lengths:
        offsets.append(round(t, 3))
        t += ln
    return offsets


async def assemble(job_dir: Path, cfg: dict[str, Any], *, clip_volume: float = 0.12, subtitles: bool = True,
                   log: Callable[[str], None] = lambda m: None) -> dict[str, Any]:
    """clips/scene_NN.mp4 + 장면별 TTS + 자막 → final.mp4."""
    from . import run as runmod   # 무거운 모듈이라 실제 편집할 때만 불러온다
    from .render import render_broll
    from .subtitles import build_ass
    from .tts import get_tts

    plan = load_plan(job_dir)
    status = clip_status(job_dir, plan)
    if not status["ready"]:
        raise FlowError(f"아직 영상이 없는 장면: {status['missing']}")

    tts = get_tts(cfg)
    voice = cfg["tts"]["voice"]
    attempts = 1 + max(0, int(cfg["tts"].get("retries", 2)))
    wait = float(cfg["tts"].get("retry_wait", 1.5))
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    parts: list[Path] = []
    words_rel: list[list[Word]] = []
    narr_len: list[float] = []
    for sc in plan.scenes:
        p = audio_dir / f"scene_{sc.index:02d}.mp3"
        words, dur = await runmod._synthesize_one(tts, sc.narration, p, voice, attempts, wait, log=log)
        parts.append(p)
        words_rel.append(words or [])
        narr_len.append(dur)
        log(f"음성 {sc.index}/{len(plan.scenes)} · {dur:.2f}초")

    clip_files = [clip_path(job_dir, sc.index) for sc in plan.scenes]
    clip_len = [await probe_duration(c) for c in clip_files]
    lengths = scene_lengths(narr_len, clip_len)
    narration = job_dir / "narration.mp3"
    offsets = await pad_join_audio(parts, lengths, narration)

    w, h, fps = int(cfg["video"]["width"]), int(cfg["video"]["height"]), int(cfg["video"]["fps"])
    ass_path = None
    if subtitles:
        per_scene = [[Word(text=x.text, start=round(min(x.start, ln) + off, 3), end=round(min(x.end, ln) + off, 3))
                      for x in ws] for ws, off, ln in zip(words_rel, offsets, lengths)]
        st = cfg.get("subtitles") or {}
        ass_path = build_ass(per_scene, job_dir / "subs.ass", w, h, font=cfg["video"].get("font", "Malgun Gothic"),
                             size=int(st.get("size", 64)), highlight=st.get("highlight", "#FFD400"),
                             outline=st.get("outline", "#000000"))
    clips = [{"kind": "video", "path": c, "start": 0.0, "duration": ln, "has_audio": await has_audio(c)}
             for c, ln in zip(clip_files, lengths)]
    final = job_dir / "final.mp4"
    log("렌더 중…")
    await render_broll(clips, narration, final, ass_path, width=w, height=h, fps=fps,
                       source_volume=clip_volume, blur_background=True,
                       fonts_dir=Path(cfg["paths"]["assets"]) / "fonts")
    total = await probe_duration(final)
    (job_dir / "meta.txt").write_text(_meta(plan), encoding="utf-8")
    mark(job_dir, stage="done", final=str(final), seconds=round(total, 2))
    return {"final_video": str(final), "seconds": round(total, 2), "resolution": f"{w}x{h}",
            "scenes": [{"scene": sc.index, "seconds": ln, "narration_seconds": round(n, 2), "clip_seconds": round(c, 2)}
                       for sc, ln, n, c in zip(plan.scenes, lengths, narr_len, clip_len)]}


def _meta(plan: FlowPlan) -> str:
    lines = ["[제목 후보]", *plan.titles, "", "[설명]", plan.angle, "", "[출처]"]
    lines += [f"- {s.url}" for s in plan.sources]
    return "\n".join(lines) + "\n"
