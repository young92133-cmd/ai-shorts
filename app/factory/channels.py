"""경쟁 채널 벤치마킹 명령: 분석(캐시) · 추천 주제 · 여러 채널 비교 · 패턴을 적용한 쇼츠 제작.

결과는 output/_factory/channels/<채널 id>/ 에 저장하고, 새 데이터가 필요할 때(--refresh 또는 기한 초과)만 다시 수집한다.
제작은 기존 core.make / batch 를 그대로 쓴다.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from . import core, batch, state as st
from ..pipeline import channels as ch, comments, llm as llmmod
from ..pipeline.llm import safe_error

MAX_AGE_DAYS = 3


def _root() -> Path:
    return core.output_root() / "_factory" / "channels"


def _read(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _key(text: str) -> str:
    return hashlib.sha1(ch.channel_url(text).lower().encode()).hexdigest()[:12]


def _dir(channel_id: str) -> Path:
    if not core.PID_RE.fullmatch(channel_id or ""):
        raise core.FactoryError("invalid", "채널 id 형식이 올바르지 않습니다.")
    d = _root() / channel_id
    if not (d / "scan.json").is_file():
        raise core.FactoryError("not_found", "분석한 채널이 없습니다. 먼저 channel analyze 로 분석해 주세요.")
    return d


def _resolve(ref: str) -> str:
    """채널 id · @핸들 · URL → 저장된 채널 id."""
    if core.PID_RE.fullmatch(ref or "") and (_root() / ref / "scan.json").is_file():
        return ref
    try:
        alias = (_read(_root() / "index.json", {}) or {}).get(_key(ref))
    except ValueError as e:
        raise core.FactoryError("invalid", str(e)) from e
    if not alias:
        raise core.FactoryError("not_found", "분석한 채널이 없습니다. 먼저 channel analyze 로 분석해 주세요.")
    return alias


def _fresh(scan: dict | None, max_age_days: float) -> bool:
    if not scan:
        return False
    age = dt.datetime.now(ch.KST) - dt.datetime.fromisoformat(scan["scanned_at"])
    return age.total_seconds() < max_age_days * 86400


def _llm_cfg() -> dict:
    return {**core._cfg()["llm"], "allow_paid_openai": False, "allow_paid_anthropic": False}


async def analyze(channel: str, *, refresh: bool = False, ai: bool = True, latest: int = 30, popular: int = 15,
                  max_age_days: float = MAX_AGE_DAYS, log=print) -> dict:
    try:
        key = _key(channel)
    except ValueError as e:
        raise core.FactoryError("invalid", str(e)) from e
    index = _read(_root() / "index.json", {}) or {}
    cid = index.get(key)
    d = _root() / cid if cid else None
    scan = _read(d / "scan.json") if d else None
    reused = _fresh(scan, max_age_days) and not refresh
    if not reused:
        try:
            new = await ch.scan(channel, latest=latest, popular=popular, log=log)
        except ValueError as e:
            raise core.FactoryError("not_found", str(e)) from e
        except Exception as e:
            raise core.FactoryError("network", "채널 정보를 가져오지 못했습니다: " + safe_error(e)) from e
        cid = "ch_" + (new["channel"]["id"] or key)[-22:].replace("-", "_")
        d = _root() / cid
        new = ch.metrics(new, previous=scan)
        await ch.add_transcripts(new, d / "transcripts", log=log)
        new["coverage"]["comments"] = 0
        top = [f"https://www.youtube.com/watch?v={v['id']}" for v in ch.standouts(new, 3)]
        texts = [c["text"] for c in await comments.fetch_candidates(top, limit=20, log=log)]
        new["coverage"]["comments"] = len(texts)
        new["comment_texts"] = texts
        new["channel_id"] = cid
        batch._write(d / "scan.json", new)
        index[key] = cid
        batch._write(_root() / "index.json", index)
        scan = new
    analysis = _read(d / "analysis.json")
    fingerprint = hashlib.sha1(json.dumps([(v["id"], v["views"]) for v in scan["videos"]]).encode()).hexdigest()
    if ai and (not analysis or analysis.get("scan_fingerprint") != fingerprint):
        calls: list[dict] = []
        integ = core.bench_auto.load_integration()   # 주제만으로 만들 수 있는 구조만 (권리 확인 영상이 필요한 구조 제외)
        profiles = [p for p in core.bench_auto.profile_ids(integ) if not integ["profiles"][p].get("requires_licensed_video")]
        try:
            with llmmod.provider_session(_llm_cfg(), lambda e: calls.append({**e, "at": st.now()})):
                analysis = await ch.analyze(_llm_cfg(), scan, profiles, scan.get("comment_texts"))
        except Exception as e:
            raise core.FactoryError("ai_failed", "패턴 분석 AI 호출 실패: " + safe_error(e) +
                                    " — Claude 구독 로그인(claude-login.cmd)을 확인하거나 --no-ai 로 지표만 보세요.",
                                    channel_id=cid, ai_calls=calls) from e
        analysis.update(channel_id=cid, channel_name=scan["channel"]["name"], scan_fingerprint=fingerprint,
                        created=st.now(), ai_calls=calls, model=_llm_cfg().get("model"))
        batch._write(d / "analysis.json", analysis)
    return {"status": "ok", "channel_id": cid, "reused_cache": reused, **summary(scan, analysis)}


def summary(scan: dict, analysis: dict | None) -> dict:
    top = sorted(scan["videos"], key=lambda v: v.get("age_adjusted", 0), reverse=True)[:8]
    out = {"channel": scan["channel"], "source": scan["source"], "scanned_at": scan["scanned_at"],
           "coverage": scan["coverage"], "stats": scan["stats"],
           "top_videos": [{k: v.get(k) for k in ("id", "title", "views", "age_days", "views_per_day", "age_adjusted",
                                                  "duration", "groups", "hook_3s", "chars_per_sec")} for v in top]}
    if analysis:
        out["analysis"] = {k: analysis.get(k) for k in ("summary", "recurring_topics", "narration", "source_usage",
                                                         "audience_interest", "patterns", "topic_ideas", "uncollected",
                                                         "created", "ai_calls")}
    else:
        out["analysis"] = None
    return out


def channels() -> dict:
    rows = []
    for d in sorted(_root().glob("ch_*")):
        scan, analysis = _read(d / "scan.json"), _read(d / "analysis.json")
        if scan:
            rows.append({"channel_id": d.name, "name": scan["channel"]["name"], "url": scan["channel"]["url"],
                         "scanned_at": scan["scanned_at"], "videos": scan["stats"]["videos"],
                         "median_views": scan["stats"]["median_views"],
                         "patterns": [p["type"] for p in (analysis or {}).get("patterns", [])]})
    return {"status": "ok", "channels": rows}


def show(ref: str) -> dict:
    d = _dir(_resolve(ref))
    return {"status": "ok", "channel_id": d.name, **summary(_read(d / "scan.json"), _read(d / "analysis.json"))}


def _analysis(cid: str) -> dict:
    a = _read(_dir(cid) / "analysis.json")
    if not a:
        raise core.FactoryError("not_ready", "패턴 분석이 아직 없습니다. channel analyze 를 AI 분석과 함께 다시 실행해 주세요.")
    return a


def topics(refs: list[str]) -> dict:
    """B: 한 채널의 추천 주제 5개 / C: 여러 채널 공통 패턴의 주제. batch --select 로 고를 수 있게 후보로 저장."""
    ids = [_resolve(r) for r in refs]
    analyses = [_analysis(i) for i in ids]
    if len(ids) == 1:
        ideas = [{**i, "channel_id": ids[0]} for i in analyses[0]["topic_ideas"]]
        compared = None
    else:
        compared = ch.compare(analyses)
        ideas = compared["topic_ideas"]
    by_id = dict(zip(ids, analyses))
    rows = []
    for idea in ideas:
        opts = ch.make_options(by_id[idea["channel_id"]], idea["pattern_index"], idea)
        opts["instructions"] += f"\n- 영상 제목 후보: {idea['title']}"
        # 조사에는 분야가 드러나는 문장을 쓴다 (제목만 넣으면 'K팝 신인상'이 '야구 신인상'으로 조사된 적이 있다)
        rows.append({"topic": idea.get("search_query") or idea["title"], "title": idea["title"], "angle": idea["angle"],
                     "why": idea["why"], "channel_id": idea["channel_id"], "pattern_index": idea["pattern_index"],
                     "pattern": by_id[idea["channel_id"]]["patterns"][idea["pattern_index"]]["type"],
                     "too_similar": idea.get("too_similar", False), **opts})
    saved = batch.save_candidates(core.output_root(), rows)
    return {"status": "ok", **saved, "compare": compared,
            "message": "번호를 골라 batch --select 2 --candidates <id> 로 제작합니다. 조회수를 보장하지 않습니다."}


async def make(ref: str, *, topic: str | None = None, pattern: int = 0, review: bool = False, log=print, **options) -> dict:
    """A: 주제 직접 입력 + 채널 패턴 적용."""
    cid = _resolve(ref)
    opts = ch.make_options(_analysis(cid), pattern)
    if not topic:
        raise core.FactoryError("invalid", "주제를 입력하거나 channel topics 로 추천 주제를 골라 주세요.")
    seconds = options.pop("seconds", None) or opts["seconds"]
    instructions = "\n".join(x for x in (options.pop("instructions", ""), opts["instructions"]) if x)
    result = await core.make(topic=topic, review=review, seconds=seconds, benchmark=opts["benchmark"],
                             instructions=instructions, log=log, **options)
    return record(result, cid, pattern)


def record(result: dict, cid: str, pattern: int) -> dict:
    """프로젝트 폴더에 적용한 패턴과 원본 자막과의 겹침 비율을 남긴다 (복사 감시)."""
    if not result.get("project_dir"):
        return result
    job = Path(result["project_dir"])
    script = _read(job / "script.json", {}) or {}
    text = " ".join(s.get("narration", "") for s in script.get("scenes", []))
    refs = [v.get("transcript", "") for v in _read(_dir(cid) / "scan.json")["videos"] if v.get("transcript")]
    rate = ch.overlap(text, refs) if text else None
    info = {"channel_id": cid, "pattern_index": pattern, "overlap_with_benchmark": rate,
            "warning": "벤치마킹 자막과 겹치는 문장이 많습니다. 대본을 고쳐 주세요." if rate and rate > 0.15 else ""}
    batch._write(job / "channel_benchmark.json", info)
    return {**result, "channel_benchmark": info}


async def auto(refs: list[str], *, review: bool = False, log=print, **options) -> dict:
    """C: 여러 채널 공통 패턴 → 첫 추천 주제를 골라 제작."""
    listed = topics(refs)
    pick = next((c for c in listed["candidates"] if not c.get("too_similar")), None)
    if not pick:
        raise core.FactoryError("not_found", "공통 패턴에서 쓸 만한 새 주제를 찾지 못했습니다.")
    result = await core.make(topic=pick["topic"], review=review, seconds=options.pop("seconds", None) or pick["seconds"],
                             benchmark=pick["benchmark"], instructions=pick["instructions"], log=log, **options)
    return {**record(result, pick["channel_id"], pick["pattern_index"]), "picked": {k: pick[k] for k in ("number", "topic", "pattern", "channel_id")},
            "candidates_id": listed["candidates_id"]}


def add_parser(sub):
    p = sub.add_parser("channel", help="경쟁 채널 쇼츠 벤치마킹 (분석·추천 주제·비교·패턴 적용 제작)")
    c = p.add_subparsers(dest="channel_cmd", required=True)
    an = c.add_parser("analyze", help="채널 URL 또는 @채널명 분석 (캐시 재사용)")
    an.add_argument("channel")
    an.add_argument("--refresh", action="store_true", help="캐시가 있어도 다시 수집 (조회수 증가 실측)")
    an.add_argument("--no-ai", action="store_true", help="공개 지표만 계산, AI 패턴 분석 안 함")
    an.add_argument("--latest", type=int, default=30)
    an.add_argument("--popular", type=int, default=15)
    c.add_parser("list", help="분석한 채널 목록")
    sh = c.add_parser("show", help="분석 결과")
    sh.add_argument("channel")
    tp = c.add_parser("topics", help="추천 주제 (채널 1개) / 공통 패턴 주제 (여러 개)")
    tp.add_argument("channels", nargs="+")
    mk = c.add_parser("make", help="주제 + 채널 패턴으로 제작")
    mk.add_argument("channel")
    mk.add_argument("--topic", required=True)
    mk.add_argument("--pattern", type=int, default=0, help="패턴 번호 (0부터, 기본 성과 1위)")
    mk.add_argument("--review", action="store_true")
    mk.add_argument("--seconds", type=int)
    au = c.add_parser("auto", help="여러 채널 공통 패턴으로 주제 자동 선정 후 제작")
    au.add_argument("channels", nargs="+")
    au.add_argument("--review", action="store_true")
    au.add_argument("--seconds", type=int)
    return p


async def dispatch(a, log=print) -> dict:
    cmd = a.channel_cmd
    if cmd == "analyze":
        if not (1 <= a.latest <= 50 and 0 <= a.popular <= 30):
            raise core.FactoryError("invalid", "--latest 는 1~50, --popular 는 0~30 입니다.")
        return await analyze(a.channel, refresh=a.refresh, ai=not a.no_ai, latest=a.latest, popular=a.popular, log=log)
    if cmd == "list":
        return channels()
    if cmd == "show":
        return show(a.channel)
    if cmd == "topics":
        return topics(a.channels)
    if cmd == "make":
        return await make(a.channel, topic=a.topic, pattern=a.pattern, review=a.review, seconds=a.seconds, log=log)
    if cmd == "auto":
        return await auto(a.channels, review=a.review, seconds=a.seconds, log=log)
    raise core.FactoryError("invalid", "지원하지 않는 channel 명령")
