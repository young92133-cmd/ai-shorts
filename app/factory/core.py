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

from ..config import load_config, load_presets, merge_options
from ..pipeline import blueprint as bpmod, capcut, cards, research, timeline as tlmod, visuals as visualsmod
from ..pipeline import run as runmod
from ..pipeline.assets import kind_of
from ..pipeline.media import probe_video, require_ffmpeg
from ..pipeline.models import PlannedScript, VisualDecision
from ..pipeline.script_split import EMPHASIS_MAX, trend_direction
from ..pipeline.sources import SourceRegistry
from ..pipeline.styles import load_styles, nfc
from . import state as st

Log = Callable[[str], None]
PID_RE = re.compile(r"^[A-Za-z0-9_-]{3,80}$")
CARD_CHOICES = tuple(k for k in cards.CARD_KINDS if k != "safe_card")


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
    return merge_options(cfg, presets[preset], overrides)


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
    if status == "failed":
        out["failed_at"] = state.get("failed_at", "")
    out.update(extra)
    return out


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
    info = await probe_video(final)
    stream = (info.get("streams") or [{}])[0]
    duration = round(float((info.get("format") or {}).get("duration") or 0), 2)
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
            "final_sources", "plan_method", "split_method")
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
    state = st.advance(job_dir, state, "failed", error=f"{type(e).__name__}: {e}", failed_at=at)
    return _summary(job_dir, state)


# ---------- 명령 ----------

async def make(*, topic: str | None = None, url: str | None = None, auto: bool = False, script_text: str | None = None,
               preset: str = "daily", style: str | None = None, seconds: int | None = None, review: bool = False,
               instructions: str = "", llm: str | None = None, model: str | None = None, tts: str | None = None,
               voice: str | None = None, subtitles: bool | None = None, assets: list[str] | None = None,
               asset_rights: dict[str, Any] | None = None, log: Log = print) -> dict[str, Any]:
    """쇼츠 한 편을 만든다. review=True 면 대본까지만 만들고 승인 대기로 멈춘다."""
    modes = [bool(topic), bool(url), bool(auto), bool(script_text)]
    if sum(modes) != 1:
        raise FactoryError("invalid", "topic / url / auto / script 중 하나만 지정해 주세요.")
    mode = "topic" if topic else "url" if url else "auto" if auto else "script"
    text = topic or url or script_text or ""
    style_data = find_style(style)
    request = {"mode": mode, "input": text, "preset": preset, "style": style_data["id"] if style_data else None,
               "seconds": seconds, "review": review, "instructions": instructions, "llm": llm, "model": model,
               "tts": tts, "voice": voice, "subtitles": subtitles}
    run_cfg = _run_cfg(request)
    require_ffmpeg()
    project_id = _new_id()
    job_dir = output_root() / project_id
    state = st.save(job_dir, st.new(project_id, request))
    rights: dict[str, Any] = {}
    for path in assets or []:
        src = Path(path)
        if not src.is_file() or not kind_of(src):
            return _fail(job_dir, state, FactoryError("invalid", f"첨부 파일을 쓸 수 없습니다: {path}"))
        (job_dir / "uploads").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, job_dir / "uploads" / src.name)
        rights[src.name] = asset_rights or {}
    state = st.save(job_dir, {**state, "asset_rights": rights})
    try:
        result = await runmod.run_pipeline(
            job_dir, mode, text, run_cfg, progress=_progress(job_dir, state, log), review=None,
            until="script" if review else "done", instructions=instructions, style=style_data,
            upload_rights=rights)
    except Exception as e:  # noqa: BLE001 - 실패도 상태 파일에 남기고 JSON 으로 알린다
        return _fail(job_dir, state, e)
    state["topic"] = result.get("topic", "")
    if review:
        state = st.advance(job_dir, state, "waiting_for_script_approval", topic=state["topic"])
        return _summary(job_dir, state, **_script_view(job_dir))
    return await _finish(job_dir, state, result)


async def resume(project_id: str | None = None, log: Log = print) -> dict[str, Any]:
    """승인된(또는 멈춘) 대본으로 이어서 장면·TTS·화면·자막·렌더를 한다. 조사·대본은 다시 하지 않는다."""
    job_dir = project_dir(project_id)
    state = st.load(job_dir)
    status = state.get("status")
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
        result = await runmod.run_pipeline(
            job_dir, "resume", "", run_cfg, progress=_progress(job_dir, state, log), review=None,
            instructions=req.get("instructions", ""), style=find_style(req.get("style")),
            upload_rights=state.get("asset_rights") or {}, script_in=script)
    except Exception as e:  # noqa: BLE001
        return _fail(job_dir, state, e)
    return await _finish(job_dir, state, result)


def status(project_id: str | None = None) -> dict[str, Any]:
    job_dir = project_dir(project_id)
    state = st.load(job_dir)
    out = _summary(job_dir, state, topic=state.get("topic") or state["request"].get("input", "")[:60],
                   request=state["request"], history=state.get("history", [])[-8:])
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
    if part in ("all", "script") and (job_dir / "script.json").is_file():
        out["script"] = _script_view(job_dir)
    if part in ("all", "scenes", "visuals") and (job_dir / bpmod.FILE).is_file():
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
        return _summary(job_dir, state, rerender="failed", error=f"{type(e).__name__}: {e}",
                        message="다시 렌더에 실패했습니다. 기존 영상은 그대로 있습니다.")
    result = {"video": res["video"], "topic": state.get("topic", ""), "timeline": tlmod.FILE}
    return {**await _finish(job_dir, state, result), "rerendered": True, **extra}


def styles() -> dict[str, Any]:
    cfg = _cfg()
    return {"status": "ok",
            "presets": [{"id": k, "name": v.get("name", k), "description": v.get("description", "")}
                        for k, v in load_presets(cfg).items()],
            "styles": [{"id": s["id"], "name": s.get("name", ""), "hook": str(s.get("hook_pattern", ""))[:80]}
                       for s in load_styles(cfg).values()],
            "message": "make 에 --preset(분야 기본값)과 --style(참고 영상 스타일 id 또는 이름)로 지정합니다."}


async def trends(limit: int = 10, log: Log = print) -> dict[str, Any]:
    kws = await research.hot_keywords(log=log)
    return {"status": "ok", "keywords": kws[:limit],
            "message": "마음에 드는 키워드로 make --topic 을 실행하거나, make --auto 로 AI 가 고르게 할 수 있습니다."}


async def export(project_id: str | None = None, *, pack: bool = False, capcut_draft: bool = False,
                 log: Log = print) -> dict[str, Any]:
    """완성 파일 목록. pack=True 면 재료 묶음 zip, capcut_draft=True 면 CapCut 프로젝트도 만든다."""
    job_dir = project_dir(project_id)
    state = st.load(job_dir)
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
