"""화제 후보를 저장하고 여러 편을 기존 Factory로 한 편씩 만든다."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import core, state as st
from ..pipeline.llm import safe_error


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def save_candidates(root: Path, keywords: list[str]) -> dict:
    cid = "trends_" + core._new_id()
    data = {"candidates_id": cid, "created": st.now(),
            "candidates": [{"number": i + 1, "topic": topic} for i, topic in enumerate(keywords)]}
    base = root / "_factory"
    _write(base / (cid + ".json"), data)
    _write(base / "latest_trends.json", {"candidates_id": cid})
    return data


def load_candidates(candidates_id: str | None = None) -> dict:
    base = core.output_root() / "_factory"
    if not candidates_id:
        latest = base / "latest_trends.json"
        if not latest.is_file():
            raise core.FactoryError("not_found", "먼저 trends로 화제 후보를 찾아 주세요.")
        candidates_id = json.loads(latest.read_text(encoding="utf-8"))["candidates_id"]
    if not core.PID_RE.fullmatch(candidates_id) or not candidates_id.startswith("trends_"):
        raise core.FactoryError("invalid", "후보 id 형식이 올바르지 않습니다.")
    path = base / (candidates_id + ".json")
    if not path.is_file():
        raise core.FactoryError("not_found", "저장된 화제 후보를 찾지 못했습니다.")
    return json.loads(path.read_text(encoding="utf-8"))


def _path(batch_id: str | None) -> Path:
    base = core.output_root() / "_factory"
    if not batch_id:
        files = sorted(base.glob("batch_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            raise core.FactoryError("not_found", "순차 제작 기록이 없습니다.")
        return files[0]
    if not core.PID_RE.fullmatch(batch_id) or not batch_id.startswith("batch_"):
        raise core.FactoryError("invalid", "순차 제작 id 형식이 올바르지 않습니다.")
    path = base / (batch_id + ".json")
    if not path.is_file():
        raise core.FactoryError("not_found", "순차 제작 기록을 찾지 못했습니다.")
    return path


def _summarize(data: dict) -> dict:
    statuses = [item["result"].get("status") for item in data["items"]]
    done = statuses.count("render_complete")
    failed = sum(s in ("failed", "error") for s in statuses)
    waiting = statuses.count("waiting_for_script_approval")
    data.update(completed=done, failed=failed, waiting=waiting, updated=st.now())
    data["status"] = ("running" if any(s in ("queued", "running") for s in statuses)
                      else "partial_failure" if failed else "waiting_for_script_approval" if waiting
                      else "completed" if done == len(statuses) else "running")
    return data


def status(batch_id: str | None = None) -> dict:
    return json.loads(_path(batch_id).read_text(encoding="utf-8"))


async def make(*, topics: list[str] | None = None, select: list[int] | None = None,
               candidates_id: str | None = None, count: int = 1, log=print, **options: Any) -> dict:
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10:
        raise core.FactoryError("invalid", "편수는 1~10 사이 정수여야 합니다.")
    if bool(topics) == bool(select):
        raise core.FactoryError("invalid", "주제 목록 또는 화제 후보 번호 중 하나를 지정해 주세요.")
    if select:
        if len(set(select)) != len(select):
            raise core.FactoryError("invalid", "후보 번호가 중복됐습니다.")
        candidates = load_candidates(candidates_id)
        lookup = {c["number"]: c["topic"] for c in candidates["candidates"]}
        if any(isinstance(n, bool) or not isinstance(n, int) or n not in lookup for n in select):
            raise core.FactoryError("invalid", "후보 목록에 있는 번호를 골라 주세요.")
        topics = [lookup[n] for n in select]
        candidates_id = candidates["candidates_id"]
    if not topics or any(not isinstance(t, str) or not t.strip() for t in topics) or len(topics) * count > 10:
        raise core.FactoryError("invalid", "빈 주제 없이 한 번에 최대 10편까지 지정해 주세요.")
    entries = [topic.strip() for topic in topics for _ in range(count)]
    bid = "batch_" + core._new_id()
    path = core.output_root() / "_factory" / (bid + ".json")
    data = {"batch_id": bid, "status": "running", "created": st.now(), "candidates_id": candidates_id,
            "items": [{"number": i + 1, "topic": topic, "result": {"status": "queued"}}
                      for i, topic in enumerate(entries)]}
    _write(path, data)
    for item in data["items"]:
        item["result"] = {"status": "running"}
        _write(path, data)
        log(f"[{item['number']}/{len(entries)}] 순차 제작: {item['topic']}")
        request = dict(options)
        if count > 1:
            request["instructions"] = (request.get("instructions", "") +
                f"\n같은 주제의 {count}편 시리즈 중 {(item['number'] - 1) % count + 1}편입니다. 편마다 다른 질문과 관점으로 구성하세요.").strip()
        try:
            item["result"] = await core.make(topic=item["topic"], log=log, **request)
        except Exception as exc:
            item["result"] = {"status": "error", "message": safe_error(exc)}
        _write(path, _summarize(data))
    return _summarize(data)


async def resume(batch_id: str | None = None, log=print) -> dict:
    path = _path(batch_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data["items"]:
        result = item["result"]
        if result.get("status") == "render_complete" or result.get("next_action") != "resume":
            continue
        try:
            item["result"] = await core.resume(result["project_id"], log=log)
        except Exception as exc:
            item["result"] = {**result, "status": "error", "message": safe_error(exc)}
        _write(path, _summarize(data))
    return _summarize(data)
