"""TTS provider 공통 인터페이스."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

from ..media import probe_duration
from ..models import Word


class TTSProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def synthesize(self, text: str, out_path: Path, voice: str) -> list[Word] | None:
        """text를 out_path(mp3)에 저장. 단어 타임스탬프를 알면 반환, 모르면 None."""


def split_words(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", text.strip()) if w]


async def fallback_words(text: str, audio_path: Path) -> list[Word]:
    """타임스탬프가 없는 provider용: 글자 수 비율로 단어 시간을 배분."""
    dur = await probe_duration(audio_path)
    words = split_words(text)
    if not words:
        return []
    weights = [len(w) + 0.6 for w in words]  # 단어 사이 짧은 쉼 반영
    total = sum(weights)
    out: list[Word] = []
    t = 0.0
    for w, wt in zip(words, weights):
        d = dur * wt / total
        out.append(Word(text=w, start=round(t, 3), end=round(t + d, 3)))
        t += d
    return out


def align_words(text: str, boundaries: list[Word] | None) -> list[Word]:
    """TTS 단어 경계를 실제 나레이션 단어(text.split())에 다시 맞춘다. 시간은 경계에서, 글자는 나레이션에서.

    Edge TTS 경계는 문장 끝을 넘어 두 단어를 한 토큰으로 묶거나("일. 나") 일부 음절을 빠뜨리기도 한다
    ("머지"). 그대로 자막에 쓰면 화면 글자가 나레이션과 달라지므로, 글자(문자·숫자만) 단위로 대응시켜
    나레이션 단어마다 맞은 글자들의 시간 범위를 쓴다. 한 토큰 안의 글자 시간은 토큰 길이를 글자 수로 나눠
    배분하고, 하나도 맞지 않은 단어는 앞뒤 단어 사이 시간을 글자 수 비율로 나눠 갖는다.
    """
    from difflib import SequenceMatcher

    names = split_words(text)
    if not names:
        return []
    bounds = [b for b in boundaries or [] if b.end >= b.start]
    if not bounds:
        return [Word(text=n, start=0.0, end=0.0) for n in names]

    # 나레이션 글자 → 단어 번호
    n_chars: list[str] = []
    n_owner: list[int] = []
    for wi, name in enumerate(names):
        for ch in name:
            if ch.isalnum():
                n_chars.append(ch)
                n_owner.append(wi)
    # 경계 글자 → (시작, 끝) 시간: 토큰 길이를 그 토큰의 글자 수로 나눈다
    b_chars: list[str] = []
    b_time: list[tuple[float, float]] = []
    for b in bounds:
        chars = [ch for ch in b.text if ch.isalnum()]
        step = (b.end - b.start) / len(chars) if chars else 0.0
        for j, ch in enumerate(chars):
            b_chars.append(ch)
            b_time.append((b.start + step * j, b.start + step * (j + 1)))

    spans: list[list[float] | None] = [None] * len(names)
    sm = SequenceMatcher(None, n_chars, b_chars, autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            wi = n_owner[blk.a + k]
            s, e = b_time[blk.b + k]
            if spans[wi] is None:
                spans[wi] = [s, e]
            else:
                spans[wi][0] = min(spans[wi][0], s)
                spans[wi][1] = max(spans[wi][1], e)

    # 맞은 단어의 시작이 앞 단어보다 앞서지 않게만 정리 (경계 시간 자체는 그대로 둔다)
    prev_start = 0.0
    for sp in spans:
        if sp is not None:
            sp[0] = max(sp[0], prev_start)
            sp[1] = max(sp[1], sp[0])
            prev_start = sp[0]

    # 하나도 맞지 않은 단어 묶음은 앞 단어 끝 ~ 뒤 단어 시작 사이를 글자 수 비율로 나눈다
    first, last = bounds[0].start, max(b.end for b in bounds)
    i = 0
    while i < len(names):
        if spans[i] is not None:
            i += 1
            continue
        j = i
        while j < len(names) and spans[j] is None:
            j += 1
        lo = spans[i - 1][1] if i > 0 else first
        hi = max(spans[j][0] if j < len(names) else last, lo)
        weights = [len(names[k]) for k in range(i, j)]
        total = sum(weights) or 1
        t = lo
        for k, wt in zip(range(i, j), weights):
            d = (hi - lo) * wt / total
            spans[k] = [t, t + d]
            t += d
        i = j

    return [Word(text=n, start=round(sp[0], 3), end=round(sp[1], 3)) for n, sp in zip(names, spans)]
