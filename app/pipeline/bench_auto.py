"""Benchmark × V1 통합: 조사 결과로 8개 profile 을 점수화해 고르고, 그 구조를 대본·장면에 주입한다.

흐름 (run_pipeline 의 조사 뒤 · 대본 앞):
  analyze_brief (AI 1회: 사실/추론 분리, 시청 질문 후보, profile 9기준 점수)
  → route (결정적 가중합 + 권리/근거 게이트 + fallback)
  → pick_candidate (View Potential 내부 점수 최고 후보)
  → compose_prompt_block (대본 프롬프트) → apply_scene_plan (장면 역할·성격)

점수는 '현재 확보한 자료로 어떤 구조가 경쟁력 있는가'를 고르는 내부 heuristic 이다.
조회수나 성공 확률을 예측하지 않는다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from . import benchmark
from .llm import ask_structured
from .models import ResearchDoc
from .script import CHARS_PER_SEC, _docs_block
from .script_split import CONTENT_KINDS, EMPHASIS_MAX, short_phrase

INTEGRATION_FILE = benchmark.PROFILE_ROOT / "v1" / "integration.yaml"
DECISION_FILE = "benchmark_decision.json"
CRITERIA = ("topic_fit", "viewer_curiosity", "evidence_availability", "visual_potential", "freshness",
            "comparison_potential", "payoff_strength", "repeatability", "rights_safety")
VIEW_PARTS = ("hook_strength", "evidence_strength", "visual_potential", "freshness", "payoff")
MAX_SCENES = 8
DISCLAIMER = "점수는 현재 자료로 어떤 구성이 경쟁력 있는지 고르는 내부 판단값이며 조회수나 성공 확률 예측이 아닙니다."


# ---------- AI 응답 구조 ----------

class Fact(BaseModel):
    text: str = Field(description="자료에서 직접 확인된 사실 한 문장. 추측·해석 금지")
    source_index: int = Field(description="근거 자료 번호 (자료 1 이면 1). 모르면 0")
    date: str = Field(default="", description="자료에 적힌 날짜나 시점. 없으면 빈 문자열")


class SourceAnalysis(BaseModel):
    source_topic: str = Field(description="참고 원본이 다루는 핵심 주제")
    source_hook: str = Field(description="원본이 시청자를 붙잡는 방식 (문장을 베끼지 말고 방식만)")
    source_structure: str = Field(description="원본의 전개 구조를 순서대로")
    interesting_points: list[str] = Field(description="왜 볼 만한지에 해당하는 포인트 2~4개")


class ContentCandidate(BaseModel):
    viewer_question: str = Field(description="시청자가 이 영상을 끝까지 볼 이유가 되는 구체적인 질문 하나")
    reason_to_watch: str = Field(description="이 질문이 궁금한 이유 (익숙한 대상의 변화, 의외의 숫자 등)")
    claim: str = Field(description="영상이 근거로 보여 줄 주장 한 문장. 확인된 사실 범위 안에서")
    creative_hook: str = Field(description="첫 장면 훅 문장 후보. 사실을 새로 만들지 말 것")
    evidence_fact_ids: list[int] = Field(description="이 주장을 받치는 verified_facts 번호 (1부터)")
    hook_strength: int = Field(description="훅의 힘 0~20")
    evidence_strength: int = Field(description="근거의 충분함 0~20")
    visual_potential: int = Field(description="화면으로 보여 주기 좋은 정도 0~20")
    freshness: int = Field(description="새로움·시의성 0~20")
    payoff: int = Field(description="마지막에 주는 답의 만족감 0~20")


class ProfileScore(BaseModel):
    profile_id: str = Field(description="평가한 profile id (목록의 id 그대로)")
    topic_fit: int = Field(description="주제와 구조의 적합도 0~10")
    viewer_curiosity: int = Field(description="이 구조로 만들 때 생기는 궁금증 0~10")
    evidence_availability: int = Field(description="이 구조에 필요한 근거가 자료에 있는 정도 0~10")
    visual_potential: int = Field(description="화면 구성 가능성 0~10")
    freshness: int = Field(description="시의성 0~10")
    comparison_potential: int = Field(description="비교·대조 요소 0~10")
    payoff_strength: int = Field(description="결론의 만족감 0~10")
    repeatability: int = Field(description="같은 구조로 후속 제작 가능성 0~10")
    rights_safety: int = Field(description="권리 문제 없이 만들 수 있는 정도 0~10")
    covered_slots: list[str] = Field(description="자료에서 확인된 근거 슬롯 이름 (목록에 적힌 이름 그대로)")
    reason: str = Field(description="점수의 이유 한 문장")


class EvidenceMoment(BaseModel):
    start_sec: float = Field(description="원본 영상에서 근거가 시작하는 초 (자막 타임스탬프 기준)")
    end_sec: float = Field(description="근거가 끝나는 초")
    what: str = Field(description="이 구간에서 확인되는 것 한 문장 (자막·설명으로 확인된 범위)")
    candidate_index: int = Field(default=0, description="이 근거가 받치는 기획 후보 번호 (0부터)")


class FollowupQuery(BaseModel):
    profile_id: str
    query: str = Field(description="이 구조에 부족한 근거를 찾을 한국어 검색어")


class ContentBrief(BaseModel):
    topic: str = Field(description="영상 주제 한 줄")
    verified_facts: list[Fact] = Field(description="자료에서 확인된 사실 3~10개")
    inferences: list[str] = Field(description="자료로부터의 추론·해석. 사실과 섞지 말 것")
    source_analysis: SourceAnalysis | None = Field(default=None, description="참고 URL 이 있을 때만 채운다")
    candidates: list[ContentCandidate] = Field(description="서로 다른 각도의 기획 후보 2~3개")
    profile_scores: list[ProfileScore] = Field(description="목록의 모든 profile 을 하나씩 평가")
    followup_queries: list[FollowupQuery] = Field(default_factory=list,
                                                  description="점수 상위 profile 에 부족한 근거를 찾을 검색어")
    evidence_moments: list[EvidenceMoment] = Field(
        default_factory=list, description="참고 원본에 타임스탬프 자막이 있을 때: 관찰 포인트·주장의 근거가 되는 원본 구간 2~5개")


# ---------- 통합 정보 ----------

def load_integration(path: Path | None = None) -> dict[str, Any]:
    data = yaml.safe_load((path or INTEGRATION_FILE).read_text(encoding="utf-8"))
    profiles = data.get("profiles") or {}
    if data.get("fallback") not in profiles:
        raise ValueError("benchmark integration fallback profile is missing")
    if sum(int(v) for v in (data.get("weights") or {}).values()) != 100:
        raise ValueError("benchmark integration weights must sum to 100")
    for pid, spec in profiles.items():
        if not spec.get("beats"):
            raise ValueError(f"benchmark integration beats missing: {pid}")
        for beat in spec["beats"]:
            if beat.get("kind") not in CONTENT_KINDS:
                raise ValueError(f"unknown content kind in {pid}: {beat.get('kind')}")
    return data


def profile_ids(integ: dict[str, Any] | None = None) -> list[str]:
    return list((integ or load_integration())["profiles"])


def validate_choice(choice: str | None, integ: dict[str, Any] | None = None) -> str:
    """--benchmark 값 검사. auto / off / profile id."""
    value = (choice or "auto").strip()
    if value in ("auto", "off"):
        return value
    ids = profile_ids(integ)
    if value not in ids:
        raise ValueError(f"알 수 없는 benchmark 방식입니다: {value} (auto / off / {' / '.join(ids)})")
    return value


def _profile_names() -> dict[str, str]:
    try:
        return {p["id"]: p["name"] for p in benchmark.profiles()}
    except Exception:  # noqa: BLE001 - 이름은 표시용
        return {}


# ---------- 1. Content Brief (AI 1회) ----------

BRIEF_SYSTEM = """당신은 한국어 유튜브 쇼츠 기획 PD입니다. 대본을 쓰기 전에 '시청자가 왜 이 영상을 봐야 하는가'를 정하고,
어떤 콘텐츠 구조(profile)가 지금 확보한 자료로 가장 경쟁력이 있는지 평가합니다.

규칙:
- verified_facts 에는 자료에 직접 적힌 것만 넣는다. 해석·전망·가능성은 inferences 로 분리한다.
- creative_hook 은 표현일 뿐 새로운 사실을 만들지 않는다.
- viewer_question 은 '○○는 여러 활동을 한다' 같은 설명이 아니라 구체적인 궁금증 하나여야 한다.
- 모든 profile 을 빠짐없이 평가한다. 점수는 조회수 예측이 아니라 구조 적합도다.
- 근거 영상이 필요한 profile 은 [근거 영상]이 '없음'이면 rights_safety 와 evidence_availability 를 낮게 준다.
  사용자가 준 인용용 영상·캡처가 있으면 분석·비평·비교·해설 목적의 인용(transformative_quote)으로 쓸 수 있으므로,
  해설 중심 구성이 가능한지로 rights_safety 를 평가한다.
- 참고 원본에 [타임스탬프 자막]이 있으면 evidence_moments 에 근거 구간(초)을 적는다. 자막으로 확인되지 않는 표정·동작은 단정하지 않는다.
- covered_slots 에는 그 profile 목록에 적힌 슬롯 이름 중 자료에서 실제로 확인된 것만 넣는다.
- 참고 원본(유튜브·기사)이 있으면 source_analysis 에 왜 볼 만한지 분석하되 원본 문장을 베끼지 않는다. 우리 영상은 새 구성으로 만든다.
- 모든 내용은 한국어로."""


def _profile_menu(integ: dict[str, Any]) -> str:
    rows = []
    for pid, spec in integ["profiles"].items():
        needs = spec.get("research_needs") or {}
        video = " · 근거 영상 필요(권리 확인 영상 또는 사용자가 준 인용 영상·캡처)" if spec.get("requires_licensed_video") else ""
        rows.append(f"- {pid}: {spec.get('summary', '')}{video}\n"
                    f"  필수 슬롯: {', '.join(needs.get('required', []))} / 선택 슬롯: {', '.join(needs.get('optional', []))}")
    return "\n".join(rows)


async def analyze_brief(llm: dict[str, Any], topic: str, docs: list[ResearchDoc], integ: dict[str, Any], *,
                        input_kind: str = "topic", source_info: str = "", has_licensed_video: bool = False,
                        instructions: str = "", quote_media: str = "") -> ContentBrief:
    user = (
        f"[입력 종류] {input_kind}\n[주제] {topic}\n"
        f"[근거 영상] {'있음' if has_licensed_video else '없음'}"
        + (f" ({quote_media})" if quote_media else "") + "\n"
        + (f"[사용자 지침] {instructions.strip()}\n" if instructions.strip() else "")
        + (f"\n[참고 원본 정보]\n{source_info.strip()}\n" if source_info.strip() else "")
        + f"\n## 평가할 profile 목록\n{_profile_menu(integ)}\n\n"
        f"## 조사 자료\n{_docs_block(docs, limit_chars=1800)}\n\n"
        "사실/추론을 나누고, 기획 후보 2~3개와 모든 profile 의 점수를 작성하세요."
    )
    return await ask_structured(llm, BRIEF_SYSTEM, user, ContentBrief)


# ---------- 2. Auto Router ----------

def _clamp(value: Any, top: int) -> int:
    try:
        return max(0, min(top, int(value)))
    except (TypeError, ValueError):
        return 0


def score_profile(ps: ProfileScore | None, weights: dict[str, int]) -> tuple[int, dict[str, int]]:
    parts = {c: _clamp(getattr(ps, c, 0), 10) for c in CRITERIA} if ps else {c: 0 for c in CRITERIA}
    total = sum(weights.get(c, 0) * v for c, v in parts.items()) / 10
    return round(total), parts


def route(brief: ContentBrief | None, integ: dict[str, Any], *, forced: str | None = None,
          has_licensed_video: bool = False) -> dict[str, Any]:
    """8개 profile 전체를 점수화하고 자격(게이트)을 통과한 최고점을 고른다. 부족하면 fallback."""
    weights = {k: int(v) for k, v in integ["weights"].items()}
    fallback = integ["fallback"]
    min_score = int(integ.get("min_score", 45))
    min_evidence = int(integ.get("min_evidence_availability", 4))
    by_id = {ps.profile_id.strip(): ps for ps in (brief.profile_scores if brief else [])}
    ranking: list[dict[str, Any]] = []
    for pid, spec in integ["profiles"].items():
        ps = by_id.get(pid)
        score, parts = score_profile(ps, weights)
        gates: list[str] = []
        if spec.get("requires_licensed_video") and not has_licensed_video:
            gates.append("근거 영상(권리 확인 영상 또는 사용자가 준 인용 영상)이 없어 이 구조를 만들 수 없음")
        required = (spec.get("research_needs") or {}).get("required", [])
        covered = [s for s in (ps.covered_slots if ps else []) if s in required + (spec.get("research_needs") or {}).get("optional", [])]
        missing = [s for s in required if s not in covered]
        if not ps:
            gates.append("평가 결과 없음")
        elif missing and pid != fallback:
            gates.append(f"필수 근거 부족: {', '.join(missing)}")
        if ps and parts["evidence_availability"] < min_evidence and pid != fallback:
            gates.append("근거 확보도가 낮음")
        ranking.append({"profile_id": pid, "score": score, "criteria": parts, "eligible": not gates,
                        "gates": gates, "covered_slots": covered, "missing_slots": missing,
                        "reason": ps.reason if ps else ""})
    ranking.sort(key=lambda r: (-r["score"], r["profile_id"]))
    eligible = [r for r in ranking if r["eligible"]]
    names = _profile_names()
    warnings: list[str] = []
    fallback_reason = ""
    if forced:
        chosen = next(r for r in ranking if r["profile_id"] == forced)
        if chosen["eligible"] or (brief is None and not any("권리" in g for g in chosen["gates"])):
            mode, selected = "forced", forced
        else:
            mode, selected = "forced_fallback", fallback
            fallback_reason = f"지정한 {forced} 방식은 지금 자료로 만들 수 없습니다 ({'; '.join(chosen['gates'])})"
            warnings.append(fallback_reason)
    elif brief is None:
        mode, selected = "fallback", fallback
        fallback_reason = "자료 분석(AI)이 실패해 가장 안전한 정보형 구조를 씁니다"
    elif not eligible or eligible[0]["score"] < min_score:
        mode, selected = "fallback", fallback
        top = eligible[0] if eligible else ranking[0]
        fallback_reason = (f"조건을 만족하는 구조가 없거나 최고점({top['profile_id']} {top['score']}점)이 "
                           f"기준 {min_score}점 미만이라 억지로 적용하지 않습니다")
    else:
        mode, selected = "auto", eligible[0]["profile_id"]
    sel = next(r for r in ranking if r["profile_id"] == selected)
    if mode == "auto":
        runner = next((r for r in eligible if r["profile_id"] != selected), None)
        gap = f", 다음 후보 {runner['profile_id']}보다 {sel['score'] - runner['score']}점 높음" if runner else ""
        slots = f" · 확인된 근거: {', '.join(sel['covered_slots'])}" if sel["covered_slots"] else ""
        reason = f"{sel['reason'] or '주제와 자료에 가장 잘 맞는 구조'}{slots}{gap}"
    elif mode == "forced":
        reason = f"사용자가 {selected} 방식을 지정했습니다"
    else:
        reason = fallback_reason
    spec = integ["profiles"][selected]
    return {
        "mode": mode, "requested": forced or "auto", "selected_profile": selected,
        "profile_name": names.get(selected, selected), "fallback_used": selected == fallback and mode != "auto" and forced != fallback,
        "fallback_reason": fallback_reason, "selection_reason": reason,
        "candidate_scores": {r["profile_id"]: r["score"] for r in ranking},
        "top3": [{"profile_id": r["profile_id"], "score": r["score"], "eligible": r["eligible"]} for r in ranking[:3]],
        "ranking": ranking, "narration_mode": spec.get("narration_mode", "narrated"),
        "warnings": warnings, "note": DISCLAIMER,
    }


# ---------- 3. View Potential 후보 선택 ----------

def view_potential(c: ContentCandidate) -> dict[str, int]:
    parts = {p: _clamp(getattr(c, p, 0), 20) for p in VIEW_PARTS}
    return {**parts, "total": sum(parts.values())}


def pick_candidate(brief: ContentBrief | None) -> tuple[int, ContentCandidate | None, list[dict[str, Any]]]:
    if not brief or not brief.candidates:
        return -1, None, []
    scored = [{"index": i, "viewer_question": c.viewer_question, "creative_hook": c.creative_hook,
               "view_potential": view_potential(c)} for i, c in enumerate(brief.candidates)]
    best = max(scored, key=lambda s: (s["view_potential"]["total"], -s["index"]))
    return best["index"], brief.candidates[best["index"]], scored


def followup_query(brief: ContentBrief | None, profile_id: str) -> str:
    if not brief:
        return ""
    return next((q.query.strip() for q in brief.followup_queries if q.profile_id == profile_id and q.query.strip()), "")


# ---------- 4. 대본 프롬프트 ----------

def scene_roles(spec: dict[str, Any], seconds: int) -> list[str]:
    """장면마다 맡을 역할. 짧은 영상은 여러 장면짜리 역할을 1장면으로 줄이고, 최대 8장면."""
    beats = spec["beats"]
    short = seconds < 25
    roles: list[str] = []
    for beat in beats:
        roles.extend([beat["role"]] * (1 if short else max(1, int(beat.get("scenes", 1)))))
    while len(roles) > MAX_SCENES:
        # 가장 많이 반복되는 역할부터 한 장면씩 줄인다
        counts = {r: roles.count(r) for r in roles}
        role = max(counts, key=lambda r: counts[r])
        roles.remove(role)
    return roles


def compose_prompt_block(profile_id: str, integ: dict[str, Any], decision: dict[str, Any],
                         brief: ContentBrief | None, candidate: ContentCandidate | None, seconds: int,
                         quote_media: bool = False) -> str:
    spec = integ["profiles"][profile_id]
    roles = scene_roles(spec, seconds)
    beats = {b["role"]: b for b in spec["beats"]}
    lines = [f"\n[콘텐츠 구조 — {decision.get('profile_name', profile_id)} ({profile_id})]",
             "이 영상은 아래 구조를 따릅니다. 카테고리 기본 규칙보다 이 구조가 우선합니다. (사용자 지침이 있으면 그것이 최우선)",
             f"- 훅 전략: {spec.get('hook_strategy', '')}",
             f"- 페이싱: {spec.get('pacing', '')}",
             f"- 결론 전략: {spec.get('payoff_strategy', '')}",
             f"- 마지막 장면: {spec.get('ending_question', '')}",
             f"- 장면 수: 정확히 {len(roles)}개. 각 장면의 beat_role 에 아래 역할 이름을 그대로 쓰세요.",
             "[장면별 역할과 시간 배분]"]
    cursor = 0.0
    total_weight = sum(beats[r]["weight"] / roles.count(r) for r in roles)
    for i, role in enumerate(roles, 1):
        beat = beats[role]
        sec = seconds * (beat["weight"] / roles.count(role)) / total_weight
        lines.append(f"{i}. beat_role={role} · {cursor:.0f}~{cursor + sec:.0f}초 · 약 {int(sec * CHARS_PER_SEC)}자 · "
                     f"{beat.get('instruction', '')} · 강조문구 {beat.get('emphasis_max', EMPHASIS_MAX)}자 이내")
        cursor += sec
    if candidate:
        lines += ["", "[시청 이유 — 대본보다 먼저 정한 것]",
                  f"- viewer_question(영상이 답할 질문): {candidate.viewer_question}",
                  f"- reason_to_watch(볼 이유): {candidate.reason_to_watch}",
                  f"- claim(근거로 보여 줄 주장): {candidate.claim}",
                  f"- creative_hook(표현 후보, 사실 아님): {candidate.creative_hook}"]
    if brief and brief.verified_facts:
        lines += ["", "[verified_facts — 자료에서 확인된 사실. 이것만 단정해서 말할 수 있다]"]
        use = set(candidate.evidence_fact_ids) if candidate else set()
        for i, f in enumerate(brief.verified_facts, 1):
            mark = " ★주장의 근거" if i in use else ""
            date = f" ({f.date})" if f.date else ""
            lines.append(f"F{i}. {f.text}{date} [자료 {f.source_index}]{mark}")
    if brief and brief.inferences:
        lines += ["", "[inference — 추론. 말할 때는 '~일 수 있다', '~로 보인다'처럼 추론임을 드러낸다]"]
        lines += [f"I{i}. {t}" for i, t in enumerate(brief.inferences, 1)]
    sel = next((r for r in decision.get("ranking", []) if r["profile_id"] == profile_id), None)
    if sel and sel.get("missing_slots"):
        lines.append(f"- 확인되지 않은 근거: {', '.join(sel['missing_slots'])} → 이 부분은 단정하지 말고 모른다고 하거나 생략한다.")
    if brief and brief.source_analysis:
        sa = brief.source_analysis
        lines += ["", "[참고 원본 분석 — 구조와 볼 이유만 참고. 원본 문장·장면 순서를 그대로 쓰지 않는다]",
                  f"- 원본 주제: {sa.source_topic}", f"- 원본 훅 방식: {sa.source_hook}",
                  f"- 원본 구조: {sa.source_structure}",
                  f"- 볼 만한 포인트: {' / '.join(sa.interesting_points)}"]
    if quote_media:
        roles = ", ".join(spec.get("evidence_roles") or [])
        lines += ["", f"[인용 장면 — {roles} 역할 장면에는 원본 영상·캡처가 짧게 인용된다]",
                  "- 그 장면 나레이션은 원본을 다시 들려주는 게 아니라 화면에서 무엇을 봐야 하는지, 왜 중요한지 해설한다.",
                  "- 원본 대사·가사를 그대로 읽지 않는다. 우리 분석·비교가 중심이고 원본은 근거로만 쓴다."]
        if brief and brief.evidence_moments:
            lines += [f"- 근거 구간 {m.start_sec:.0f}~{m.end_sec:.0f}초: {m.what}" for m in brief.evidence_moments[:5]]
    lines.append("- 사실(verified_facts)·추론(inference)·창작 표현(creative_hook)을 섞지 마세요. 자료에 없는 숫자·날짜·발언을 만들지 마세요.")
    return "\n".join(lines) + "\n"


# ---------- 5. 장면 계획 ----------

def _fit_roles(roles: list[str], n: int) -> list[str]:
    """역할 목록을 실제 장면 수 n 에 맞춘다. 장면이 모자라면 서로 다른 역할부터 남기고(처음·끝 유지),
    남으면 여러 장면짜리 역할을 늘린다."""
    if n <= 0:
        return []
    if n == len(roles):
        return list(roles)
    if n > len(roles):
        out = list(roles)
        while len(out) < n:
            counts = {r: out.count(r) for r in out}
            middle = [r for r in out[1:-1]] or out
            role = max(middle, key=lambda r: (counts[r], -out.index(r)))
            out.insert(out.index(role), role)
        return out
    unique = list(dict.fromkeys(roles))
    if n >= len(unique):
        out = list(unique)
        for r in roles:   # 남는 자리는 원래 여러 장면이던 역할에 순서대로 준다
            if len(out) >= n:
                break
            if roles.count(r) > out.count(r):
                out.insert(out.index(r), r)
        return out
    if n == 1:
        return [unique[0]]
    idx = [round(i * (len(unique) - 1) / (n - 1)) for i in range(n)]
    return [unique[i] for i in idx]


def apply_scene_plan(script: Any, profile_id: str, integ: dict[str, Any], seconds: int) -> Any:
    """AI 가 붙인 beat_role(없으면 순서)로 장면 역할·내용 성격·강조문구 길이를 profile 에 맞춘다. 나레이션은 고치지 않는다."""
    spec = integ["profiles"][profile_id]
    beats = {b["role"]: b for b in spec["beats"]}
    n = len(script.scenes)
    expected = _fit_roles(scene_roles(spec, seconds), n)
    for i, scene in enumerate(script.scenes):
        role = (getattr(scene, "beat_role", "") or "").strip()
        if role not in beats:
            role = expected[i]
        if i == 0:
            role = spec["beats"][0]["role"]          # 첫 장면은 항상 훅
        if i == n - 1 and n > 1:
            role = spec["beats"][-1]["role"]         # 마지막은 결론/질문
        beat = beats[role]
        scene.beat_role = role
        scene.scene_type = role
        kind = beat["kind"]
        current = getattr(scene, "content_kind", "")
        has_material = ((current in ("number", "trend") and getattr(scene, "key_number", ""))
                        or (current == "comparison" and getattr(scene, "compare_a", "") and getattr(scene, "compare_b", "")))
        if kind in ("hook", "conclusion") or not has_material:
            if kind == "comparison" and not (getattr(scene, "compare_a", "") and getattr(scene, "compare_b", "")):
                kind = current if current in CONTENT_KINDS and current not in ("hook", "conclusion") else "claim"
            if kind in ("number", "trend") and not getattr(scene, "key_number", ""):
                kind = current if current in CONTENT_KINDS and current not in ("hook", "conclusion") else "concept"
            scene.content_kind = kind
        limit = int(beat.get("emphasis_max", EMPHASIS_MAX))
        text = " ".join((scene.on_screen_text or "").split())
        if not text or len(text) > limit:
            scene.on_screen_text = short_phrase(text or scene.narration, scene.content_kind,
                                                getattr(scene, "key_number", ""), max_chars=limit)
        tag = f"benchmark:{profile_id}/{role}"
        scene.notes = f"{scene.notes} {tag}".strip() if tag not in (scene.notes or "") else scene.notes
    return script


# ---------- 6. 품질 확인 ----------

def quality_check(decision: dict[str, Any], script: Any, duration: float | None = None,
                  integ: dict[str, Any] | None = None) -> list[str]:
    """렌더를 막지 않는 경고 목록."""
    integ = integ or load_integration()
    pid = decision.get("selected_profile")
    if not pid or pid not in integ["profiles"]:
        return []
    spec = integ["profiles"][pid]
    warnings: list[str] = []
    roles = [getattr(s, "beat_role", "") for s in script.scenes]
    if not roles or roles[0] != spec["beats"][0]["role"]:
        warnings.append("첫 장면이 훅 역할이 아닙니다")
    if spec["beats"][-1]["role"] not in roles:
        warnings.append("마지막 질문/결론 장면이 없습니다")
    payoff_roles = {b["role"] for b in spec["beats"] if b["kind"] == "conclusion"}
    if not payoff_roles.intersection(roles):
        warnings.append("질문에 답하는 결론 장면이 없습니다")
    missing = [b["role"] for b in spec["beats"] if b["role"] not in roles]
    if missing:
        warnings.append(f"빠진 구조 역할: {', '.join(missing)}")
    if duration:
        try:
            prof = benchmark.load_profile(pid)
            lo, hi = prof.min_seconds, prof.max_seconds
            if not lo - 5 <= duration <= hi + 10:
                warnings.append(f"영상 길이 {duration:.1f}초가 이 구조의 권장 범위({lo}~{hi}초)를 벗어났습니다")
        except Exception:  # noqa: BLE001
            pass
    if not 3 <= len(script.scenes) <= MAX_SCENES:
        warnings.append(f"장면 수 {len(script.scenes)}개가 권장 범위(3~{MAX_SCENES})를 벗어났습니다")
    return warnings


# ---------- 저장 ----------

def brief_summary(brief: ContentBrief | None, index: int, scored: list[dict[str, Any]]) -> dict[str, Any]:
    if not brief:
        return {"viewer_question": "", "reason_to_watch": "", "claim": "", "creative_hook": "",
                "view_potential_score": None, "content_candidates": [], "selected_candidate": None,
                "verified_facts": [], "inferences": [], "source_analysis": None, "evidence_moments": []}
    cand = brief.candidates[index] if 0 <= index < len(brief.candidates) else None
    return {
        "viewer_question": cand.viewer_question if cand else "",
        "reason_to_watch": cand.reason_to_watch if cand else "",
        "claim": cand.claim if cand else "",
        "creative_hook": cand.creative_hook if cand else "",
        "evidence_fact_ids": cand.evidence_fact_ids if cand else [],
        "view_potential_score": scored[index]["view_potential"]["total"] if cand else None,
        "view_potential": scored[index]["view_potential"] if cand else None,
        "content_candidates": scored, "selected_candidate": index if cand else None,
        "verified_facts": [f.model_dump() for f in brief.verified_facts],
        "inferences": list(brief.inferences),
        "source_analysis": brief.source_analysis.model_dump() if brief.source_analysis else None,
        "evidence_moments": [m.model_dump() for m in brief.evidence_moments],
    }


def save_decision(job_dir: Path, decision: dict[str, Any]) -> Path:
    path = job_dir / DECISION_FILE
    path.write_text(json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_decision(job_dir: Path) -> dict[str, Any] | None:
    path = job_dir / DECISION_FILE
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def state_view(decision: dict[str, Any] | None) -> dict[str, Any]:
    """project_state.json 에 남길 요약 (전체는 benchmark_decision.json)."""
    if not decision:
        return {"mode": "off"}
    keys = ("mode", "requested", "selected_profile", "profile_name", "candidate_scores", "top3",
            "viewer_question", "reason_to_watch", "claim", "view_potential_score", "selection_reason",
            "fallback_used", "fallback_reason", "narration_mode", "scene_roles", "research_followup",
            "warnings", "quality", "note", "view_potential", "creative_hook", "evidence_moments")
    out = {k: decision[k] for k in keys if k in decision}
    # 주장을 받치는 근거: 선택 후보가 가리킨 verified_facts 원문 (전체 사실·추론은 benchmark_decision.json)
    facts = decision.get("verified_facts") or []
    ids = decision.get("evidence_fact_ids") or []
    if facts and ids:
        out["evidence"] = [facts[i - 1]["text"] for i in ids if isinstance(i, int) and 0 < i <= len(facts)]
    return out
