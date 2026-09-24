"""Understand an uploaded reference video before researching and editing a short."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from ..config import env
from .llm import ask_structured
from .media import extract_frames, has_audio, probe_duration, run_ffmpeg
from .models import ResearchDoc, Word
from .vision import describe_all
from .youtube import transcribe, words_to_text


class ReferenceBrief(BaseModel):
    topic: str = Field(description="참고 영상이 실제로 다루는 인물·사건·개념을 포함한 정확한 주제")
    summary: str = Field(description="영상에서 확인한 핵심 내용과 전개를 3~5문장으로 요약")
    search_query: str = Field(description="같은 인물·사건의 관련 영상을 찾을 구체적인 검색어")


SYSTEM = """당신은 업로드된 참고 영상을 분석하는 쇼츠 편집자입니다.
음성 전사와 화면 설명에서 실제로 확인된 정보만 사용하세요. 파일명과 사용자의 메모는
검색 힌트일 뿐 사실의 근거로 취급하지 마세요. 영상에 없는 인물·사건을 지어내지 마세요.
검색어는 추측성 표현을 빼고 해당 주제를 찾을 수 있게 구체적으로 쓰세요."""

FRAME_PROMPT = (
    "영상에서 뽑은 한 장면입니다. 화면에 실제로 보이는 행동·장소·자료와 읽을 수 있는 자막이나 글자를 "
    "한국어로 간단히 설명하세요. 텍스트 근거 없이 실존 인물의 이름을 추측하지 마세요. "
    'JSON 만 출력: {"description":"...","keywords":["..."]}'
)


async def _transcribe_audio(audio: Path, use_openai: bool) -> list[Word]:
    """Use GPT's transcription API only when GPT was selected; otherwise local Whisper."""
    key = env("OPENAI_API_KEY")
    if not use_openai:
        return await transcribe(audio)
    if not key:
        raise RuntimeError("GPT 음성 인식에 OpenAI API 키가 필요합니다.")
    async with httpx.AsyncClient(timeout=300) as client:
        with audio.open("rb") as source:
            response = await client.post("https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                data={"model": "whisper-1", "response_format": "verbose_json",
                      "timestamp_granularities[]": "word"},
                files={"file": (audio.name, source, "audio/mpeg")})
        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI 음성 인식 오류 {response.status_code}: {response.text[:200]}")
    data = response.json()
    words = [Word(text=str(w.get("word", "")).strip(), start=float(w["start"]), end=float(w["end"]))
             for w in data.get("words", []) if w.get("word") and "start" in w and "end" in w]
    if words:
        return words
    return [Word(text=str(s.get("text", "")).strip(), start=float(s["start"]), end=float(s["end"]))
            for s in data.get("segments", []) if s.get("text") and "start" in s and "end" in s]


async def analyze_uploaded_video(llm: dict, video: Path, workdir: Path,
                                 hint: str = "", log=print) -> tuple[ReferenceBrief, ResearchDoc, list[Word]]:
    """Sample the full timeline and transcribe speech; never silently analyze just one frame."""
    workdir.mkdir(parents=True, exist_ok=True)
    duration = await probe_duration(video)
    if duration <= 0:
        raise RuntimeError("업로드 영상을 읽지 못했습니다.")
    frames = await extract_frames(video, workdir / "frames", count=min(8, max(3, int(duration // 12))), max_width=640)
    frame_provider = "gemini" if env("GEMINI_API_KEY") else (
        "openai" if llm.get("provider") == "openai" and env("OPENAI_API_KEY") else "")
    descriptions = await describe_all(frames, log=log, provider=frame_provider,
                                     model=llm.get("model", ""), prompt=FRAME_PROMPT) if frames and frame_provider else []
    visuals = [f"[{i + 1}/{len(frames)}] {d.description}"
               for i, d in enumerate(descriptions) if d and d.description]

    words: list[Word] = []
    transcript_error = ""
    if await has_audio(video):
        audio = workdir / "reference.mp3"
        await run_ffmpeg(["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(audio)])
        try:
            words = await _transcribe_audio(audio, llm.get("provider") == "openai")
        except Exception as exc:  # voice recognition is optional when vision works
            transcript_error = str(exc)
            log(f"음성 인식 실패: {exc}")

    if not words and not visuals:
        reason = transcript_error or "영상에서 음성이나 화면 내용을 읽지 못했습니다."
        raise RuntimeError(f"참고 영상 분석에 실패했습니다. {reason} 음성 인식 또는 Gemini 화면 분석이 필요합니다.")

    text = words_to_text(words)[:12000]
    evidence = "\n".join(visuals)
    prompt = (f"파일명: {video.name}\n사용자 메모: {hint[:500]}\n길이: {duration:.1f}초\n"
              f"\n음성 전사:\n{text or '(없음)'}\n\n시간순 화면 설명:\n{evidence or '(없음)'}")
    brief = await ask_structured(llm, SYSTEM, prompt, ReferenceBrief)
    if not brief.topic.strip() or not brief.search_query.strip():
        raise RuntimeError("참고 영상의 주제 또는 검색어를 정하지 못했습니다.")
    (workdir / "analysis.json").write_text(json.dumps({
        "brief": brief.model_dump(), "duration": duration, "frames": [str(p) for p in frames],
        "transcript": [w.model_dump() for w in words], "visuals": visuals,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    doc = ResearchDoc(title=brief.topic, url="", text=f"{brief.summary}\n\n음성 전사: {text}\n화면: {evidence}"[:15000])
    log(f"참고 영상 분석 완료: {brief.topic}")
    return brief, doc, words
