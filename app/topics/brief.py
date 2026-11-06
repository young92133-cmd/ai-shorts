"""승인된 주제를 쇼츠 make 지시문으로 바꾼다. 검증된 사실·기준일·출처만 넣고 LLM 은 부르지 않는다."""
from __future__ import annotations

import re

from .schema import Topic, now
from .verification import eligible


def source_label(doc) -> str:
    """출처 표기: 주소 대신 '발행처 「자료 제목」'. 제목 끝의 사이트 메뉴 경로는 뗀다."""
    from .discovery import publisher
    title = re.split(r'\s+\|\s+', doc.title or '')[0].strip()
    owner = re.split(r'\s*:\s*', doc.title)[-1].strip() if ':' in (doc.title or '') else publisher(doc.url)
    return f'{owner} 「{title}」' if title else owner


def shorts_brief(topic: Topic, docs, *, at=None) -> dict:
    """make(topic=title, instructions=...) 에 그대로 넘길 묶음. 수치는 검증된 사실 문장 안의 것만 쓰게 한다."""
    if not eligible(topic, at):
        raise ValueError('핵심 주장 검증·기한·중복 조건을 먼저 확인해 주세요')
    facts = [f for f in topic.facts if f.verification == 'verified']
    if not facts:
        raise ValueError('제작에 사용할 검증된 사실이 없습니다')
    labels = {e.evidence_id: source_label(e) for e in docs}
    lines = []
    for f in facts:
        claim = f.claim if f.kind == 'fact' else f'[{"전망" if f.kind == "forecast" else "의견"}] {f.claim}'
        scope = ', '.join(x for x in (f'{f.as_of} 발표' if f.as_of else '', f'적용: {f.applies_to}' if f.applies_to else '') if x)
        cited = ' / '.join(dict.fromkeys(labels[c.evidence_id] for c in f.citations if c.evidence_id in labels))
        lines.append('- ' + claim + (f' ({scope})' if scope else '') + (f' — 출처: {cited}' if cited else ''))
    direction = topic.angle or '선택하기 전 근거와 조건을 함께 확인하게 돕는다.'
    instructions = '\n'.join([
        '아래는 사람이 승인한 검증된 사실이다. 수치·날짜·기관명은 이 목록에 있는 것만 쓰고 새로 지어내지 마라.',
        '전망·의견 표시가 붙은 문장은 사실처럼 단정하지 마라.',
        *lines,
        f'방향: {direction}',
        f'시청자: {", ".join(topic.target_audience)}',
    ])
    return {'topic_id': topic.topic_id, 'title': topic.title, 'instructions': instructions,
            'fact_ids': [f.fact_id for f in facts], 'sources': [{'title': e.title, 'url': e.url} for e in docs],
            'provenance': {'model': 'none', 'created_at': at or now(), 'config_version': 'topic-strategy-v1',
                           'verification': topic.verification, 'score': topic.score.model_dump() if topic.score else None,
                           'direction': direction}}
