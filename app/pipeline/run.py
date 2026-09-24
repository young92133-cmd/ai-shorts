"""파이프라인 오케스트레이터. 웹 UI 와 CLI 가 공유한다."""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

from ..config import load_config, load_presets, merge_options
from . import article as articlemod
from . import assets as assetmod
from . import broll as brollmod
from . import clips as clipmod
from . import comments as commentmod, reference as refmod, research, script as scriptmod, youtube
from .assets import kind_of
from .images import get_images
from .images.base import make_fallback_card, resize_cover
from .media import concat_audio, extract_frames, has_audio, probe_duration, require_ffmpeg
from .models import ResearchDoc, SceneAudio, SceneVisual, Script, SourcedImage, Word
from . import timeline as timelinemod
from .comment_layout import clean_slots, place as place_comment
from .render import make_thumbnail, render_clips
from .subtitles import build_ass, words_to_lines
from .tts import get_tts

ProgressFn = Callable[[str, int, str], None]
ReviewFn = Callable[[Script, dict[str, Any]], Awaitable[tuple[Script, dict[str, Any]]]]

STAGES = ["research", "script", "tts", "images", "render", "done"]


def _noop_progress(stage: str, pct: int, msg: str) -> None:
    print(f"[{stage:8s} {pct:3d}%] {msg}", flush=True)


def _find_bgm(cfg: dict[str, Any]) -> Path | None:
    name = (cfg.get("preset") or {}).get("bgm")
    bgm_dir = Path(cfg["paths"]["assets"]) / "bgm"
    if name and (bgm_dir / name).exists():
        return bgm_dir / name
    cands = sorted(bgm_dir.glob("*.mp3")) if bgm_dir.exists() else []
    return cands[0] if cands else None


def _write_meta(job_dir: Path, titles: list[str], description: str, hashtags: list[str], sources: list[str]) -> None:
    tags = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
    text = "\n".join([
        "[제목 후보]", *[f"{i + 1}. {t}" for i, t in enumerate(titles)], "",
        "[설명]", description, "", tags, "",
        "[출처]", *sources,
    ])
    (job_dir / "meta.txt").write_text(text, encoding="utf-8")
    (job_dir / "meta.json").write_text(json.dumps(
        {"titles": titles, "description": description, "hashtags": hashtags, "sources": sources},
        ensure_ascii=False, indent=2), encoding="utf-8")


def _apply_voice(cfg: dict[str, Any], choices: dict[str, Any]) -> None:
    """검토 화면 ⑤ 에서 고른 TTS·목소리를 적용한다 (TTS 는 승인 뒤에 돌므로 이때 바꿔도 된다)."""
    provider, voice = choices.get("tts_provider"), choices.get("voice")
    if provider and provider != cfg["tts"]["provider"]:
        cfg["tts"]["provider"] = provider
        if not voice:
            voice = ((cfg.get("preset") or {}).get("voice") or {}).get(provider) \
                or cfg["tts"].get("voices", {}).get(provider, "")
    if voice:
        cfg["tts"]["voice"] = voice


async def _synthesize_scenes(cfg: dict[str, Any], script: Script, job_dir: Path, progress: ProgressFn) -> tuple[Path, list[SceneAudio]]:
    tts = get_tts(cfg)
    voice = cfg["tts"]["voice"]
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    parts: list[Path] = []
    words_per_scene: list[list[Word]] = []
    for i, scene in enumerate(script.scenes):
        p = audio_dir / f"scene_{i:02d}.mp3"
        words = await tts.synthesize(scene.narration, p, voice)
        parts.append(p)
        words_per_scene.append(words or [])
        progress("tts", int(10 + 80 * (i + 1) / len(script.scenes)), f"음성 합성 {i + 1}/{len(script.scenes)}")

    narration = job_dir / "narration.mp3"
    gap = float(cfg["video"].get("scene_gap", 0.25))
    offsets = await concat_audio(parts, narration, gap=gap)
    scenes: list[SceneAudio] = []
    for i, (p, off, words) in enumerate(zip(parts, offsets, words_per_scene)):
        dur = await probe_duration(p)
        abs_words = [Word(text=w.text, start=round(w.start + off, 3), end=round(w.end + off, 3)) for w in words]
        scenes.append(SceneAudio(index=i, path=str(p), duration=dur, words=abs_words, offset=off))
    return narration, scenes


async def _prepare_visuals(cfg: dict[str, Any], script: Script, visuals: list[SceneVisual],
                          job_dir: Path, progress: ProgressFn) -> list[Path]:
    """장면별 비주얼을 실제 이미지 파일로 만든다.

    upload/sourced 는 있는 파일을 1080x1920 으로 맞추고, generated 만 AI 로 생성한다.
    어떤 단계가 실패해도 대체 카드로 내려가 영상은 반드시 완성된다.
    """
    w, h = int(cfg["images"]["width"]), int(cfg["images"]["height"])
    retries = int(cfg["images"].get("retries", 2))
    style = (cfg.get("preset") or {}).get("image_style", "")
    img_dir = job_dir / "scenes"
    img_dir.mkdir(exist_ok=True)

    need_gen = [v for v in visuals if v.kind == "generated"]
    provider = get_images(cfg) if need_gen else None
    if need_gen and provider is None:
        progress("images", 0, f"AI 생성 꺼짐 - 빈 장면 {len(need_gen)}개는 대체 카드로 만듭니다")
    sem = asyncio.Semaphore(getattr(provider, "concurrency", 3) if provider else 3)
    total = len(visuals)
    done = 0

    def bump(msg: str) -> None:
        nonlocal done
        done += 1
        progress("images", int(10 + 85 * done / total), f"{msg} {done}/{total}")

    async def one(v: SceneVisual) -> Path:
        i = v.scene_index
        scene = script.scenes[i]
        out = img_dir / f"scene_{i:02d}.jpg"

        # 1) 이미 파일이 있는 경우 (첨부 / 기사 이미지)
        if v.kind in ("upload", "sourced") and v.path:
            src = Path(v.path)
            try:
                if kind_of(src) == "video":
                    frames = await extract_frames(src, img_dir / "_src", count=1, max_width=w)
                    if not frames:
                        raise RuntimeError("영상에서 프레임을 뽑지 못했습니다")
                    src = frames[0]
                await asyncio.to_thread(shutil.copyfile, src, out)
                await asyncio.to_thread(resize_cover, out, w, h)
                bump(v.note or "비주얼")
                return out
            except Exception as e:  # noqa: BLE001
                progress("images", 0, f"장면 {i + 1} {v.note} 사용 실패 → AI 생성으로 대체 ({e})")
                v.kind, v.credit = "generated", ""

        # 2) AI 생성
        prompt = scene.image_prompt
        full_prompt = f"{style}, {prompt}" if style and style.lower() not in prompt.lower() else prompt
        async with sem:
            for attempt in range(retries + 1):
                try:
                    if provider is None:
                        raise RuntimeError("이미지 provider 없음")
                    await provider.generate(full_prompt, out, w, h)
                    bump("이미지 생성")
                    return out
                except Exception as e:  # noqa: BLE001
                    if attempt == retries:
                        progress("images", 0, f"장면 {i + 1} 이미지 실패 → 대체 카드 사용 ({e})")
                        v.kind, v.note = "card", "대체 카드"
                        make_fallback_card("", out, w, h, seed=prompt)  # 키워드는 자막 Title 로 표시됨
                        bump("대체 카드")
                        return out
                    await asyncio.sleep(2 * (attempt + 1))
        return out

    return list(await asyncio.gather(*(one(v) for v in visuals)))


async def run_pipeline(
    job_dir: Path,
    mode: str,
    input_text: str,
    cfg: dict[str, Any],
    progress: ProgressFn = _noop_progress,
    review: ReviewFn | None = None,
    until: str = "done",
    clip_mode: bool = False,
    instructions: str = "",
    style: dict[str, Any] | None = None,
    visual_mode: str = "",
    reference_name: str = "",
) -> dict[str, Any]:
    """mode: topic | url | auto. 결과 dict 에 산출물 경로를 담아 돌려준다.

    style 이 주어지면 그 지침을 따르고, 없으면 소재를 분석해 구성을 자동으로 정한다.
    visual_mode: images | broll | clip. 비우면 프리셋 기본값 → 자동 분석 결과 순.
    """
    require_ffmpeg()
    job_dir.mkdir(parents=True, exist_ok=True)
    preset = cfg["preset"]
    llm = cfg["llm"]
    vcfg = cfg["video"]
    fonts_dir = Path(cfg["paths"]["assets"]) / "fonts"
    sub_cfg = preset.get("subtitle", {})
    visual_mode = visual_mode or preset.get("visual_mode", "")
    if clip_mode:
        visual_mode = "clip"
    result: dict[str, Any] = {"job_dir": str(job_dir), "mode": mode, "style": (style or {}).get("name", "")}

    # ---------- 1. 리서치 / 입력 분석 ----------
    docs: list[ResearchDoc] = []
    sourced: list[SourcedImage] = []
    extra_context = ""
    topic = input_text

    urls = articlemod.split_urls(input_text) if mode == "url" else []
    article_urls = [u for u in urls if not articlemod.is_youtube(u)]
    youtube_urls = [u for u in urls if articlemod.is_youtube(u)]
    reference_path: Path | None = None
    reference_lines: list[str] = []
    reference_query = ""

    # 유튜브가 아닌 링크(기사·커뮤니티 글)가 섞여 있으면 기사 모드
    if mode == "upload":
        reference_path = job_dir / "uploads" / Path(reference_name).name
        if not reference_name or not reference_path.is_file() or kind_of(reference_path) != "video":
            raise RuntimeError("참고 영상 파일이 없습니다. 영상 파일을 올린 뒤 다시 시도해 주세요.")
        progress("research", 5, "업로드 영상의 음성과 장면을 분석하는 중")
        brief, doc, words = await refmod.analyze_uploaded_video(
            llm, reference_path, job_dir / "reference", input_text,
            log=lambda m: progress("research", 55, m))
        topic, reference_query = brief.topic, brief.search_query
        docs = [doc]
        reference_lines = youtube.words_to_lines(words)
        result["reference"] = brief.model_dump()
        extra_context = "업로드 영상에서 확인된 내용만 출발점으로 쓰고, 새 자료와 대조해 새로운 관점의 대본을 쓰세요."
        progress("research", 70, "관련 자료 찾는 중")
        found = await research.research_topic(reference_query, log=lambda m: progress("research", 80, m))
        docs.extend(found)

    elif mode == "url" and article_urls and not youtube_urls:
        progress("research", 5, f"링크 {len(article_urls)}개 분석 중")
        docs, sourced = await articlemod.fetch_articles(
            article_urls, job_dir / "sourced", with_images=True,
            log=lambda m: progress("research", 40, m))
        if not docs:
            raise RuntimeError("링크에서 본문을 읽지 못했습니다. 주소를 확인해 주세요.")
        topic = docs[0].title
        result["source"] = {"urls": article_urls, "titles": [d.title for d in docs]}
        result["sourced_images"] = [s.model_dump() for s in sourced]
        extra_context = ("아래 기사들의 내용을 바탕으로 쇼츠 대본을 쓰세요. "
                         "기사 문장을 그대로 읽지 말고 쇼츠 호흡으로 재구성하세요.")
        progress("research", 90, f"본문 {len(docs)}건, 이미지 {len(sourced)}장 수집")

    elif mode == "url":
        progress("research", 5, "유튜브 정보 가져오는 중")
        input_text = youtube_urls[0] if youtube_urls else input_text
        info = await youtube.fetch_info(input_text)
        result["source"] = info
        progress("research", 20, f"'{info['title']}' 자막 가져오는 중")
        words = await youtube.fetch_transcript(input_text, job_dir)
        if not words:
            progress("research", 30, "자막이 없어 오디오를 내려받아 음성 인식합니다 (시간이 걸립니다)")
            audio = await youtube.download_media(input_text, job_dir, audio_only=True)
            words = await youtube.transcribe(audio)
        (job_dir / "transcript.json").write_text(
            json.dumps([w.model_dump() for w in words], ensure_ascii=False), encoding="utf-8")

        if visual_mode == "clip":
            progress("script", 10, "하이라이트 구간 고르는 중")
            cplan = await scriptmod.plan_clips(llm, preset, info["title"], youtube.words_to_lines(words),
                                               instructions, style)
            segments = clipmod.normalize_segments(cplan.segments, info["duration"])
            (job_dir / "clip_plan.json").write_text(cplan.model_dump_json(indent=2), encoding="utf-8")
            _write_meta(job_dir, cplan.titles, cplan.description, cplan.hashtags, [info["webpage_url"]])
            result["clip_plan"] = cplan.model_dump()
            result["segments"] = segments
            if until in ("research", "script"):
                return result

            progress("images", 10, "원본 영상 다운로드 중")
            source = await youtube.download_media(input_text, job_dir, audio_only=False)
            progress("render", 10, "자막·렌더링 중")
            new_words = clipmod.retime_words(words, segments)
            ass = build_ass(new_words, job_dir / "subs.ass", vcfg["width"], vcfg["height"], font=vcfg["font"],
                            size=int(sub_cfg.get("size", 64)), highlight=sub_cfg.get("highlight", "#FFD400"),
                            outline=sub_cfg.get("outline", "#000000")) if vcfg.get("subtitles", True) else None
            final = await render_clips(source, segments, job_dir / "final.mp4", ass_path=ass, bgm=_find_bgm(cfg),
                                       width=vcfg["width"], height=vcfg["height"], fps=vcfg["fps"],
                                       bgm_volume=float(vcfg.get("bgm_volume", 0.1)) * 0.6, fonts_dir=fonts_dir)
            await make_thumbnail(final, job_dir / "thumb.jpg")
            result.update(video=str(final), thumb=str(job_dir / "thumb.jpg"), meta=str(job_dir / "meta.txt"))
            progress("done", 100, "완료")
            return result

        topic = info["title"]
        docs = [ResearchDoc(title=info["title"], url=info["webpage_url"], text=youtube.words_to_text(words)[:12000])]
        extra_context = (f"원본 영상 채널: {info['channel']}\n원본 설명: {info['description'][:800]}\n"
                         "위 영상의 핵심 내용을 새로운 관점으로 재구성한 쇼츠 대본을 쓰세요. 영상 내용을 그대로 읽지 마세요.")

    elif mode == "auto":
        progress("research", 5, "지금 뜨는 키워드 수집 중")
        kws = await research.hot_keywords(log=lambda m: progress("research", 8, m))
        if not kws:
            raise RuntimeError("트렌드 키워드를 가져오지 못했습니다. 주제를 직접 입력해 주세요.")
        if input_text.strip():
            kws = [k for k in kws if input_text.strip() in k] or kws
        pick = await scriptmod.pick_trend(llm, preset, kws, instructions)
        progress("research", 25, f"선택된 키워드: {pick.keyword} ({pick.reason})")
        topic = pick.keyword
        result["trend"] = pick.model_dump()
        docs = await research.research_topic(pick.search_query, log=lambda m: progress("research", 60, m))

    else:  # topic
        progress("research", 5, "자료 검색 중")
        suffix = preset.get("research_queries_suffix", "")
        query = f"{input_text} {suffix}".strip()
        docs = await research.research_topic(query, log=lambda m: progress("research", 60, m))

    result["topic"] = topic
    result["docs"] = [{"title": d.title, "url": d.url} for d in docs]
    progress("research", 100, f"리서치 완료 ({len(docs)}건)")
    if until == "research":
        return result

    # ---------- 2. 제작 방향 (자동 모드) ----------
    plan = None
    if not style:
        progress("script", 5, "소재 분석해서 구성 정하는 중")
        try:
            plan = await scriptmod.make_plan(llm, preset, topic, docs, int(vcfg["target_seconds"]), instructions)
            result["plan"] = plan.model_dump()
            progress("script", 8, f"구성: {plan.structure} ({plan.scene_count}장면)")
            if not visual_mode:
                visual_mode = plan.visual_mode
        except Exception as e:  # noqa: BLE001
            progress("script", 8, f"구성 분석 건너뜀 ({e})")

    # ---------- 3. 대본 ----------
    style_note = f" / 스타일: {style['name']}" if style else ""
    progress("script", 10, f"대본 작성 중 ({llm['provider']} / {llm['model']}{style_note})")
    script = await scriptmod.write_script(llm, preset, topic, docs, int(vcfg["target_seconds"]),
                                          extra_context, instructions, style, plan)
    (job_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    progress("script", 80, f"대본 {len(script.scenes)}장면, {len(script.full_narration())}자")
    # Show actual candidate sources/comments before the user approves the edit.
    broll_sources: list[Any] = []
    comment_candidates: list[dict[str, Any]] = []
    if visual_mode == "broll":
        progress("script", 84, "연관 영상 후보 찾는 중")
        query = reference_query or f"{topic} {preset.get('research_queries_suffix', '')}".strip()
        try:
            if reference_path:
                from .models import SourceVideo
                broll_sources.append(SourceVideo(url="", title=f"내 영상: {reference_path.name}",
                                                 duration=await probe_duration(reference_path),
                                                 channel="내 파일", path=str(reference_path)))
            remaining = max(0, int(vcfg.get("broll_max_sources", 4)) - len(broll_sources))
            if remaining:
                broll_sources.extend(await brollmod.gather_sources(youtube_urls, query, remaining,
                                      log=lambda m: progress("script", 86, m)))
        except Exception as exc:  # a missing search result must not prevent use of the local reference
            progress("script", 86, f"연관 영상 검색 실패: {exc}")
        candidate_urls = youtube_urls + [s.url for s in broll_sources if s.url]
        comment_candidates = await commentmod.fetch_candidates(candidate_urls,
                                  log=lambda m: progress("script", 89, m))
        result["source_candidates"] = [s.model_dump() for s in broll_sources]
        result["comment_candidates"] = comment_candidates
    # 스타일이 참고 영상에서 댓글 자리를 찾아 뒀으면, 좋아요 많은 댓글을 그 수만큼 미리 골라 둔다
    comment_slots = clean_slots((style or {}).get("comment_slots"))
    suggested = [c["id"] for c in sorted(comment_candidates, key=lambda c: -int(c.get("likes") or 0))
                 [:min(2, len(comment_slots))]]
    result["suggested_comment_ids"] = suggested
    choices: dict[str, Any] = {"comment_ids": suggested}
    if review:
        script, choices = await review(script, {
            "topic": topic,
            "source_candidates": result.get("source_candidates", []),
            "comment_candidates": comment_candidates,
            "suggested_comment_ids": suggested,
            "reference": result.get("reference"),
        })
        (job_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
        _apply_voice(cfg, choices)
    if broll_sources and "source_indexes" in choices:
        chosen = set(choices["source_indexes"])
        broll_sources = [s for i, s in enumerate(broll_sources) if i in chosen]
    selected_comments = [c for c in comment_candidates if c["id"] in set(choices.get("comment_ids", []))][:2]
    result["selected_comments"] = selected_comments
    # 화면에 쓴 기사 이미지의 출처를 설명란 출처 목록에 합친다
    all_sources = list(dict.fromkeys(
        [*script.sources, *[s.page_url for s in sourced if s.page_url],
         *[c["url"] for c in selected_comments]]))
    _write_meta(job_dir, script.titles, script.description, script.hashtags, all_sources)
    result["final_sources"] = all_sources
    result["script"] = script.model_dump()
    progress("script", 100, "대본 확정")
    if until == "script":
        return result

    # ---------- 4. TTS ----------
    progress("tts", 5, f"음성 합성 ({cfg['tts']['provider']} / {cfg['tts']['voice']})")
    narration, scene_audio = await _synthesize_scenes(cfg, script, job_dir, progress)
    total = await probe_duration(narration)
    result["narration"] = str(narration)
    result["duration"] = total
    progress("tts", 100, f"나레이션 {total:.1f}초")
    if until == "tts":
        return result

    gap = float(vcfg.get("scene_gap", 0.25))
    durations = [s.duration + gap for s in scene_audio]
    durations[-1] = scene_audio[-1].duration + 0.5   # 마지막 장면 여운

    # ---------- 5-B. 영상 짜깁기 (broll) ----------
    broll_picks: list[Any] = []
    if visual_mode == "broll":
        try:
            progress("images", 5, "선택한 소스 영상 준비 중")
            if not broll_sources:
                raise RuntimeError("쓸 만한 소스 영상을 찾지 못했습니다")

            progress("images", 20, f"소스 {len(broll_sources)}개 자막 확인 중")
            timelines = await brollmod.load_timelines(broll_sources, job_dir / "broll",
                                                      log=lambda m: progress("images", 30, m))
            if reference_path:
                for i, source in enumerate(broll_sources):
                    if source.path == str(reference_path):
                        timelines[i] = reference_lines
            progress("images", 45, "장면별 화면 고르는 중")
            max_per = float(vcfg.get("broll_max_per_source", 15))
            bplan = await brollmod.match_broll(llm, script, durations, broll_sources, timelines, max_per)
            broll_picks = brollmod.normalize_picks(bplan, broll_sources, durations, max_per,
                                                   log=lambda m: progress("images", 50, m))
            if not any(broll_picks):
                raise RuntimeError("대본에 맞는 화면을 찾지 못했습니다")

            progress("images", 55, "소스 영상 내려받는 중 (시간이 걸립니다)")
            await brollmod.download_sources(broll_sources, broll_picks, job_dir / "broll",
                                            log=lambda m: progress("images", 70, m))
            broll_picks = brollmod.drop_failed(broll_picks, broll_sources)
            if not any(broll_picks):
                raise RuntimeError("소스 영상을 내려받지 못했습니다")
            (job_dir / "broll_plan.json").write_text(bplan.model_dump_json(indent=2), encoding="utf-8")
            result["broll"] = {"sources": [s.model_dump() for s in broll_sources],
                               "picks": [p.model_dump() if p else None for p in broll_picks]}
            # 실제로 쓴 영상 출처를 설명란에 추가
            all_sources = list(dict.fromkeys(
                [*all_sources, *brollmod.source_urls(broll_sources, broll_picks)]))
            _write_meta(job_dir, script.titles, script.description, script.hashtags, all_sources)
            result["final_sources"] = all_sources
        except Exception as e:  # noqa: BLE001
            progress("images", 75, f"짜깁기 실패 - 이미지 모드로 전환합니다 ({e})")
            visual_mode, broll_picks, broll_sources = "images", [], []

    # ---------- 5. 비주얼 (첨부 → 기사 이미지 → AI 생성 → 카드) ----------
    progress("images", 78, "장면별 비주얼 정하는 중")
    uploads = await assetmod.load_assets(job_dir / "uploads",
                                         log=lambda m: progress("images", 80, m))
    if reference_path:
        uploads = [a for a in uploads if Path(a.path) != reference_path]
    if uploads:
        await assetmod.describe_assets(uploads, log=lambda m: progress("images", 82, m))
    visuals = await assetmod.resolve_visuals(llm, script.scenes, uploads, sourced,
                                             log=lambda m: progress("images", 84, m))

    # 짜깁기로 채워진 장면은 이미지를 만들 필요가 없다
    covered = {p.scene_index for p in broll_picks if p}
    for v in visuals:
        if v.scene_index in covered:
            pick = broll_picks[v.scene_index]
            v.kind, v.path = "broll", ""
            v.credit = brollmod.credit_for(pick, broll_sources)
            v.note = f"소스 {pick.source_index + 1} {pick.start:.0f}~{pick.end:.0f}초"

    need_image = [v for v in visuals if v.kind != "broll"]
    images_by_scene: dict[int, Path] = {}
    if need_image:
        progress("images", 86, f"이미지 준비 {len(need_image)}장 ({cfg['images']['provider']})")
        made = await _prepare_visuals(cfg, script, need_image, job_dir, progress)
        images_by_scene = {v.scene_index: p for v, p in zip(need_image, made)}
    result["images"] = [str(p) for p in images_by_scene.values()]
    result["visuals"] = [v.model_dump() for v in visuals]
    progress("images", 100, "비주얼 완료")
    if until == "images":
        return result

    # ---------- 6. 자막 + 렌더 ----------
    # 렌더 재료를 timeline.json 에 먼저 저장한다. 완성 후 자막·댓글만 고쳐 다시 렌더하거나
    # CapCut 으로 내보낼 때 이 파일만 쓴다.
    progress("render", 5, "자막 생성")
    use_broll = any(broll_picks)
    tl_scenes: list[dict[str, Any]] = []
    for i, (dur, sc, v) in enumerate(zip(durations, script.scenes, visuals)):
        pick = broll_picks[i] if use_broll and i < len(broll_picks) else None
        if pick:
            sv = broll_sources[pick.source_index]
            src = Path(sv.path)
            visual = {"kind": "video", "path": src, "src_start": pick.start,
                      "has_audio": await has_audio(src), "source_url": sv.url}
        else:
            visual = {"kind": "image", "path": images_by_scene[i]}
        # 기사·첨부 이미지를 쓴 장면에는 해당 구간 동안 출처를 표시한다
        tl_scenes.append({"duration": dur, "title": sc.on_screen_text, "credit": v.credit, "visual": visual})
    # 고른 댓글: 스타일의 댓글 자리가 있으면 그 흐름대로, 없으면 둘째 장면부터 한 장면에 하나씩 3.5초
    tl_comments = []
    total_dur = sum(durations)
    for i, c in enumerate(selected_comments):
        slot = place_comment(comment_slots, i, total_dur)
        if slot:
            at, end, y = slot
        else:
            at = scene_audio[min(i + 1, len(scene_audio) - 1)].offset
            end, y = at + 3.5, None
        tc = timelinemod.text_comment(c["id"], c["text"], at, end, c.get("url", ""))
        if y is not None:
            tc["y"] = y
        tl_comments.append(tc)
    bgm_volume = float(vcfg.get("bgm_volume", 0.1)) * (0.6 if use_broll else 1.0)
    tl = timelinemod.build_timeline(
        job_dir, width=vcfg["width"], height=vcfg["height"], fps=vcfg["fps"],
        mode="broll" if use_broll else "slideshow", narration=narration, bgm=_find_bgm(cfg),
        bgm_volume=bgm_volume, source_volume=float(vcfg.get("broll_source_volume", 0.12)),
        transition=float(vcfg.get("transition", 0.4)), scenes=tl_scenes,
        lines=words_to_lines([s.words for s in scene_audio]),
        subtitle_style={"font": vcfg["font"], "size": int(sub_cfg.get("size", 64)),
                        "highlight": sub_cfg.get("highlight", "#FFD400"),
                        "outline": sub_cfg.get("outline", "#000000")},
        subtitles_enabled=bool(vcfg.get("subtitles", True)), titles_enabled=bool(vcfg.get("titles", True)),
        comments=tl_comments, comment_slots=comment_slots)
    timelinemod.save(job_dir, tl)
    result["timeline"] = timelinemod.FILE

    progress("render", 15, "ffmpeg 렌더링 중 (1~3분)")
    final = await timelinemod.render_timeline(tl, job_dir, job_dir / "final.mp4", fonts_dir)
    await make_thumbnail(final, job_dir / "thumb.jpg", at=0.5)
    result.update(video=str(final), thumb=str(job_dir / "thumb.jpg"), meta=str(job_dir / "meta.txt"))
    progress("done", 100, "완료")
    return result


async def rerender(job_dir: Path, cfg: dict[str, Any], progress: ProgressFn = _noop_progress) -> dict[str, Any]:
    """timeline.json 으로 영상만 다시 만든다 (⑦ 자막·댓글 수정 후). LLM·TTS 는 부르지 않는다.

    새 파일로 렌더한 뒤 성공했을 때만 final.mp4 를 바꾼다. 실패해도 기존 영상은 남는다.
    """
    require_ffmpeg()
    tl = timelinemod.load(job_dir)
    progress("render", 10, "자막·댓글을 적용해서 다시 렌더링 중 (1~3분)")
    tmp = job_dir / "final_new.mp4"
    tmp.unlink(missing_ok=True)
    await timelinemod.render_timeline(tl, job_dir, tmp, Path(cfg["paths"]["assets"]) / "fonts")
    final = job_dir / "final.mp4"
    tmp.replace(final)
    progress("render", 90, "썸네일 만드는 중")
    await make_thumbnail(final, job_dir / "thumb.jpg", at=0.5)
    progress("done", 100, "다시 만들기 완료")
    return {"video": str(final), "thumb": str(job_dir / "thumb.jpg"), "duration": timelinemod.total_duration(tl)}


# ---------- CLI ----------

def _cli() -> None:
    ap = argparse.ArgumentParser(description="AI 쇼츠 생성 CLI")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--topic", help="주제 텍스트")
    g.add_argument("--url", help="유튜브 URL 또는 기사·글 링크 (여러 개면 공백/줄바꿈으로 구분)")
    g.add_argument("--auto", action="store_true", help="핫이슈 자동 선택")
    ap.add_argument("--preset", default="daily", help="engineering | entertainment | politics | daily")
    ap.add_argument("--clip", action="store_true", help="URL 모드에서 원본 클립 재편집")
    ap.add_argument("--until", default="done", choices=STAGES, help="이 단계까지만 실행")
    ap.add_argument("--tts", help="edge | openai | elevenlabs | typecast")
    ap.add_argument("--images", help="pollinations | fal | openai")
    ap.add_argument("--llm", help="claude | openai | anthropic")
    ap.add_argument("--model", help="모델 ID (예: claude-sonnet-5, gpt-5-mini)")
    ap.add_argument("--seconds", type=int, help="목표 길이(초)")
    ap.add_argument("--job", help="출력 폴더 이름 (기본: 자동)")
    ap.add_argument("--instructions", default="", help="이번 영상에만 적용할 추가 지침")
    ap.add_argument("--style", help="저장된 스타일 지침 id (비우면 자동 분석 모드)")
    ap.add_argument("--visual", choices=["images", "broll", "clip"], help="비주얼 모드")
    ap.add_argument("--uploads", help="첨부할 이미지·영상이 들어있는 폴더")
    args = ap.parse_args()

    cfg = load_config()
    presets = load_presets(cfg)
    if args.preset not in presets:
        sys.exit(f"프리셋 없음: {args.preset} (가능: {', '.join(presets)})")
    run_cfg = merge_options(cfg, presets[args.preset], {
        "tts_provider": args.tts, "image_provider": args.images, "llm_provider": args.llm, "llm_model": args.model,
        "target_seconds": args.seconds,
    })

    import datetime
    mode = "url" if args.url else "auto" if args.auto else "topic"
    text = args.url or args.topic or ""
    job = args.job or datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{mode}"
    job_dir = Path(cfg["paths"]["output"]) / job

    style = None
    if args.style:
        from .styles import find_style, load_styles
        style = find_style(cfg, args.style)
        if not style:
            sys.exit(f"스타일 없음: {args.style} (가능: {', '.join(load_styles(cfg)) or '없음'})")

    if args.uploads:
        src = Path(args.uploads)
        if not src.is_dir():
            sys.exit(f"폴더가 아닙니다: {src}")
        job_dir.mkdir(parents=True, exist_ok=True)
        dst = job_dir / "uploads"
        dst.mkdir(exist_ok=True)
        n = 0
        for p in src.iterdir():
            if p.is_file() and assetmod.kind_of(p):
                shutil.copyfile(p, dst / p.name)
                n += 1
        print(f"첨부 {n}개 복사됨")

    result = asyncio.run(run_pipeline(job_dir, mode, text, run_cfg, until=args.until, clip_mode=args.clip,
                                      instructions=args.instructions, style=style, visual_mode=args.visual or ""))
    print(json.dumps({k: v for k, v in result.items() if k not in ("script", "docs")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli()
