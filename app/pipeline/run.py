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
from . import bench_auto
from . import assets as assetmod
from . import blueprint as blueprintmod
from . import broll as brollmod
from . import clips as clipmod
from . import comments as commentmod, reference as refmod, research, script as scriptmod, script_split, youtube
from .assets import kind_of
from .images import get_images
from . import visuals as visualsmod
from .llm import safe_error
from .media import concat_audio, trim_edge_silence, has_audio, probe_duration, require_ffmpeg
from .models import PlannedScript, ResearchDoc, SceneAudio, SceneVisual, Script, SourcedImage, Word
from . import timeline as timelinemod
from .sources import SourceRegistry, guard_timeline
from .comment_layout import clean_slots, place as place_comment
from .render import make_thumbnail
from .subtitles import words_to_lines
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


class TTSFailed(RuntimeError):
    """장면 음성을 끝내 만들지 못했다. 가짜 길이로 대신하지 않고 렌더를 멈춘다."""


MIN_SCENE_AUDIO = 0.2   # 이보다 짧은 음성 파일은 실패로 본다


def _fit_words(words: list[Word] | None, raw: float, dur: float, lead: float) -> list[Word] | None:
    """무음을 잘라낸 뒤 단어 시간을 새 음성 파일에 맞춘다.

    - TTS 가 준 실제 단어 경계: 잘라낸 앞부분(lead)만큼 당긴다.
    - 단어 경계가 없어 파일 전체 길이에 글자 수로 나눈 추정값(fallback_words): 새 길이에 맞게 비율로 줄인다.
      (추정값은 무음까지 포함한 길이로 나눈 것이라, 그냥 당기면 뒤쪽 자막이 음성보다 늦어진다)
    """
    if not words or (not lead and abs(raw - dur) < 0.02):
        return words
    spread = words[0].start < 0.01 and abs(words[-1].end - raw) < 0.05
    if spread and raw > 0:
        k = dur / raw
        return [Word(text=w.text, start=round(w.start * k, 3), end=round(w.end * k, 3)) for w in words]
    return [Word(text=w.text, start=round(max(0.0, w.start - lead), 3), end=round(max(0.0, w.end - lead), 3))
            for w in words]


async def _synthesize_one(tts: Any, text: str, out: Path, voice: str, attempts: int,
                          wait: float, log: Callable[[str], None] = lambda m: None,
                          ) -> tuple[list[Word] | None, float]:
    """장면 하나의 음성을 만들고 실제 길이를 잰다. 실패하면 재시도, 끝내 실패하면 마지막 원인을 올린다.

    TTS 가 붙인 앞뒤 무음은 잘라낸다(말 중간의 쉼은 유지). 돌려주는 길이는 잘라낸 뒤의 실측값이고,
    단어 시간도 잘라낸 만큼 앞으로 당긴다.
    """
    last = ""
    for attempt in range(1, attempts + 1):
        try:
            out.unlink(missing_ok=True)
            words = await tts.synthesize(text, out, voice)
            if not out.is_file() or out.stat().st_size == 0:
                raise RuntimeError("음성 파일이 만들어지지 않았습니다")
            try:
                raw = await probe_duration(out)
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"음성 길이를 측정하지 못했습니다 ({e})") from e
            lead = 0.0
            try:
                lead = await trim_edge_silence(out)
            except Exception as e:  # noqa: BLE001 - 무음 정리는 품질 개선일 뿐, 실패하면 원본 그대로 쓴다
                log(f"앞뒤 무음 정리를 건너뜁니다 ({e})")
            try:
                dur = await probe_duration(out)
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"음성 길이를 측정하지 못했습니다 ({e})") from e
            if not dur or dur < MIN_SCENE_AUDIO:
                raise RuntimeError(f"음성 길이가 비정상입니다 ({dur}초)")
            return _fit_words(words, raw, dur, lead), dur
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}" if not isinstance(e, RuntimeError) else str(e)
            if attempt < attempts:
                await asyncio.sleep(wait * attempt)
    raise TTSFailed(last)


async def _synthesize_scenes(cfg: dict[str, Any], script: Script, job_dir: Path, progress: ProgressFn) -> tuple[Path, list[SceneAudio]]:
    """장면별 음성 생성 → 실제 길이 측정 → 장면 사이 여백을 넣어 나레이션 한 파일로 잇는다 (2C).

    어느 장면이든 재시도 끝에 실패하면 TTSFailed 로 멈춘다. 잘못된 타임라인으로 렌더하지 않는다.
    """
    tts = get_tts(cfg)
    voice = cfg["tts"]["voice"]
    attempts = 1 + max(0, int(cfg["tts"].get("retries", 2)))
    wait = float(cfg["tts"].get("retry_wait", 1.5))
    audio_dir = job_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    parts: list[Path] = []
    words_per_scene: list[list[Word]] = []
    measured: list[float] = []
    for i, scene in enumerate(script.scenes):
        p = audio_dir / f"scene_{i:02d}.mp3"
        try:
            words, dur = await _synthesize_one(tts, scene.narration, p, voice, attempts, wait,
                                               log=lambda m: progress("tts", 0, m))
        except TTSFailed as e:
            head = " ".join(scene.narration.split())[:30]
            raise TTSFailed(f"{i + 1}번 장면 음성 생성 실패({attempts}회 시도): {e} · 내레이션: '{head}…'") from e
        parts.append(p)
        words_per_scene.append(words or [])
        measured.append(dur)
        progress("tts", int(10 + 80 * (i + 1) / len(script.scenes)),
                 f"음성 합성 {i + 1}/{len(script.scenes)} · 실제 {dur:.2f}초")

    narration = job_dir / "narration.mp3"
    gap = float(cfg["video"].get("scene_gap", 0.25))
    try:
        # 끝 여운까지 나레이션에 넣어 두면 최종 영상 길이가 설계도 길이와 정확히 같아진다
        offsets = await concat_audio(parts, narration, gap=gap, tail=blueprintmod.TAIL)
    except Exception as e:  # noqa: BLE001
        raise TTSFailed(f"장면 음성을 하나로 잇지 못했습니다: {e}") from e
    scenes: list[SceneAudio] = []
    for i, (p, off, words, dur) in enumerate(zip(parts, offsets, words_per_scene, measured)):
        # 단어 시간은 그 장면 음성 안에 있어야 한다 (자막이 다음 장면으로 넘어가지 않게)
        abs_words = [Word(text=w.text, start=round(min(w.start, dur) + off, 3), end=round(min(w.end, dur) + off, 3))
                     for w in words]
        scenes.append(SceneAudio(index=i, path=str(p), duration=dur, words=abs_words, offset=off))
    return narration, scenes


async def _usable_uploads(job_dir: Path, registry: SourceRegistry, reference_path: Path | None,
                         progress: ProgressFn) -> list:
    """장면 화면 후보가 될 수 있는 업로드: 소스 대장에서 영상 사용 가능으로 확인된 것만."""
    uploads = await assetmod.load_assets(job_dir / "uploads", log=lambda m: progress("images", 80, m))
    if reference_path:
        uploads = [a for a in uploads if Path(a.path) != reference_path]
    return [a for a in uploads if (registry.by_path(a.path) and registry.by_path(a.path).usable_in_video)]


async def _preview_visuals(script: Script, job_dir: Path, cfg: dict[str, Any], registry: SourceRegistry,
                           reference_path: Path | None, progress: ProgressFn) -> list[dict[str, Any]]:
    """검토 화면용 장면 화면 미리보기 (2D). 카드·지정 업로드만 그리고 AI 생성·대장 등록은 하지 않는다.

    렌더 때 다시 정하므로, 미리보기가 실패해도 제작은 계속한다.
    """
    try:
        uploads = await _usable_uploads(job_dir, registry, reference_path, lambda *a: None)
        pinned = visualsmod.preview_uploads(uploads, len(script.scenes))
        plan = visualsmod.plan_visuals(script.scenes, pinned, registry, ai_available=get_images(cfg) is not None)
        plan = await visualsmod.materialize(plan, script.scenes, job_dir, cfg, None, preview=True)
        return [d.model_dump() for d in plan]
    except Exception as e:  # noqa: BLE001
        progress("script", 90, f"화면 미리보기를 만들지 못했습니다 (렌더 때 다시 정합니다): {e}")
        return []


def _has_licensed_video(registry: SourceRegistry) -> bool:
    """영상 화면에 써도 되는(권리 확인된) 사용자 영상이 있는가. 분석 전용 참고 영상은 제외."""
    return any(i.kind == "video" and i.usable_in_video and i.used_for != "reference"
               for i in registry.items.values())


async def _choose_benchmark(benchmark: str, *, mode: str, llm: dict[str, Any], topic: str, docs: list[ResearchDoc],
                            seconds: int, source_info: str, instructions: str, style: dict[str, Any] | None,
                            registry: SourceRegistry, job_dir: Path, progress: ProgressFn,
                            ) -> tuple[dict[str, Any] | None, str, int | None]:
    """조사 뒤 · 대본 앞: 시청 질문과 8개 구조 점수 → 구조 선택 → 대본 프롬프트 블록.

    반환: (결정 기록, 대본 프롬프트 블록, 장면 수). 결정은 benchmark_decision.json 에도 저장한다.
    보충 조사로 찾은 자료는 docs 에 그대로 더한다.
    """
    if benchmark == "off":
        return None, "", None
    if style and benchmark == "auto":
        decision = {"mode": "not_applicable", "requested": benchmark,
                    "selection_reason": "저장된 스타일 지침을 지정해 스타일 구성을 따릅니다"}
        bench_auto.save_decision(job_dir, decision)
        return decision, "", None
    integ = bench_auto.load_integration()
    forced = None if benchmark == "auto" else bench_auto.validate_choice(benchmark, integ)
    has_video = _has_licensed_video(registry)
    progress("script", 3, "시청자가 볼 이유와 어울리는 콘텐츠 구조를 분석하는 중")
    input_kind = {"url": "reference_url", "upload": "uploaded_reference_video"}.get(mode, mode)
    cbrief = None
    try:
        cbrief = await bench_auto.analyze_brief(llm, topic, docs, integ, input_kind=input_kind,
                                                source_info=source_info, has_licensed_video=has_video,
                                                instructions=instructions)
    except Exception as e:  # noqa: BLE001 - 구조 분석이 실패해도 안전한 정보형 구조로 계속한다
        progress("script", 4, f"구조 분석 실패 - 안전한 정보형 구조로 진행합니다 ({safe_error(e)})")
    decision = bench_auto.route(cbrief, integ, forced=forced, has_licensed_video=has_video)
    index, candidate, scored = bench_auto.pick_candidate(cbrief)
    decision.update(bench_auto.brief_summary(cbrief, index, scored))
    profile_id = decision["selected_profile"]
    roles = bench_auto.scene_roles(integ["profiles"][profile_id], seconds)
    decision["scene_roles"] = roles
    query = bench_auto.followup_query(cbrief, profile_id)
    if query:
        progress("script", 6, f"{profile_id} 구조에 필요한 근거 보충 조사: {query}")
        try:
            known = {d.url for d in docs}
            extra = [d for d in await research.research_topic(query, max_docs=3, log=lambda m: progress("script", 6, m))
                     if d.url not in known]
        except Exception as e:  # noqa: BLE001
            extra = []
            progress("script", 6, f"보충 조사 실패 ({e})")
        for doc in extra:
            if doc.url:
                registry.add(kind="article", origin="url", url=doc.url, title=doc.title, used_for="script_research")
        docs.extend(extra)
        decision["research_followup"] = {"query": query, "added_docs": [d.url for d in extra]}
    block = bench_auto.compose_prompt_block(profile_id, integ, decision, cbrief, candidate, seconds)
    if decision.get("research_followup", {}).get("added_docs"):
        block += "- 보충 조사 자료(위 사실 목록 뒤에 추가된 자료)는 본문에서 확인되는 내용만 쓰세요.\n"
    bench_auto.save_decision(job_dir, decision)
    score = decision["candidate_scores"].get(profile_id)
    progress("script", 8, f"구조 선택: {decision['profile_name']} ({profile_id}, {score}점, {decision['mode']})"
                          + (f" · 질문: {decision['viewer_question']}" if decision.get("viewer_question") else ""))
    return decision, block, len(roles)


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
    upload_rights: dict[str, dict[str, Any]] | None = None,
    script_in: Script | None = None,
    benchmark: str = "off",
) -> dict[str, Any]:
    """mode: topic | url | auto | upload | script | resume(승인된 script_in 으로 이어서). 결과 dict 에 산출물 경로를 담아 돌려준다.

    style 이 주어지면 그 지침을 따르고, 없으면 소재를 분석해 구성을 자동으로 정한다.
    visual_mode: images | broll | clip. 비우면 프리셋 기본값 → 자동 분석 결과 순.
    benchmark: off(기존 V1 그대로) | auto(8개 구조 자동 선택) | profile id(강제 지정).
    """
    require_ffmpeg()
    job_dir.mkdir(parents=True, exist_ok=True)
    registry = SourceRegistry(job_dir)
    registry.save()
    for file in (job_dir / "uploads").glob("*"):
        if file.is_file() and kind_of(file):
            registry.add(kind=kind_of(file), origin="upload", path=str(file), title=file.name,
                         rights=(upload_rights or {}).get(file.name), used_for="reference" if file.name == reference_name else "candidate")
    preset = cfg["preset"]
    llm = cfg["llm"]
    vcfg = cfg["video"]
    fonts_dir = Path(cfg["paths"]["assets"]) / "fonts"
    sub_cfg = preset.get("subtitle", {})
    visual_mode = visual_mode or preset.get("visual_mode", "")
    if mode == "script":
        visual_mode = "images"  # 권리 미확인 외부 자료를 자동 탐색하지 않는다.
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
    source_info = ""   # benchmark 분석용 참고 원본 정보 (제목·채널·요약)

    # 유튜브가 아닌 링크(기사·커뮤니티 글)가 섞여 있으면 기사 모드
    if mode == "script":
        progress("research", 100, "입력한 완성 대본을 사용합니다. 별도 자료 조사는 하지 않습니다.")
    elif mode == "resume":
        # 승인된 대본으로 이어서 만든다 (factory resume). 조사·기획·대본 작성을 다시 하지 않는다.
        if script_in is None:
            raise ValueError("이어서 만들 대본이 없습니다.")
        topic = script_in.topic
        if reference_name:
            reference_path = job_dir / "uploads" / Path(reference_name).name
        progress("research", 100, "저장된 대본으로 이어서 만듭니다. 자료 조사와 대본 작성은 다시 하지 않습니다.")
    elif mode == "upload":
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
        source_info = f"업로드 참고 영상 요약: {brief.summary}"
        extra_context = "업로드 영상에서 확인된 내용만 출발점으로 쓰고, 새 자료와 대조해 새로운 관점의 대본을 쓰세요."
        progress("research", 70, "관련 자료 찾는 중")
        found = await research.research_topic(reference_query, log=lambda m: progress("research", 80, m))
        docs.extend(found)

    elif mode == "url" and article_urls and not youtube_urls:
        progress("research", 5, f"링크 {len(article_urls)}개 분석 중")
        docs, sourced = await articlemod.fetch_articles(
            article_urls, job_dir / "sourced", with_images=False,
            log=lambda m: progress("research", 40, m))
        if not docs:
            raise RuntimeError("링크에서 본문을 읽지 못했습니다. 주소를 확인해 주세요.")
        topic = docs[0].title
        result["source"] = {"urls": article_urls, "titles": [d.title for d in docs]}
        source_info = "참고 기사: " + " / ".join(d.title for d in docs)
        result["sourced_images"] = [s.model_dump() for s in sourced]
        extra_context = ("아래 기사들의 내용을 바탕으로 쇼츠 대본을 쓰세요. "
                         "기사 문장을 그대로 읽지 말고 쇼츠 호흡으로 재구성하세요.")
        progress("research", 90, f"본문 {len(docs)}건, 이미지 {len(sourced)}장 수집")

    elif mode == "url":
        progress("research", 5, "유튜브 정보 가져오는 중")
        input_text = youtube_urls[0] if youtube_urls else input_text
        info = await youtube.fetch_info(input_text)
        registry.add(kind="video", origin="url", url=input_text, title=info.get("title", ""),
                     used_for="script_research")
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

            raise ValueError("유튜브 원본 클립은 사용 권한이 확인되지 않아 제작할 수 없습니다. 권리 증빙을 입력한 내 영상을 업로드해 주세요.")

        topic = info["title"]
        docs = [ResearchDoc(title=info["title"], url=info["webpage_url"], text=youtube.words_to_text(words)[:12000])]
        source_info = (f"참고 유튜브 제목: {info['title']}\n채널: {info['channel']}\n"
                       f"설명: {info['description'][:500]}")
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
    for doc in docs:
        if doc.url:
            registry.add(kind="article", origin="url", url=doc.url, title=doc.title, used_for="script_research")
    progress("research", 100, f"리서치 완료 ({len(docs)}건)")
    if until == "research":
        return result

    # ---------- 1-B. Benchmark 구조 자동 선택 ----------
    bench_decision: dict[str, Any] | None = None
    bench_block, bench_scenes = "", None
    if mode == "resume":
        bench_decision = bench_auto.load_decision(job_dir)   # 다시 고르지 않는다
    elif mode == "script":
        if benchmark != "off":
            bench_decision = {"mode": "not_applicable", "requested": benchmark,
                              "selection_reason": "완성 대본 입력은 문장을 바꾸지 않으므로 구조를 적용하지 않습니다"}
            bench_auto.save_decision(job_dir, bench_decision)
    else:
        bench_decision, bench_block, bench_scenes = await _choose_benchmark(
            benchmark, mode=mode, llm=llm, topic=topic, docs=docs, seconds=int(vcfg["target_seconds"]),
            source_info=source_info, instructions=instructions, style=style, registry=registry,
            job_dir=job_dir, progress=progress)
    if bench_decision:
        result["benchmark"] = bench_decision
        result["docs"] = [{"title": d.title, "url": d.url} for d in docs]

    # ---------- 2. 제작 방향 (자동 모드) ----------
    plan = None
    if not style and mode not in ("script", "resume") and not bench_block:
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
    if mode == "resume":
        script = PlannedScript.model_validate(script_in.model_dump())
        result["plan_method"] = "resumed"
        progress("script", 70, f"승인된 대본 {len(script.scenes)}장면을 그대로 사용")
    elif mode == "script":
        progress("script", 10, "완성 대본을 이야기 흐름에 따라 장면으로 나누는 중")
        script, split_method = await script_split.split_finished_script(
            llm, input_text, preset=preset, instructions=instructions)
        topic = script.topic
        result["topic"] = topic
        result["split_method"] = split_method
        if split_method == "fallback":
            progress("script", 75, "AI 장면 분석이 어려워 문장 경계 기준으로 나눴습니다. 검토 화면에서 확인해 주세요.")
    else:
        progress("script", 10, f"대본 작성 중 ({llm['provider']} / {llm['model']}{style_note})")
        script = await scriptmod.write_script(llm, preset, topic, docs, int(vcfg["target_seconds"]),
                                              extra_context, instructions, style, plan,
                                              benchmark_block=bench_block, benchmark_scenes=bench_scenes)
        # 2D: 자동 대본에도 장면 역할·내용 성격·짧은 강조문구를 붙인다 (나레이션은 그대로)
        progress("script", 70, "장면별 화면 계획 세우는 중")
        script, plan_method = await script_split.annotate_script(llm, script, preset=preset,
                                                                 instructions=instructions)
        result["plan_method"] = plan_method
        if plan_method == "rules":
            progress("script", 75, "AI 장면 분석이 어려워 내용 규칙으로 화면을 계획했습니다.")
        if bench_block:
            # 장면 역할·내용 성격·강조문구 길이를 선택된 구조에 맞춘다 (나레이션은 그대로)
            script = bench_auto.apply_scene_plan(script, bench_decision["selected_profile"],
                                                 bench_auto.load_integration(), int(vcfg["target_seconds"]))
            bench_decision["scene_roles"] = [s.beat_role for s in script.scenes]
            bench_decision["quality"] = bench_auto.quality_check(bench_decision, script)
            bench_auto.save_decision(job_dir, bench_decision)
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
        for source in broll_sources:
            if source.url:
                registry.add(kind="video", origin="url", url=source.url, title=source.title,
                             used_for="broll_candidate")
        candidate_urls = youtube_urls + [s.url for s in broll_sources if s.url]
        comment_candidates = await commentmod.fetch_candidates(candidate_urls,
                                  log=lambda m: progress("script", 89, m))
        for comment in comment_candidates:
            if comment.get("url"):
                registry.add(kind="comment", origin="url", url=comment["url"],
                             title=comment.get("text", "")[:80], used_for="script_research")
        result["source_candidates"] = [{**s.model_dump(), "usable_in_video": bool(
            (registry.by_path(s.path) if s.path else registry.by_url(s.url)) and
            (registry.by_path(s.path) if s.path else registry.by_url(s.url)).usable_in_video)}
            for s in broll_sources]
        result["comment_candidates"] = comment_candidates
    # 스타일이 참고 영상에서 댓글 자리를 찾아 뒀으면, 좋아요 많은 댓글을 그 수만큼 미리 골라 둔다
    comment_slots = clean_slots((style or {}).get("comment_slots"))
    suggested = [c["id"] for c in sorted(comment_candidates, key=lambda c: -int(c.get("likes") or 0))
                 [:min(2, len(comment_slots))]]
    result["suggested_comment_ids"] = suggested
    choices: dict[str, Any] = {"comment_ids": suggested}
    # 검토 화면용 장면 설계 초안 (예상 시간). 직접 대본·AI 대본 두 경로 모두 만든다.
    draft = blueprintmod.from_script(script, gap=float(vcfg.get("scene_gap", 0.25)),
                                     width=int(vcfg["width"]), height=int(vcfg["height"]),
                                     fps=int(vcfg["fps"]))
    blueprintmod.save(job_dir, draft)
    visual_preview = await _preview_visuals(script, job_dir, cfg, registry, reference_path, progress)
    result["visual_plan"] = visual_preview
    if review:
        script, choices = await review(script, {
            "visual_plan": visual_preview,
            "topic": topic,
            "source_candidates": result.get("source_candidates", []),
            "comment_candidates": comment_candidates,
            "suggested_comment_ids": suggested,
            "reference": result.get("reference"),
            "blueprint": draft.model_dump(),
            "split_method": result.get("split_method", ""),
        })
        (job_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
        _apply_voice(cfg, choices)
        registry = SourceRegistry(job_dir)  # 검토 화면에서 새로 올린 장면 파일 반영
    if broll_sources and "source_indexes" in choices:
        chosen = set(choices["source_indexes"])
        broll_sources = [s for i, s in enumerate(broll_sources) if i in chosen]
    permitted = []
    for source in broll_sources:
        item = registry.by_path(source.path) if source.path else registry.by_url(source.url)
        if item and item.usable_in_video and source.path:
            permitted.append(source)
        else:
            progress("images", 0, f"'{source.title}'은 영상 사용 권한이 없어 화면 소재에서 제외합니다.")
    broll_sources = permitted
    selected_comments = [c for c in comment_candidates if c["id"] in set(choices.get("comment_ids", []))][:2]
    result["selected_comments"] = selected_comments
    # 화면에 쓴 기사 이미지의 출처를 설명란 출처 목록에 합친다
    all_sources = list(dict.fromkeys(
        [*script.sources, *[s.page_url for s in sourced if s.page_url],
         *[c["url"] for c in selected_comments]]))
    _write_meta(job_dir, script.titles, script.description, script.hashtags, all_sources)
    result["final_sources"] = all_sources
    result["script"] = script.model_dump()
    blueprint = blueprintmod.from_script(script, gap=float(vcfg.get("scene_gap", 0.25)),
                                           width=int(vcfg["width"]), height=int(vcfg["height"]),
                                           fps=int(vcfg["fps"]))
    blueprintmod.save(job_dir, blueprint)
    result["blueprint"] = blueprint.model_dump()
    progress("script", 100, "대본 확정")
    if until == "script":
        return result

    # ---------- 4. TTS ----------
    progress("tts", 5, f"음성 합성 ({cfg['tts']['provider']} / {cfg['tts']['voice']})")
    narration, scene_audio = await _synthesize_scenes(cfg, script, job_dir, progress)
    try:
        total = await probe_duration(narration)
    except Exception as e:  # noqa: BLE001
        raise TTSFailed(f"완성된 나레이션 길이를 측정하지 못했습니다: {e}") from e
    result["narration"] = str(narration)
    registry.add(kind="audio", origin="generated", path=str(narration), title="나레이션", used_for="narration")
    result["duration"] = total

    # ---------- 4-B. 실제 음성 길이로 장면 시간 확정 (2C) ----------
    gap = float(vcfg.get("scene_gap", 0.25))
    blueprint = blueprintmod.align_to_audio(blueprint, scene_audio, gap=gap)
    blueprintmod.save(job_dir, blueprint)
    result["blueprint"] = blueprint.model_dump()
    for s in blueprint.scenes:
        progress("tts", 95, f"장면 {s.index + 1}: 예상 {s.estimated_duration:.2f}초 → 실제 음성 "
                            f"{s.actual_tts_duration:.2f}초 ({s.timeline_start:.2f}~{s.timeline_end:.2f})")
    progress("tts", 100, f"나레이션 {total:.1f}초 · 영상 길이 {blueprint.actual_duration:.1f}초로 확정")
    if bench_decision and bench_decision.get("selected_profile"):
        bench_decision["quality"] = bench_auto.quality_check(bench_decision, script, blueprint.actual_duration)
        bench_auto.save_decision(job_dir, bench_decision)
        result["benchmark"] = bench_decision
    if until == "tts":
        return result

    # 장면별 화면 길이는 확정된 설계도가 기준이다 (실제 음성 + 장면 사이 여백, 마지막은 여운)
    durations = blueprintmod.scene_durations(blueprint)

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

    # ---------- 5. 장면별 화면 자동 선택 (2D) ----------
    # 권리 확인 업로드 → 내 영상 구간 → AI 이미지(켜져 있을 때) → 내용 성격별 카드 → 안전 카드
    progress("images", 78, "장면별 화면 자동 선택 중")
    uploads = await _usable_uploads(job_dir, registry, reference_path, progress)
    if uploads:
        await assetmod.describe_assets(uploads, log=lambda m: progress("images", 82, m))
    by_scene = await assetmod.plan_assets(llm, uploads, script.scenes, log=lambda m: progress("images", 84, m))
    broll_cover = {p.scene_index: broll_sources[p.source_index].path for p in broll_picks if p}
    decisions = visualsmod.plan_visuals(script.scenes, by_scene, registry,
                                        ai_available=get_images(cfg) is not None, broll=broll_cover)
    decisions = await visualsmod.materialize(decisions, script.scenes, job_dir, cfg, registry, progress)
    images_by_scene = {i: Path(d.asset_path) for i, d in enumerate(decisions)
                       if d.resolved_visual_type != "upload_video"}
    visuals: list[SceneVisual] = []
    for i, d in enumerate(decisions):
        credit = ""
        if d.resolved_visual_type == "upload_video":
            credit = brollmod.credit_for(broll_picks[i], broll_sources)
        elif d.asset_source == "user_upload":
            item = registry.by_path(d.asset_path)
            credit = item.credit if item else ""
        kind = {"user_upload": "upload", "ai_generated": "generated"}.get(d.asset_source, "card")
        visuals.append(SceneVisual(scene_index=i, kind="broll" if d.resolved_visual_type == "upload_video" else kind,
                                   path=d.asset_path, credit=credit, note=d.resolved_visual_type))
    # 설계도·manifest 에 무엇을 왜 골랐는지 남긴다 (2C 시간은 그대로)
    for scene, d in zip(blueprint.scenes, decisions):
        scene.visual_decision = d
    blueprintmod.save(job_dir, blueprint)
    visualsmod.save_manifest(job_dir, decisions)
    result["blueprint"] = blueprint.model_dump()
    result["visual_plan"] = [d.model_dump() for d in decisions]
    result["images"] = [str(p) for p in images_by_scene.values()]
    result["visuals"] = [v.model_dump() for v in visuals]
    kinds = ", ".join(f"{i + 1}:{d.resolved_visual_type}" for i, d in enumerate(decisions))
    progress("images", 100, f"장면 화면 결정 완료 ({kinds})")
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
        # 첨부 자료를 쓴 장면에는 해당 구간 동안 출처를 표시한다.
        # 카드는 강조문구를 이미 크게 그리므로 상단 키워드를 겹쳐 띄우지 않는다.
        title = sc.on_screen_text if decisions[i].show_title else ""
        tl_scenes.append({"duration": dur, "title": title, "credit": v.credit, "visual": visual})
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
        mode="broll" if use_broll else "slideshow", narration=narration, bgm=None,
        bgm_volume=bgm_volume, source_volume=float(vcfg.get("broll_source_volume", 0.12)),
        transition=float(vcfg.get("transition", 0.4)), scenes=tl_scenes,
        lines=words_to_lines([s.words for s in scene_audio]),
        subtitle_style={"font": vcfg["font"], "size": int(sub_cfg.get("size", 64)),
                        "highlight": sub_cfg.get("highlight", "#FFD400"),
                        "outline": sub_cfg.get("outline", "#000000")},
        subtitles_enabled=bool(vcfg.get("subtitles", True)), titles_enabled=bool(vcfg.get("titles", True)),
        comments=tl_comments, comment_slots=comment_slots)
    # 타인 댓글 후보는 대본 검토에만 남기고 영상에는 싣지 않는다.
    tl["comments"] = []
    blueprintmod.check_timeline(blueprint, tl)   # 설계도와 어긋난 타임라인으로는 렌더하지 않는다
    guard_timeline(job_dir, tl)
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
    guard_timeline(job_dir, tl)
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
