"""프로젝트 상태 파일 (output/<project_id>/project_state.json).

Claude Code / Codex 가 "어디까지 됐어?", "계속해" 를 처리할 때 이 파일 하나만 보면 된다.
상태 순서:
  created → researching → research_complete → script_ready → waiting_for_script_approval
  → script_approved → blueprint_complete → tts_complete → visuals_complete → rendering → render_complete
  (어느 단계에서든) → failed
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

FILE = "project_state.json"
ORDER = ("created", "researching", "research_complete", "script_ready", "waiting_for_script_approval",
         "script_approved", "blueprint_complete", "tts_complete", "visuals_complete", "rendering", "render_complete")
TERMINAL = ("render_complete", "failed")
# 대본이 이미 저장된 뒤의 상태 — 여기서 실패했거나 멈췄으면 조사·대본을 다시 하지 않고 resume 할 수 있다
AFTER_SCRIPT = ORDER[ORDER.index("script_ready"):]

NEXT_ACTION = {
    "waiting_for_script_approval": "resume",
    "script_ready": "resume",
    "script_approved": "resume",
    "render_complete": "done",
}
MESSAGE = {
    "created": "작업을 만들었습니다.",
    "researching": "자료를 조사하는 중입니다.",
    "research_complete": "자료 조사를 마쳤습니다.",
    "script_ready": "대본을 만들었습니다.",
    "waiting_for_script_approval": "대본을 검토한 뒤 resume 하면 이어서 영상을 만듭니다.",
    "script_approved": "승인된 대본으로 영상을 만들고 있습니다.",
    "blueprint_complete": "장면 설계를 마쳤습니다.",
    "tts_complete": "음성을 만들고 실제 길이로 장면 시간을 확정했습니다.",
    "visuals_complete": "장면별 화면을 정했습니다.",
    "rendering": "영상을 렌더링하는 중입니다.",
    "render_complete": "완성 영상을 만들었습니다.",
    "failed": "작업이 실패했습니다.",
}


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def load(job_dir: Path) -> dict[str, Any]:
    return json.loads((job_dir / FILE).read_text(encoding="utf-8"))


def exists(job_dir: Path) -> bool:
    return (job_dir / FILE).is_file()


def save(job_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    job_dir.mkdir(parents=True, exist_ok=True)
    state["updated"] = now()
    tmp = job_dir / (FILE + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(job_dir / FILE)
    return state


def new(project_id: str, request: dict[str, Any]) -> dict[str, Any]:
    return {"project_id": project_id, "status": "created", "request": request, "created": now(), "updated": now(),
            "error": "", "failed_at": "", "history": [{"status": "created", "at": now()}], "outputs": {},
            "ai_provider_used": "none", "ai_providers_used": [], "ai_calls": []}


def advance(job_dir: Path, state: dict[str, Any], status: str, **extra: Any) -> dict[str, Any]:
    """상태를 앞으로만 옮긴다 (failed 는 언제든). 같은 상태 반복 기록은 하지 않는다."""
    if status != state.get("status"):
        if status in ORDER and state.get("status") in ORDER and ORDER.index(status) < ORDER.index(state["status"]):
            return state   # 진행 중 로그가 뒤늦게 와도 상태를 되돌리지 않는다
        state["status"] = status
        state.setdefault("history", []).append({"status": status, "at": now()})
    state.update(extra)
    return save(job_dir, state)


def next_action(state: dict[str, Any], job_dir: Path) -> str:
    status = state.get("status", "")
    if status == "failed":
        return "resume" if state.get("failed_at") in AFTER_SCRIPT and (job_dir / "script.json").is_file() else "make"
    return NEXT_ACTION.get(status, "status")
