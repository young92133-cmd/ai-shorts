"""콘텐츠팩토리 조종부 (Factory Layer).

Claude Code / Codex 가 자연어 요청을 받아 부르는 명령들. 새 제작 엔진이 아니라 app/pipeline 의
기존 기능(조사·대본·장면 설계·TTS·화면 선택·권리 검사·자막·렌더)을 그대로 호출한다.

모든 함수는 AI 가 읽기 쉬운 dict(JSON)를 돌려준다: status / project_id / message / next_action + 결과 경로.
프로젝트 상태는 output/<project_id>/project_state.json 에 저장돼, 중간에 멈췄다가 resume 할 수 있다.

    Claude/Codex ─┐
                  ↓
            app.factory (이 파일)
                  ↓
             app/pipeline
                  ↑
    Web UI ───────┘ (현재는 jobs.py 가 직접 호출, 장기적으로 이 층을 쓰게 한다)
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

from ..carousel import characters as charmod, pipeline as carouselmod
from ..carousel.schema import CAROUSEL_FORMATS, OUTPUT_FORMATS
from ..carousel.templates import list_templates, load_template
from ..config import load_config, load_presets, merge_options
from ..pipeline import blueprint as bpmod, capcut, cards, research, timeline as tlmod, visuals as visualsmod
from ..pipeline import run as runmod, llm as llmmod, bench_auto, quote as quotemod
from ..pipeline.assets import kind_of
from ..pipeline.media import probe_video, require_ffmpeg
from ..pipeline.models import PlannedScript, VisualDecision
from ..pipeline.script_split import EMPHASIS_MAX, trend_direction
from ..pipeline.sources import SourceRegistry
from ..pipeline.styles import load_styles, nfc
from . import state as st
from .intent import detect_output_format

Log = Callable[[str], None]
PID_RE = re.compile(r"^[A-Za-z0-9_-]{3,80}$")
CARD_CHOICES = tuple(k for k in cards.CARD_KINDS if k != "safe_card")
FORMATS = {
    "information": {"name": "정보형", "instructions": "정보/상식을 쉽게 설명하고 근거 없는 숫자나 단정을 보태지 마세요."},
    "story": {"name": "스토리/사연형", "instructions": "상황→작은 변화→결말의 이야기로 구성하세요. 창작 사연은 창작이라고 명시하고 실제 사건처럼 꾸미지 마세요."},
    "issue": {"name": "일반 이슈형", "instructions": "이슈의 배경→핵심→생활에 미치는 영향을 정리하세요. 불확실한 정보는 단정하지 마세요."},
}


class FactoryError(Exception):
    """명령을 수행할 수 없는 상황. code 로 종류를 구분한다 (not_found / invalid / not_ready ...)."""

    def __init__(self, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra

    def as_dict(self) -> dict[str, Any]:
        return {"status": "error", "error": self.code, "message": self.message, **self.extra}


# ---------- 공통 ----------

def _cfg() -> dict[str, Any]:
    return load_config()


def output_root() -> Path:
    return Path(_cfg()["paths"]["output"])


def _projects() -> list[Path]:
    root = output_root()
    dirs = [p.parent for p in root.glob(f"*/{st.FILE}")]
    return sorted(dirs, key=lambda d: st.load(d).get("created", ""), reverse=True)


def project_dir(project_id: str | None) -> Path:
    """프로젝트 폴더. id 를 안 주면 가장 최근 프로젝트."""
    if not project_id:
        found = _projects()
        if not found:
            raise FactoryError("not_found", "아직 만든 프로젝트가 없습니다. make 로 먼저 만들어 주세요.")
        return found[0]
    if not PID_RE.match(project_id):
        raise FactoryError("invalid", f"프로젝트 id 형식이 올바르지 않습니다: {project_id}")
    d = output_root() / project_id
    if not st.exists(d):
        raise FactoryError("not_found", f"프로젝트를 찾을 수 없습니다: {project_id}",
                           recent=[p.name for p in _projects()[:5]])
    return d


def _new_id() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]


def find_style(name: str | None) -> dict[str, Any] | None:
    """스타일 id 또는 이름(일부만 맞아도 됨)으로 찾는다."""
    if not name:
        return None
    styles = load_styles(_cfg())
    key = nfc(name).strip()
    if key in styles:
        return styles[key]
    hits = [s for s in styles.values() if key.lower() in nfc(str(s.get("name", ""))).lower()]
    if len(hits) == 1:
        return hits[0]
    raise FactoryError("invalid", f"스타일을 찾을 수 없거나 여러 개가 맞습니다: {name}",
                       styles=[{"id": s["id"], "name": s.get("name", "")} for s in styles.values()])


def _run_cfg(request: dict[str, Any]) -> dict[str, Any]:
    cfg = _cfg()
    presets = load_presets(cfg)
    preset = request.get("preset") or "daily"
    if preset not in presets:
        raise FactoryError("invalid", f"프리셋이 없습니다: {preset}", presets=list(presets))
    overrides = {"llm_provider": request.get("llm"), "llm_model": request.get("model"),
                 "tts_provider": request.get("tts"), "voice": request.get("voice"),
                 "target_seconds": request.get("seconds")}
    if request.get("subtitles") is not None:   # 안 정했으면 프리셋 기본값을 따른다
        overrides["subtitles"] = bool(request["subtitles"])
    out = merge_options(cfg, presets[preset], overrides)
    if out["llm"]["provider"] not in ("claude", "openai", "auto"):
        raise FactoryError("invalid", "Factory AI 모드는 claude / openai / auto 중 하나여야 합니다.")
    if request.get("allow_openai") is not None:
        out["llm"]["allow_paid_openai"] = request["allow_openai"] is True
    if out["llm"]["provider"] == "openai":
        if not llmmod.paid_allowed("openai", out["llm"]):
            raise FactoryError("paid_not_allowed", "OpenAI API 사용을 먼저 명시적으로 허용해 주세요 (--allow-openai 또는 config.yaml).")
        if not llmmod.env("OPENAI_API_KEY"):
            raise FactoryError("missing_key", "OpenAI API 키가 설정되지 않았습니다. 비밀값을 채팅에 붙이지 말고 사용자 설정에 저장해 주세요.")
    # V1은 기존 카드 렌더러와 무료 음성을 기본으로 한다. 프리셋/환경 키가 과금을 켜지 않는다.
    out["images"]["provider"] = "none"
    if not request.get("tts"):
        out["tts"]["provider"] = "edge"
        out["tts"]["voice"] = request.get("voice") or (presets[preset].get("voice") or {}).get("edge") or out["tts"]["voices"]["edge"]
    if out["tts"]["provider"] == "openai" and not llmmod.paid_allowed("openai", out["llm"]):
        raise FactoryError("paid_not_allowed", "OpenAI 음성 API도 --allow-openai 또는 설정상 명시적 허용이 필요합니다.")
    return out


def _ai_session(job_dir: Path, state: dict, cfg: dict):
    def record(event: dict) -> None:
        state.setdefault("ai_calls", []).append({**event, "at": st.now()})
        if event["status"] == "success":
            state["ai_provider_used"] = event["provider"]
            providers = state.setdefault("ai_providers_used", [])
            if event["provider"] not in providers:
                providers.append(event["provider"])
        st.save(job_dir, state)
    return llmmod.provider_session(cfg["llm"], record)


def _progress(job_dir: Path, state: dict[str, Any], log: Log):
    """엔진 진행 로그 → 상태 파일. 로그는 AI 가 볼 수 있게 log(보통 stderr)로 흘린다."""
    def fn(stage: str, pct: int, msg: str) -> None:
        log(f"[{stage} {pct:3d}%] {msg}")
        target = {("research", False): "researching", ("research", True): "research_complete",
                  ("script", True): "script_ready", ("tts", True): "tts_complete",
                  ("images", True): "visuals_complete", ("render", False): "rendering",
                  ("render", True): "rendering"}.get((stage, pct >= 100))
        if stage == "tts" and pct < 100:
            target = "blueprint_complete"   # 설계도는 대본 확정 때 저장되고, 음성 합성이 시작됐다는 뜻
        if target:
            st.advance(job_dir, state, target)
    return fn


def _summary(job_dir: Path, state: dict[str, Any], **extra: Any) -> dict[str, Any]:
    status = state.get("status", "")
    out = {"status": status, "project_id": state["project_id"], "project_dir": str(job_dir),
           "message": state.get("error") if status == "failed" else st.MESSAGE.get(status, ""),
           "next_action": st.next_action(state, job_dir)}
    out["ai_provider_used"] = state.get("ai_provider_used")
    out["ai_providers_used"] = state.get("ai_providers_used", [])
    if status == "failed":
        out["failed_at"] = state.get("failed_at", "")
    if state.get("benchmark"):
        out["benchmark"] = _bench_brief(state["benchmark"])
    out.update(extra)
    return out


def _bench_brief(bench: dict[str, Any]) -> dict[str, Any]:
    """응답 JSON 에 싣는 짧은 구조 선택 요약 (전체는 inspect --part benchmark)."""
    keys = ("mode", "selected_profile", "profile_name", "top3", "viewer_question", "view_potential_score",
            "selection_reason", "fallback_used", "warnings", "quality")
    return {k: bench[k] for k in keys if bench.get(k) not in (None, "", [])}


def _record_benchmark(job_dir: Path, state: dict[str, Any], result: dict[str, Any]) -> None:
    """파이프라인이 고른 구조를 상태 파일에 남긴다. resume/rerender 는 같은 결정을 유지한다."""
    decision = result.get("benchmark") or bench_auto.load_decision(job_dir)
    if decision:
        state["benchmark"] = bench_auto.state_view(decision)


def _script_view(job_dir: Path) -> dict[str, Any]:
    script = PlannedScript.model_validate_json((job_dir / "script.json").read_text(encoding="utf-8"))
    return {"topic": script.topic, "titles": script.titles, "script_path": str(job_dir / "script.json"),
            "total_chars": len(script.full_narration()),
            "scenes": [{"scene": i + 1, "role": s.scene_type, "content_kind": s.content_kind,
                        "narration": s.narration, "emphasis": s.on_screen_text}
                       for i, s in enumerate(script.scenes)]}


async def _finish(job_dir: Path, state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """렌더 완료 처리: 결과 확인 → 상태·출력 경로 저장 → 웹 UI 목록에도 보이게 job.json 기록."""
    final = Path(result["video"])
    if not final.is_file() or not final.stat().st_size:
        raise RuntimeError("렌더 결과 영상 파일이 없거나 비어 있습니다.")
    info = await probe_video(final)
    stream = (info.get("streams") or [{}])[0]
    duration = round(float((info.get("format") or {}).get("duration") or 0), 2)
    if not stream.get("width") or not stream.get("height") or duration <= 0:
        raise RuntimeError("렌더 결과의 해상도와 길이를 확인할 수 없습니다.")
    outputs = {name: str(job_dir / f) for name, f in (
        ("final_video", "final.mp4"), ("thumbnail", "thumb.jpg"), ("meta", "meta.txt"), ("script", "script.json"),
        ("blueprint", bpmod.FILE), ("timeline", tlmod.FILE), ("visuals", visualsmod.MANIFEST),
        ("sources", "sources.json")) if (job_dir / f).exists()}
    state = st.advance(job_dir, state, "render_complete", error="", failed_at="", outputs=outputs,
                       video={"duration": duration, "resolution": f"{stream.get('width')}x{stream.get('height')}"})
    _write_web_job(job_dir, state, result)
    bp = bpmod.load(job_dir)
    return _summary(job_dir, state, final_video=str(final), duration=duration,
                    resolution=state["video"]["resolution"], outputs=outputs,
                    scenes=[{"scene": s.index + 1, "visual": s.visual_decision.resolved_visual_type if s.visual_decision else "",
                             "start": s.timeline_start, "end": s.timeline_end} for s in bp.scenes])


def _write_web_job(job_dir: Path, state: dict[str, Any], result: dict[str, Any]) -> None:
    """웹 UI(보조 화면)가 같은 결과를 보여주도록 job.json 을 남긴다 (서버를 다시 켜면 목록에 보인다)."""
    req = state["request"]
    script = json.loads((job_dir / "script.json").read_text(encoding="utf-8")) if (job_dir / "script.json").exists() else None
    keep = ("video", "thumb", "meta", "duration", "topic", "timeline", "blueprint", "visual_plan", "visuals",
            "final_sources", "plan_method", "split_method", "benchmark")
    path = job_dir / "job.json"
    before = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    job = {"id": state["project_id"], "mode": req.get("mode", "topic"), "input": req.get("input", ""),
           "preset": req.get("preset", "daily"), "options": {"source": "factory"}, "status": "done", "stage": "done",
           "pct": 100, "message": "완료 (Claude/Codex 에서 제작)", "created": state.get("created", ""), "error": "",
           "logs": [], "script": script,
           "result": {**(before.get("result") or {}), **{k: v for k, v in result.items() if k in keep},
                      "rendered_at": dt.datetime.now().isoformat(timespec="seconds")}}
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _fail(job_dir: Path, state: dict[str, Any], e: Exception) -> dict[str, Any]:
    at = state.get("status", "")
    state = st.advance(job_dir, state, "failed", error=f"{type(e).__name__}: {llmmod.safe_error(e)}", failed_at=at)
    return _summary(job_dir, state)


# ---------- 명령 ----------

def _copy_assets(job_dir: Path, assets: list[str] | None, asset_rights: dict[str, Any] | None,
                 ref: Path | None, register: bool = False) -> dict[str, Any]:
    rights: dict[str, Any] = {}
    for path in assets or []:
        src = Path(path)
        if not src.is_file() or not kind_of(src):
            raise FactoryError("invalid", f"첨부 파일을 쓸 수 없습니다: {path}")
        (job_dir / "uploads").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, job_dir / "uploads" / src.name)
        rights[src.name] = asset_rights or {}
    if ref:
        (job_dir / "uploads").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ref, job_dir / "uploads" / ref.name)
        # 참고 파일은 권리 확인된 화면 자료와 분리한다. 분석용으로만 쓴다.
        rights[ref.name] = {"license": "reference_only"}
    if register and rights:
        # 캐러셀은 run_pipeline 을 거치지 않으므로 소스 대장에 직접 올린다 (쇼츠는 run_pipeline 이 올린다)
        registry = SourceRegistry(job_dir)
        for name, r in rights.items():
            f = job_dir / "uploads" / name
            registry.add(kind=kind_of(f) or "image", origin="upload", path=str(f), title=name, rights=r,
                         used_for="candidate")
    return rights

def parse_quote_source(text: str | None, default_url: str = "") -> dict[str, str]:
    """--quote-source "제목 | 채널 | URL" 또는 URL 하나. 비우면 분석한 링크(--url)를 출처로 쓴다."""
    parts = [x.strip() for x in (text or "").split("|")]
    url = next((x for x in parts if x.startswith(("http://", "https://"))), "") or default_url
    rest = [x for x in parts if x and not x.startswith(("http://", "https://"))]
    return {"title": rest[0] if rest else "", "channel": rest[1] if len(rest) > 1 else "", "url": url}


def _copy_quotes(job_dir: Path, quotes: list[str] | None, source: dict[str, str]) -> dict[str, Any]:
    """인용 자료(외부 영상·캡처)를 업로드 폴더로 복사한다. 권리 확인이 아니라 인용 목적·출처를 기록한다."""
    rights: dict[str, Any] = {}
    for path in quotes or []:
        src = Path(path)
        if not src.is_file() or not kind_of(src):
            raise FactoryError("invalid", f"인용 파일을 쓸 수 없습니다: {path}")
        (job_dir / "uploads").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, job_dir / "uploads" / src.name)
        rights[src.name] = quotemod.quote_rights(title=source.get("title") or src.stem, channel=source.get("channel", ""),
                                                 url=source.get("url", ""))
    return rights


async def make(*, topic: str | None = None, url: str | None = None, auto: bool = False, script_text: str | None = None,
               preset: str = "daily", style: str | None = None, seconds: int | None = None, review: bool = False,
               instructions: str = "", llm: str | None = None, model: str | None = None, tts: str | None = None,
               voice: str | None = None, subtitles: bool | None = None, assets: list[str] | None = None,
               asset_rights: dict[str, Any] | None = None, reference_video: str | None = None,
               hint: str = "", content_format: str | None = None, allow_openai: bool | None = None,
               benchmark: str | None = "auto", visuals: str | None = "auto", output_format: str | None = None,
               request_text: str = "", template: str | None = None, character: str | None = None,
               pages: int | None = None, research_file: str | None = None, quotes: list[str] | None = None,
               quote_source: str | None = None, quote_reference: bool = False, log: Log = print) -> dict[str, Any]:
    """쇼츠 한 편을 만든다. review=True 면 대본까지만 만들고 승인 대기로 멈춘다.

    benchmark: auto(기본, 8개 콘텐츠 구조 중 자동 선택) | off(기존 V1 구성) | profile id(강제 지정).
    visuals: auto(기본, 권리 확인 가능한 공개 영상·사진을 찾아 장면에 사용) | cards(자체 카드만).
    output_format: shorts(기본) | card_news | insta_toon | hybrid | all. 비우면 request_text(자연어)에서 알아낸다.
    quotes: 분석·비평·비교·해설에 인용할 외부 영상·캡처 파일 (transformative_quote). 재사용 라이선스를 묻지 않는다.
            근거 역할 장면에 필요한 최소 구간만, 해설과 출처 표기와 함께 쓴다. quote_source 로 제목·채널·주소를 남긴다.
    quote_reference: reference_video 파일 자체를 인용 자료로도 쓴다 (기본은 분석 전용).
    """
    output_format = output_format or (detect_output_format(request_text) if request_text else "shorts")
    if output_format not in OUTPUT_FORMATS:
        raise FactoryError("invalid", f"출력 형식은 {' / '.join(OUTPUT_FORMATS)} 중 하나여야 합니다.")
    if output_format != "shorts" or research_file:
        return await _make_carousel(
            output_format=output_format, topic=topic, url=url, auto=auto, script_text=script_text,
            research_file=research_file, preset=preset, seconds=seconds, review=review, instructions=instructions,
            llm=llm, model=model, tts=tts, voice=voice, subtitles=subtitles, assets=assets, asset_rights=asset_rights,
            reference_video=reference_video, content_format=content_format, allow_openai=allow_openai,
            benchmark=benchmark, visuals=visuals, template=template, character=character, pages=pages, log=log)
    visuals = visuals or "auto"
    if visuals not in ("auto", "cards"):
        raise FactoryError("invalid", "visuals 는 auto / cards 중 하나여야 합니다.")
    modes = [bool(topic), bool(url), bool(auto), bool(script_text), bool(reference_video)]
    if sum(modes) != 1:
        raise FactoryError("invalid", "topic / url / auto / script / reference-video 중 하나만 지정해 주세요.")
    if seconds is not None and (isinstance(seconds, bool) or not isinstance(seconds, int) or not 10 <= seconds <= 180):
        raise FactoryError("invalid", "목표 길이는 10~180초 사이 정수여야 합니다.")
    if content_format and content_format not in FORMATS:
        raise FactoryError("invalid", "형식은 information / story / issue 중 하나여야 합니다.")
    try:
        benchmark = bench_auto.validate_choice(benchmark)
    except ValueError as e:
        raise FactoryError("invalid", str(e), benchmarks=["auto", "off", *bench_auto.profile_ids()]) from e
    if content_format:
        instructions = f"{FORMATS[content_format]['instructions']}\n{instructions}".strip()
    mode = "topic" if topic else "url" if url else "auto" if auto else "upload" if reference_video else "script"
    text = topic or url or script_text or hint or ""
    ref = Path(reference_video).resolve() if reference_video else None
    if ref and (not ref.is_file() or kind_of(ref) != "video" or ref.stat().st_size > 200 * 1024 * 1024):
        raise FactoryError("invalid", "참고 영상은 200MB 이하의 읽을 수 있는 영상 파일이어야 합니다.")
    names = [Path(p).name for p in assets or []] + [Path(p).name for p in quotes or []] + ([ref.name] if ref else [])
    if len({n.casefold() for n in names}) != len(names):
        raise FactoryError("invalid", "첨부 파일과 참고 영상의 파일명이 겹칩니다. 이름을 다르게 해 주세요.")
    style_data = find_style(style)
    request = {"mode": mode, "input": text, "preset": preset, "style": style_data["id"] if style_data else None,
               "seconds": seconds, "review": review, "instructions": instructions, "llm": llm, "model": model,
               "tts": tts, "voice": voice, "subtitles": subtitles, "allow_openai": allow_openai,
               "format": content_format, "reference_name": ref.name if ref else "", "benchmark": benchmark,
               "visuals": visuals, "quotes": [Path(p).name for p in quotes or []],
               "quote_source": quote_source or "", "quote_reference": bool(quote_reference and ref)}
    run_cfg = _run_cfg(request)
    require_ffmpeg()
    project_id = _new_id()
    job_dir = output_root() / project_id
    state = st.save(job_dir, st.new(project_id, request))
    try:
        rights = _copy_assets(job_dir, assets, asset_rights, ref)
        qsource = parse_quote_source(quote_source, url or "")
        rights.update(_copy_quotes(job_dir, quotes, qsource))
        if ref and quote_reference:
            rights[ref.name] = quotemod.quote_rights(title=qsource.get("title") or ref.stem,
                                                     channel=qsource.get("channel", ""), url=qsource.get("url", ""))
        state = st.save(job_dir, {**state, "asset_rights": rights})
        with _ai_session(job_dir, state, run_cfg):
            result = await runmod.run_pipeline(
                job_dir, mode, text, run_cfg, progress=_progress(job_dir, state, log), review=None,
                until="script" if review else "done", instructions=instructions, style=style_data,
                upload_rights=rights, reference_name=request["reference_name"], benchmark=benchmark,
                source_search=visuals == "auto")
        state["topic"] = result.get("topic", "")
        _record_benchmark(job_dir, state, result)
        if review:
            state = st.advance(job_dir, state, "waiting_for_script_approval", topic=state["topic"])
            return _summary(job_dir, state, **_script_view(job_dir))
        return await _finish(job_dir, state, result)
    except Exception as e:  # noqa: BLE001 - 실패도 상태 파일에 남기고 JSON 으로 알린다
        return _fail(job_dir, state, e)


def _carousel_view(out: dict[str, Any]) -> dict[str, Any]:
    keys = ("format", "dir", "pages", "manifest", "title", "mix", "plan_method", "master_method", "fallback_pages",
            "image_pages")
    return {k: out[k] for k in keys if k in out}


async def _make_carousel(*, output_format: str, topic: str | None, url: str | None, auto: bool, script_text: str | None,
                         research_file: str | None, preset: str, seconds: int | None, review: bool, instructions: str,
                         llm: str | None, model: str | None, tts: str | None, voice: str | None,
                         subtitles: bool | None, assets: list[str] | None, asset_rights: dict[str, Any] | None,
                         reference_video: str | None, content_format: str | None, allow_openai: bool | None,
                         benchmark: str | None, visuals: str | None, template: str | None, character: str | None,
                         pages: int | None, log: Log) -> dict[str, Any]:
    """카드뉴스 / 인스타툰 / 하이브리드 (all 이면 쇼츠 + 하이브리드). 결과는 output/<id>/<format>/card_NN.png."""
    fmt = output_format
    if fmt == "shorts":
        raise FactoryError("invalid", "기존 리서치 파일 입력(--research-file)은 카드뉴스/인스타툰/하이브리드에서만 씁니다.")
    if sum([bool(topic), bool(url), bool(auto), bool(script_text), bool(research_file), bool(reference_video)]) != 1:
        raise FactoryError("invalid", "topic / url / auto / script / research-file 중 하나만 지정해 주세요.")
    if reference_video:
        raise FactoryError("invalid", "참고 영상 파일 입력은 쇼츠에서만 지원합니다. 주제·링크·원고로 만들어 주세요.")
    if review:
        raise FactoryError("invalid", "카드뉴스·인스타툰은 대본 검토 단계 없이 바로 PNG 까지 만듭니다. --review 없이 실행해 주세요.")
    if fmt == "all" and research_file:
        raise FactoryError("invalid", "all 모드는 쇼츠 입력(topic/url/auto/script)으로 시작해 주세요.")
    if pages is not None and (isinstance(pages, bool) or not isinstance(pages, int) or not 6 <= pages <= 10):
        raise FactoryError("invalid", "페이지 수는 6~10 사이 정수여야 합니다.")
    if research_file and not Path(research_file).is_file():
        raise FactoryError("invalid", f"리서치 파일이 없습니다: {research_file}")
    if content_format and content_format not in FORMATS:
        raise FactoryError("invalid", "형식(톤)은 information / story / issue 중 하나여야 합니다.")
    if fmt == "all":
        try:
            benchmark = bench_auto.validate_choice(benchmark)
        except ValueError as e:
            raise FactoryError("invalid", str(e)) from e
    try:
        if template:
            load_template(template, "hybrid" if fmt == "all" else fmt)
        if character:
            charmod.get_character(character)
    except (KeyError, ValueError) as e:
        raise FactoryError("invalid", str(e).strip("'\""), templates=[t["id"] for t in list_templates()],
                           characters=[c.id for c in charmod.list_characters()]) from e
    if content_format:
        instructions = f"{FORMATS[content_format]['instructions']}\n{instructions}".strip()
    mode = ("topic" if topic else "url" if url else "auto" if auto else "research" if research_file else "script")
    text = topic or url or script_text or (str(Path(research_file).resolve()) if research_file else "")
    request = {"mode": mode, "input": text, "preset": preset, "seconds": seconds, "review": False,
               "instructions": instructions, "llm": llm, "model": model, "tts": tts, "voice": voice,
               "subtitles": subtitles, "allow_openai": allow_openai, "format": content_format,
               "output_format": fmt, "template": template, "character": character, "pages": pages,
               "benchmark": benchmark or "auto", "visuals": visuals or "auto", "reference_name": "", "style": None}
    run_cfg = _run_cfg(request)
    if fmt == "all":
        require_ffmpeg()
    project_id = _new_id()
    job_dir = output_root() / project_id
    state = st.save(job_dir, st.new(project_id, request))
    try:
        rights = _copy_assets(job_dir, assets, asset_rights, None, register=fmt != "all")
        state = st.save(job_dir, {**state, "asset_rights": rights})
    except Exception as e:  # noqa: BLE001
        return _fail(job_dir, state, e)
    progress = _progress(job_dir, state, log)
    kwargs = dict(cfg=run_cfg, progress=progress, template=template, character=character, n_pages=pages,
                  instructions=instructions, image_search=(visuals or "auto") == "auto")
    if fmt != "all":
        try:
            with _ai_session(job_dir, state, run_cfg):
                out = await carouselmod.run_carousel(job_dir, fmt=fmt, mode=mode, text=text, **kwargs)
            return _finish_carousel(job_dir, state, out)
        except Exception as e:  # noqa: BLE001
            return _fail(job_dir, state, e)

    # all: 쇼츠(기존 엔진 그대로) → 같은 조사·대본으로 하이브리드 캐러셀
    result: dict[str, Any] = {}
    try:
        with _ai_session(job_dir, state, run_cfg):
            result = await runmod.run_pipeline(
                job_dir, mode, text, run_cfg, progress=progress, review=None, until="done",
                instructions=instructions, style=None, upload_rights=state.get("asset_rights") or {},
                reference_name="", benchmark=benchmark, source_search=(visuals or "auto") == "auto")
        state["topic"] = result.get("topic", "")
        _record_benchmark(job_dir, state, result)
        shorts_summary = await _finish(job_dir, state, result)
    except Exception as e:  # noqa: BLE001 - 쇼츠가 실패해도 카드는 만든다
        shorts_summary = _fail(job_dir, state, e)
    state = st.load(job_dir)
    try:
        inputs = carouselmod.inputs_from_shorts(job_dir, result) if (job_dir / "script.json").is_file() else None
        with _ai_session(job_dir, state, run_cfg):
            out = await carouselmod.run_carousel(job_dir, fmt="hybrid", mode=mode, text=text, inputs=inputs, **kwargs)
        state = st.load(job_dir)
        st.save(job_dir, {**state, "carousel": _carousel_view(out),
                          "outputs": {**state.get("outputs", {}), "carousel_dir": out["dir"],
                                      "carousel_manifest": out["manifest"]}})
        carousel = {"status": "complete", **_carousel_view(out)}
    except Exception as e:  # noqa: BLE001
        carousel = {"status": "failed", "error": f"{type(e).__name__}: {llmmod.safe_error(e)}"}
        st.save(job_dir, {**st.load(job_dir), "carousel": carousel})
    shorts_ok = shorts_summary.get("status") == "render_complete"
    overall = ("render_complete" if shorts_ok and carousel["status"] == "complete" else
               "failed" if not shorts_ok and carousel["status"] != "complete" else "partial_failure")
    return {**shorts_summary, "status": overall, "output_format": "all",
            "shorts_status": shorts_summary.get("status"), "carousel": carousel}


async def make_planned_carousel(story, evidence, *, character_root=None, log: Log = print) -> dict[str, Any]:
    """Render an approved Topic Strategy bundle with the shared carousel engine; no research/planning calls."""
    from ..carousel.schema import MasterContent, CarouselPlan
    from ..pipeline.models import ResearchDoc
    from ..topics.store import write
    master = MasterContent.model_validate(story.master)
    plan = CarouselPlan.model_validate(story.carousel_plan)
    request = {'mode': 'topic_strategy', 'input': master.topic, 'preset': 'daily',
               'output_format': plan.format, 'review': False, 'instructions': story.dialogue_disclaimer,
               'llm': 'claude', 'allow_openai': False, 'visuals': 'cards'}
    cfg = _run_cfg(request)
    # Approved factual plan renders with our graphics; keys alone cannot trigger image API spending.
    cfg['carousel'] = {**cfg.get('carousel', {}), 'image_provider': 'none', 'image_search': False}
    job_dir = output_root() / _new_id()
    state = st.save(job_dir, st.new(job_dir.name, request))
    write(job_dir / 'topic_strategy.json', story.model_dump())
    registry = SourceRegistry(job_dir)
    docs = [ResearchDoc(title=e.title, url=e.url, text=e.text, published=e.published_at) for e in evidence]
    for e in evidence:
        registry.add(kind='article', origin='url', url=e.url, title=e.title, usage='research', used_for='script_research')
    try:
        out = await carouselmod.run_carousel(job_dir, fmt=plan.format, mode='topic_strategy', text=master.topic,
            cfg=cfg, progress=_progress(job_dir, state, log), character=story.character_id,
            inputs={'topic': master.topic, 'docs': docs}, image_search=False, character_root=character_root,
            prepared_master=master, prepared_plan=plan, instructions=story.dialogue_disclaimer)
        manifest = Path(out['manifest'])
        data = json.loads(manifest.read_text(encoding='utf-8'))
        data['topic_strategy'] = {'topic_id': story.topic_id, 'provenance': story.provenance,
                                  'dialogue_disclaimer': story.dialogue_disclaimer}
        write(manifest, data)
        caption = manifest.parent / 'caption.txt'
        with caption.open('a', encoding='utf-8') as f:
            f.write('\n' + story.dialogue_disclaimer + '\n')
        state['topic_strategy'] = {'topic_id': story.topic_id, 'provenance_file': str(job_dir / 'topic_strategy.json')}
        return _finish_carousel(job_dir, state, out)
    except Exception as exc:
        return _fail(job_dir, state, exc)


def _finish_carousel(job_dir: Path, state: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    pages = [Path(p) for p in out["pages"]]
    if not pages or not all(p.is_file() and p.stat().st_size for p in pages):
        raise RuntimeError("페이지 PNG 가 만들어지지 않았습니다.")
    outputs = {"carousel_dir": out["dir"], "carousel_manifest": out["manifest"],
               "sources": str(job_dir / "sources.json"), "master": str(job_dir / "master.json")}
    state = st.advance(job_dir, state, "render_complete", error="", failed_at="", outputs=outputs,
                       topic=out.get("topic", ""), carousel=_carousel_view(out))
    return _summary(job_dir, state, output_format=out["format"], **_carousel_view(out),
                    message=f"{out['format']} {len(pages)}장(1080x1350 PNG)을 만들었습니다.",
                    page_count=len(pages), resolution="1080x1350",
                    image_search_error=out.get("image_search_error", ""))


def _is_carousel(state: dict[str, Any]) -> bool:
    return (state.get("request") or {}).get("output_format") in CAROUSEL_FORMATS


async def resume(project_id: str | None = None, log: Log = print) -> dict[str, Any]:
    """승인된(또는 멈춘) 대본으로 이어서 장면·TTS·화면·자막·렌더를 한다. 조사·대본은 다시 하지 않는다."""
    if not project_id:
        pending = [p for p in _projects() if st.next_action(st.load(p), p) == "resume" and not _is_carousel(st.load(p))]
        if pending:
            project_id = pending[0].name
    job_dir = project_dir(project_id)
    state = st.load(job_dir)
    status = state.get("status")
    if _is_carousel(state):
        raise FactoryError("not_ready", "카드뉴스·인스타툰 프로젝트는 이어서 만들 단계가 없습니다. make 로 다시 만들어 주세요.")
    if status == "render_complete":
        raise FactoryError("not_ready", "이미 완성된 영상입니다. 다시 만들려면 rerender 를 쓰세요.",
                           final_video=state.get("outputs", {}).get("final_video", ""))
    can = status in st.AFTER_SCRIPT or (status == "failed" and state.get("failed_at") in st.AFTER_SCRIPT)
    if not can or not (job_dir / "script.json").is_file():
        raise FactoryError("not_ready", "이어서 만들 대본이 없습니다. make 로 새로 만들어 주세요.", status=status)
    script = PlannedScript.model_validate_json((job_dir / "script.json").read_text(encoding="utf-8"))
    req = state["request"]
    run_cfg = _run_cfg(req)
    require_ffmpeg()
    state = st.save(job_dir, {**state, "status": "script_approved", "error": "", "failed_at": "",
                              "history": [*state.get("history", []), {"status": "script_approved", "at": st.now()}]})
    try:
        with _ai_session(job_dir, state, run_cfg):
            result = await runmod.run_pipeline(
                job_dir, "resume", "", run_cfg, progress=_progress(job_dir, state, log), review=None,
                instructions=req.get("instructions", ""), style=find_style(req.get("style")),
                upload_rights=state.get("asset_rights") or {}, script_in=script,
                reference_name=req.get("reference_name", ""), source_search=req.get("visuals") == "auto")
        _record_benchmark(job_dir, state, result)
        return await _finish(job_dir, state, result)
    except Exception as e:  # noqa: BLE001
        return _fail(job_dir, state, e)


def status(project_id: str | None = None) -> dict[str, Any]:
    job_dir = project_dir(project_id)
    state = st.load(job_dir)
    out = _summary(job_dir, state, topic=state.get("topic") or state["request"].get("input", "")[:60],
                   request=state["request"], history=state.get("history", [])[-8:], ai_calls=state.get("ai_calls", []))
    out.setdefault("benchmark", {"mode": "off"})   # 통합 이전 프로젝트는 구조 선택 없이 만들어졌다
    if state.get("status") == "render_complete":
        out.update(final_video=state["outputs"].get("final_video", ""), **state.get("video", {}))
    if not project_id:
        out["recent_projects"] = [{"project_id": d.name, "status": st.load(d).get("status"),
                                   "topic": st.load(d).get("topic", "")} for d in _projects()[:5]]
    return out


def inspect(project_id: str | None = None, part: str = "all") -> dict[str, Any]:
    """대본 / 장면 시간 / 화면 결정 / 파일을 보여준다."""
    job_dir = project_dir(project_id)
    state = st.load(job_dir)
    out = _summary(job_dir, state)
    if part in ("all", "script") and (job_dir / "script.json").is_file() and not _is_carousel(state):
        out["script"] = _script_view(job_dir)
    if part in ("all", "scenes", "visuals") and (job_dir / bpmod.FILE).is_file() and not _is_carousel(state):
        bp = bpmod.load(job_dir)
        out["timing"] = bp.timing
        out["scenes"] = [{
            "scene": s.index + 1, "role": s.scene_type, "narration": s.narration, "emphasis": s.emphasis_text,
            "estimated": s.estimated_duration, "actual_tts": s.actual_tts_duration,
            "start": s.timeline_start, "end": s.timeline_end,
            **({"visual": s.visual_decision.resolved_visual_type, "visual_source": s.visual_decision.asset_source,
                "rights": s.visual_decision.rights_status, "reason": s.visual_decision.selection_reason,
                "fallback": s.visual_decision.fallback_used, "asset": s.visual_decision.asset_path}
               if s.visual_decision and part != "scenes" else {})} for s in bp.scenes]
    if part in ("all", "carousel") and (state.get("outputs") or {}).get("carousel_manifest"):
        path = Path(state["outputs"]["carousel_manifest"])
        if path.is_file():
            m = json.loads(path.read_text(encoding="utf-8"))
            out["carousel"] = {k: m.get(k) for k in ("format", "template", "size", "page_count", "mix", "plan_method",
                                                     "fallback_pages", "image_credits")}
            out["carousel"]["pages"] = [{**{k: r.get(k) for k in ("page", "file", "type", "headline", "layout",
                                                                  "characters", "fallback_used")},
                                         "image": bool(r.get("image"))} for r in m.get("pages", [])]
    if part in ("all", "benchmark") and not _is_carousel(state):
        out["benchmark"] = bench_auto.load_decision(job_dir) or state.get("benchmark") or {"mode": "off"}
    if part in ("all", "files"):
        out["files"] = {p.name: str(p) for p in sorted(job_dir.iterdir()) if p.is_file()}
    return out


def edit_scene(project_id: str | None, scene: int, *, narration: str | None = None,
               emphasis: str | None = None) -> dict[str, Any]:
    """렌더 전 대본 장면 수정 ("3번 장면 문장 바꿔줘"). 수정 후 resume 하면 반영된다."""
    job_dir = project_dir(project_id)
    state = st.load(job_dir)
    if state.get("status") not in ("waiting_for_script_approval", "script_ready") and not (
            state.get("status") == "failed" and state.get("failed_at") in st.AFTER_SCRIPT):
        raise FactoryError("not_ready", "대본 수정은 렌더 전(대본 승인 대기)에만 할 수 있습니다.", status=state.get("status"))
    data = json.loads((job_dir / "script.json").read_text(encoding="utf-8"))
    if not 1 <= scene <= len(data["scenes"]):
        raise FactoryError("invalid", f"장면 번호는 1~{len(data['scenes'])} 사이여야 합니다.")
    s = data["scenes"][scene - 1]
    if narration is not None:
        if not narration.strip():
            raise FactoryError("invalid", "내레이션이 비어 있습니다.")
        s["narration"] = s["subtitle"] = " ".join(narration.split())
    if emphasis is not None:
        s["on_screen_text"] = " ".join(emphasis.split())[:EMPHASIS_MAX + 2]
    PlannedScript.model_validate(data)
    (job_dir / "script.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return _summary(job_dir, state, **_script_view(job_dir))


def _own_rights(license_: str, note: str, confirmed: bool) -> dict[str, Any]:
    return {"license": license_, "license_note": note, "rights_confirmed": confirmed, "commercial_allowed": confirmed,
            "adaptation_allowed": confirmed, "third_party_rights_checked": confirmed}


async def set_visual(project_id: str | None, scene: int, *, card: str | None = None, file: str | None = None,
                     license_: str = "my_channel", note: str = "", confirm_rights: bool = False,
                     log: Log = print) -> dict[str, Any]:
    """장면 화면 바꾸기 ("3번 장면 화면 바꿔줘").

    - 렌더 전: 권리 확인한 파일을 그 장면 지정 파일로 넣는다 (resume 때 자동 선택기가 1순위로 쓴다).
    - 렌더 후: 파일 또는 카드 종류로 그 장면 화면을 바꾸고 다시 렌더한다 (음성·시간은 그대로).
    권리 확인이 안 된 파일은 쓰지 않는다.
    """
    if bool(card) == bool(file):
        raise FactoryError("invalid", "card 또는 file 중 하나만 지정해 주세요.", cards=list(CARD_CHOICES))
    if card and card not in CARD_CHOICES:
        raise FactoryError("invalid", f"카드 종류: {', '.join(CARD_CHOICES)}")
    job_dir = project_dir(project_id)
    state = st.load(job_dir)
    rendered = state.get("status") == "render_complete"
    script = PlannedScript.model_validate_json((job_dir / "script.json").read_text(encoding="utf-8"))
    if not 1 <= scene <= len(script.scenes):
        raise FactoryError("invalid", f"장면 번호는 1~{len(script.scenes)} 사이여야 합니다.")
    i = scene - 1
    registry = SourceRegistry(job_dir)
    upload = None
    if file:
        src = Path(file)
        if not src.is_file() or kind_of(src) != "image":
            raise FactoryError("invalid", "이미지 파일만 장면 화면으로 바꿀 수 있습니다.")
        upload = job_dir / "uploads" / f"scene_{i:02d}_{src.name}"
        upload.parent.mkdir(parents=True, exist_ok=True)
        for old in upload.parent.glob(f"scene_{i:02d}_*"):
            old.unlink()
        shutil.copyfile(src, upload)
        rights = _own_rights(license_, note, confirm_rights)
        item = registry.add(kind="image", origin="upload", path=str(upload), title=src.name, rights=rights,
                            used_for=f"scene_{i:02d}")
        if not item.usable_in_video:
            upload.unlink(missing_ok=True)
            registry.remove_path(upload)
            raise FactoryError("rights", "권리가 확인되지 않아 이 파일은 영상에 쓸 수 없습니다. "
                               "직접 만든 자료라면 --license 와 --note(근거), --confirm-rights 를 함께 주세요.")
        state = st.save(job_dir, {**state, "asset_rights": {**state.get("asset_rights", {}), upload.name: rights}})
    if not rendered:
        if card:
            raise FactoryError("not_ready", "카드 교체는 렌더 후에 할 수 있습니다. 파일로 바꾸거나 resume 후 다시 시도하세요.")
        return _summary(job_dir, state, changed_scene=scene, note="resume 하면 이 파일이 그 장면에 우선 쓰입니다.")

    # 렌더 후: 장면 이미지 교체 → 기록 갱신 → 다시 렌더
    cfg = _run_cfg(state["request"])
    bp = bpmod.load(job_dir)
    s = script.scenes[i]
    out = job_dir / "scenes" / f"scene_{i:02d}.jpg"
    if upload:
        shutil.copyfile(upload, out)
        how = cards.fit_image(out, int(cfg["images"]["width"]), int(cfg["images"]["height"]))
        parent = registry.by_path(upload)
        registry.add(kind="image", origin="derived", path=str(out), title=f"장면 {scene}",
                     rights=parent.model_dump() if parent else None, parent_id=parent.id if parent else "",
                     used_for=f"scene_{i:02d}")
        decision = VisualDecision(scene_id=f"scene_{scene:02d}", requested_visual_type=s.visual_type,
                                  resolved_visual_type="upload_image", asset_path=str(out), asset_source="user_upload",
                                  rights_reason=f"권리 확인된 업로드 ({license_})",
                                  selection_reason=f"사용자 요청으로 교체 ({'가운데 맞춤' if how == 'cover' else '흐린 배경 위 원본 전체'})")
    else:
        cards.render_card(card, out, width=int(cfg["images"]["width"]), height=int(cfg["images"]["height"]),
                          emphasis=s.on_screen_text, key_number=s.key_number, compare_a=s.compare_a,
                          compare_b=s.compare_b, trend_up=trend_direction(s.narration) != "down", seed=s.narration[:40])
        registry.add(kind="image", origin="generated", path=str(out), title=f"장면 {scene}", used_for=f"scene_{i:02d}")
        decision = VisualDecision(scene_id=f"scene_{scene:02d}", requested_visual_type=s.visual_type,
                                  resolved_visual_type=card, asset_path=str(out), asset_source="internal_generated",
                                  rights_reason="앱이 직접 그린 카드라 사용권 문제가 없음",
                                  selection_reason="사용자 요청으로 카드 교체", show_title=False)
    bp.scenes[i].visual_decision = decision
    bpmod.save(job_dir, bp)
    visualsmod.save_manifest(job_dir, [x.visual_decision for x in bp.scenes if x.visual_decision])
    tl = tlmod.load(job_dir)
    tl["scenes"][i]["visual"] = {**tl["scenes"][i]["visual"], "kind": "image", "path": tlmod.rel(out, job_dir)}
    tl["scenes"][i]["title"] = s.on_screen_text if decision.show_title else ""
    tlmod.save(job_dir, tl)
    return await rerender(state["project_id"], log=log, changed_scene=scene)


async def rerender(project_id: str | None = None, log: Log = print, **extra: Any) -> dict[str, Any]:
    """저장된 렌더 재료(timeline.json)로 영상만 다시 만든다. 조사·대본·음성은 다시 하지 않는다."""
    job_dir = project_dir(project_id)
    state = st.load(job_dir)
    if not (job_dir / tlmod.FILE).is_file():
        raise FactoryError("not_ready", "다시 렌더할 재료가 없습니다. 먼저 영상을 완성해 주세요.", status=state.get("status"))
    cfg = _run_cfg(state["request"])
    try:
        res = await runmod.rerender(job_dir, cfg, progress=lambda stage, pct, msg: log(f"[{stage} {pct:3d}%] {msg}"))
    except Exception as e:  # noqa: BLE001 - 실패해도 기존 final.mp4 는 남는다
        return _summary(job_dir, state, rerender="failed", error=f"{type(e).__name__}: {llmmod.safe_error(e)}",
                        message="다시 렌더에 실패했습니다. 기존 영상은 그대로 있습니다.")
    result = {"video": res["video"], "topic": state.get("topic", ""), "timeline": tlmod.FILE}
    return {**await _finish(job_dir, state, result), "rerendered": True, **extra}


def styles() -> dict[str, Any]:
    cfg = _cfg()
    return {"status": "ok",
            "formats": [{"id": k, "name": v["name"]} for k, v in FORMATS.items()],
            "output_formats": list(OUTPUT_FORMATS),
            "carousel_templates": list_templates(),
            "characters": [{"id": c.id, "name": c.name, "role": c.role} for c in charmod.list_characters()],
            "presets": [{"id": k, "name": v.get("name", k), "description": v.get("description", "")}
                        for k, v in load_presets(cfg).items()],
            "styles": [{"id": s["id"], "name": s.get("name", ""), "hook": str(s.get("hook_pattern", ""))[:80]}
                       for s in load_styles(cfg).values()],
            "message": "make 에 --preset(분야 기본값)과 --style(참고 영상 스타일 id 또는 이름)로 지정합니다."}


async def trends(limit: int = 10, log: Log = print) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise FactoryError("invalid", "후보 수는 1~50 사이 정수여야 합니다.")
    kws = await research.hot_keywords(log=log)
    kws = list(dict.fromkeys(k.strip() for k in kws if k.strip()))[:limit]
    if not kws:
        raise FactoryError("not_found", "화제 소재를 가져오지 못했습니다. 나중에 다시 찾거나 주제를 직접 입력해 주세요.")
    from .batch import save_candidates
    saved = save_candidates(output_root(), kws)
    return {"status": "ok", "keywords": kws, **saved,
            "message": "번호를 골라 batch --select 2 4로 순차 제작할 수 있습니다. 후보 id도 함께 지정하면 다른 검색과 섞이지 않습니다."}


async def export(project_id: str | None = None, *, pack: bool = False, capcut_draft: bool = False,
                 log: Log = print) -> dict[str, Any]:
    """완성 파일 목록. pack=True 면 재료 묶음 zip, capcut_draft=True 면 CapCut 프로젝트도 만든다."""
    job_dir = project_dir(project_id)
    state = st.load(job_dir)
    if _is_carousel(state):
        if pack or capcut_draft:
            raise FactoryError("invalid", "카드뉴스·인스타툰은 편집 재료 zip·CapCut 내보내기가 없습니다. PNG 폴더를 그대로 쓰세요.")
        return _summary(job_dir, state, files=state.get("outputs", {}), **(state.get("carousel") or {}))
    if state.get("status") != "render_complete":
        raise FactoryError("not_ready", "완성된 영상이 아직 없습니다.", status=state.get("status"))
    out = _summary(job_dir, state, files=state.get("outputs", {}))
    tl = tlmod.load(job_dir)
    if pack:
        out["pack"] = str(await capcut.export_pack(tl, job_dir, job_dir / "capcut_pack.zip"))
    if capcut_draft:
        root = capcut.find_drafts_root(_cfg())
        if not root:
            raise FactoryError("not_found", "CapCut 프로젝트 폴더를 찾지 못했습니다.")
        out["capcut_draft"] = str(await capcut.export_draft(tl, job_dir, root, state.get("topic") or state["project_id"]))
    return out
