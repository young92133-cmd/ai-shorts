"""2D 장면별 화면 자동 선택 (Visual Resolver).

장면 설계(내용 성격·강조문구·숫자·비교 대상)와 소스 권리 대장을 보고 장면마다 보여줄 화면을 정한다.
분야별 규칙은 없다. 판단 기준은 '내용 성격'뿐이다.

우선순위:
  1. 권리 확인된 사용자 업로드 (장면 지정 파일 → 내용 매칭 순)
  2. 대장상 사용 가능한 기존 자료 (현재는 업로드 영상 broll)
  3. AI 생성 이미지 (이미지 생성이 켜져 있을 때만)
  4. 허용 스톡 (현재 연동 없음 — 자리만)
  5. 내부 카드 (숫자·변화·비교·도입·핵심·정리)
  6. 안전 카드 (카드 그리기도 실패할 때)
권리 확인이 안 된 자료는 후보가 되지 않는다. 관련 자료가 없으면 억지로 넣지 않고 카드로 간다.
장면마다 무엇을, 어디서, 왜 골랐는지 VisualDecision 으로 남긴다.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any, Callable

from . import cards
from .assets import kind_of
from .images import get_images
from .images.base import make_fallback_card
from .media import extract_frames
from .models import Asset, VisualDecision
from .script_split import trend_direction
from .sources import SourceRegistry

IMAGE_FIRST = {"hook", "subject", "story", "claim", "concept", "conclusion"}   # 그림이 설명에 유리한 성격
CARD_REASON = {
    "number_card": "중요한 숫자를 크게 보여주는 것이 가장 분명해서 숫자 카드",
    "trend_card": "시간에 따른 변화를 숫자와 증감 화살표로 보여주려고 변화 카드 (차트 엔진은 아직 없음)",
    "compare_card": "두 대상을 나란히 비교해 보여주려고 비교 카드",
    "hook_card": "첫 장면에서 시선을 끄는 질문·문구를 크게 보여주려고 도입 카드",
    "summary_card": "마지막에 핵심을 정리해 보여주려고 정리 카드",
    "statement_card": "장면의 핵심 문구를 강조하려고 핵심 카드",
    "focus_card": "장면의 핵심 문구를 강조 상자로 보여주려고 포인트 카드",
    "quote_card": "인물의 말이나 사연 속 한마디를 살리려고 인용 카드",
    "safe_card": "카드를 그리지 못해 안전한 기본 카드로 대체",
}
NO_IMAGE_REASON = "권리가 확인된 관련 사진·영상이 없고 AI 이미지 생성이 꺼져 있어"


def card_kind(scene: Any) -> str:
    kind = getattr(scene, "content_kind", "") or "subject"
    number = getattr(scene, "key_number", "")
    if kind == "trend" and number:
        return "trend_card"
    if kind in ("number", "trend") and number:
        return "number_card"
    if kind == "comparison" and getattr(scene, "compare_a", "") and getattr(scene, "compare_b", ""):
        return "compare_card"
    if kind == "hook":
        return "hook_card"
    if kind == "conclusion":
        return "summary_card"
    if kind == "story" and any(c in getattr(scene, "narration", "") for c in _SPEECH):
        return "quote_card"
    return "statement_card"


_SPEECH = ("라면서", "라며", "다며", "다고", "라고", "말했", "물었", "\"", "“", "'")


def _card_decision(scene_id: str, scene: Any, requested: str, extra: str = "", kind: str = "") -> VisualDecision:
    kind = kind or card_kind(scene)
    content = getattr(scene, "content_kind", "") or "subject"
    wanted_card = requested in ("text_card", "") or (requested == "chart" and kind in ("trend_card", "number_card"))
    reason = CARD_REASON[kind]
    if content in IMAGE_FIRST and not wanted_card:
        reason = f"{NO_IMAGE_REASON} {reason}"
    if requested in ("stock_image", "stock_video"):
        reason += " · 스톡 연동이 아직 없어 대체"
    if requested == "chart":
        reason += " · 차트 대신 숫자 중심 카드"
    if extra:
        reason += f" · {extra}"
    return VisualDecision(scene_id=scene_id, requested_visual_type=requested, resolved_visual_type=kind,
                          asset_source="internal_generated", rights_status="allowed",
                          rights_reason="앱이 직접 그린 카드라 사용권 문제가 없음", selection_reason=reason,
                          fallback_used=not wanted_card or requested == "chart", show_title=False)


def plan_visuals(scenes: list[Any], uploads: dict[int, Asset], registry: SourceRegistry, *,
                 ai_available: bool, broll: dict[int, str] | None = None,
                 resolved: dict[int, dict[str, Any]] | None = None) -> list[VisualDecision]:
    """장면마다 쓸 화면을 정한다 (파일은 아직 만들지 않는다).

    순서: 내 영상 구간 → 내 업로드 → Source Resolver 가 찾은 권리 확인 자료(영상 구간·사진) → AI 이미지 → 카드.
    """
    broll = broll or {}
    resolved = resolved or {}
    out: list[VisualDecision] = []
    for i, s in enumerate(scenes):
        sid = f"scene_{i + 1:02d}"
        requested = getattr(s, "visual_type", "") or ""
        content = getattr(s, "content_kind", "") or "subject"
        if i in broll:
            out.append(VisualDecision(
                scene_id=sid, requested_visual_type=requested, resolved_visual_type="upload_video",
                asset_path=broll[i], asset_source="user_upload", rights_status="allowed",
                rights_reason="소스 대장에서 영상 사용 가능으로 확인된 내 업로드 영상",
                selection_reason="장면 내용과 맞는 구간을 내 영상에서 골라 사용"))
            continue
        asset = uploads.get(i)
        item = registry.by_path(asset.path) if asset else None
        if asset and item and item.usable_in_video:
            out.append(VisualDecision(
                scene_id=sid, requested_visual_type=requested,
                resolved_visual_type="upload_video_frame" if asset.kind == "video" else "upload_image",
                asset_path=asset.path, asset_source="user_upload", rights_status="allowed",
                rights_reason=f"권리 확인된 업로드 ({item.license})",
                selection_reason=("이 장면에 쓰라고 지정한 파일" if asset.name.lower().startswith("scene")
                                  else "직접 올린 권리 확인 자료를 장면 내용에 맞춰 배치")))
            continue
        found = resolved.get(i)
        found_item = registry.by_path(found["path"]) if found else None
        if found and found_item and found_item.usable_in_video:
            out.append(VisualDecision(
                scene_id=sid, requested_visual_type=requested,
                resolved_visual_type="source_video" if found["kind"] == "video" else "source_image",
                asset_path=found["path"], asset_source=found.get("asset_source", "licensed_source"),
                rights_status="allowed",
                rights_reason=(f"인용(transformative_quote, 목적: {found_item.purpose}) — 출처: {found_item.credit}"
                               if found_item.license == "transformative_quote"
                               else f"{found_item.license}: {found_item.rights_basis}")[:200],
                selection_reason=found.get("reason", "장면에 맞는 권리 확인 공개 자료")))
            continue
        if ai_available and content in IMAGE_FIRST:
            out.append(VisualDecision(
                scene_id=sid, requested_visual_type=requested, resolved_visual_type="ai_image",
                asset_source="ai_generated", rights_status="allowed", rights_reason="앱이 생성하는 이미지",
                selection_reason="인물·대상·이야기처럼 그림으로 보여주기 좋은 장면이라 AI 생성 이미지"))
            continue
        out.append(_card_decision(sid, s, requested))
    _vary_repeats(out)
    return out


def _vary_repeats(decisions: list[VisualDecision]) -> None:
    """연속된 같은 종류 카드를 줄인다.

    문구 카드(핵심·포인트·인용)끼리는 모양을 번갈아 바꾼다. 장면 자기 문구를 그대로 쓰므로 관련성은 유지된다.
    숫자·비교처럼 내용이 정한 카드는 종류를 바꾸지 않고 배치·색만 바꾼다(관련성 우선).
    """
    rotation = ("statement_card", "focus_card", "quote_card")
    for prev, cur in zip(decisions, decisions[1:]):
        if cur.asset_source != "internal_generated" or cur.resolved_visual_type != prev.resolved_visual_type:
            continue
        if cur.resolved_visual_type in rotation:
            nxt = rotation[(rotation.index(cur.resolved_visual_type) + 1) % len(rotation)]
            cur.resolved_visual_type = nxt
            cur.selection_reason = f"{CARD_REASON[nxt]} · 앞 장면과 같은 모양이 이어지지 않게 바꿈"
        else:
            cur.selection_reason += " · 앞 장면과 같은 종류라 다른 배치·색으로 구분"


def _variants(decisions: list[VisualDecision]) -> list[int]:
    out, last, run = [], "", 0
    for d in decisions:
        run = run + 1 if d.resolved_visual_type == last else 0
        last = d.resolved_visual_type
        out.append(run)
    return out


async def materialize(decisions: list[VisualDecision], scenes: list[Any], job_dir: Path, cfg: dict[str, Any],
                      registry: SourceRegistry | None, progress: Callable[[str, int, str], None] = lambda *a: None,
                      *, preview: bool = False) -> list[VisualDecision]:
    """결정대로 장면 이미지 파일을 만든다.

    preview=True: 검토 화면용 미리보기만 만든다 (카드·업로드 사본만, AI 생성·대장 등록 없음).
    """
    w, h = int(cfg["images"]["width"]), int(cfg["images"]["height"])
    img_dir = job_dir / "scenes"
    img_dir.mkdir(parents=True, exist_ok=True)
    provider = None if preview else get_images(cfg)
    retries = int(cfg["images"].get("retries", 2))
    style = (cfg.get("preset") or {}).get("image_style", "")
    variants = _variants(decisions)
    done = 0

    async def card(d: VisualDecision, s: Any, out: Path, variant: int, why: str = "") -> None:
        planned_kind = d.resolved_visual_type if d.resolved_visual_type in cards.CARD_KINDS else ""
        fallback = _card_decision(d.scene_id, s, d.requested_visual_type, why, kind=planned_kind)
        if planned_kind and not why:
            fallback.selection_reason = d.selection_reason   # 반복 방지로 바꾼 이유 등 계획 단계의 설명 유지
        try:
            await asyncio.to_thread(
                cards.render_card, fallback.resolved_visual_type, out, width=w, height=h,
                emphasis=getattr(s, "on_screen_text", ""), key_number=getattr(s, "key_number", ""),
                compare_a=getattr(s, "compare_a", ""), compare_b=getattr(s, "compare_b", ""),
                trend_up=trend_direction(s.narration) != "down", variant=variant, seed=s.narration[:40])
        except Exception as e:  # noqa: BLE001 - 카드도 실패하면 기존 단색 카드
            await asyncio.to_thread(make_fallback_card, getattr(s, "on_screen_text", ""), out, w, h, s.narration[:40])
            fallback.resolved_visual_type, fallback.fallback_used = "safe_card", True
            fallback.selection_reason = f"{CARD_REASON['safe_card']} ({e})"
            fallback.show_title = False
        d.resolved_visual_type, d.asset_source = fallback.resolved_visual_type, fallback.asset_source
        d.rights_status, d.rights_reason = fallback.rights_status, fallback.rights_reason
        d.fallback_used = fallback.fallback_used or bool(why)
        d.selection_reason, d.show_title = fallback.selection_reason, fallback.show_title

    for i, (d, s) in enumerate(zip(decisions, scenes)):
        out = img_dir / (f"preview_{i:02d}.jpg" if preview else f"scene_{i:02d}.jpg")
        if d.resolved_visual_type in ("upload_video", "source_video"):
            done += 1
            continue   # 영상 구간은 렌더가 직접 쓴다
        if d.resolved_visual_type in ("upload_image", "upload_video_frame", "source_image"):
            original = Path(d.asset_path)
            try:
                src = original
                if kind_of(src) == "video":
                    frames = await extract_frames(src, img_dir / "_src", count=1, max_width=w)
                    if not frames:
                        raise RuntimeError("영상에서 장면을 뽑지 못했습니다")
                    src = frames[0]
                await asyncio.to_thread(shutil.copyfile, src, out)
                how = await asyncio.to_thread(cards.fit_image, out, w, h)
                d.selection_reason += " (비율 유지: " + ("가운데 맞춤" if how == "cover" else "흐린 배경 위 원본 전체") + ")"
                if not preview and registry:
                    # 맞춤 가공한 장면 이미지는 원본 업로드의 권리를 그대로 잇는다
                    parent = registry.by_path(original)
                    registry.add(kind="image", origin="derived", path=str(out), title=f"장면 {i + 1}",
                                 rights=parent.model_dump() if parent else None,
                                 parent_id=parent.id if parent else "", used_for=f"scene_{i:02d}")
            except Exception as e:  # noqa: BLE001
                await card(d, s, out, variants[i], why=f"업로드 파일을 쓸 수 없어 대체 ({e})")
        elif d.resolved_visual_type == "ai_image":
            if preview:
                d.asset_path = ""
                d.selection_reason += " (렌더할 때 생성)"
                done += 1
                continue
            made = False
            err = "이미지 생성이 꺼져 있음"
            if provider is not None:
                prompt = s.image_prompt if not style or style.lower() in s.image_prompt.lower() else f"{style}, {s.image_prompt}"
                for attempt in range(retries + 1):
                    try:
                        await provider.generate(prompt, out, w, h)
                        made = True
                        break
                    except Exception as e:  # noqa: BLE001
                        err = str(e)
                        await asyncio.sleep(1.5 * (attempt + 1))
            if made:
                d.asset_path = str(out)
            else:
                await card(d, s, out, variants[i], why=f"AI 이미지 생성 실패로 대체 ({err[:80]})")
        else:
            await card(d, s, out, variants[i])
        if d.resolved_visual_type != "upload_video":
            d.asset_path = str(out)
            if not preview and registry and d.asset_source not in ("user_upload", "licensed_source", "quote_source"):
                registry.add(kind="image", origin="generated", path=str(out), title=f"장면 {i + 1}",
                             used_for=f"scene_{i:02d}")
        if not preview and registry:
            item = registry.by_path(d.asset_path)
            if item and not item.usable_in_video:
                d.rights_status, d.rights_reason = "blocked", "소스 대장에서 사용 불가 — 렌더 가드가 막는다"
        done += 1
        progress("images", int(10 + 85 * done / max(1, len(decisions))), f"장면 {i + 1} 화면: {d.resolved_visual_type}")
    return decisions


MANIFEST = "visuals.json"


def save_manifest(job_dir: Path, decisions: list[VisualDecision]) -> Path:
    """장면별 화면 결정 기록 (설계도의 visual_decision 과 같은 내용을 한 파일로)."""
    import json
    out = job_dir / MANIFEST
    tmp = job_dir / (MANIFEST + ".tmp")
    tmp.write_text(json.dumps([d.model_dump() for d in decisions], ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out)
    return out


def preview_uploads(uploads: list[Asset], count: int) -> dict[int, Asset]:
    """검토 화면 미리보기용: 장면 지정 파일(scene_NN_*)만 쓴다 (내용 매칭 분석은 렌더 때 한 번만)."""
    from .assets import pinned_scene
    out: dict[int, Asset] = {}
    for a in uploads:
        idx = pinned_scene(a.name)
        if idx is not None and 0 <= idx < count and idx not in out:
            out[idx] = a
    return out
