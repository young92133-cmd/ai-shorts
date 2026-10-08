"""Build a factual story and adapt it to the existing CarouselPlan. No duplicate renderer."""
from __future__ import annotations

from ..carousel.characters import get_character
from ..carousel.schema import MasterContent, MasterFact, CardPage, ComicPage, ComicBeat, CarouselPlan
from .schema import Topic, StoryPage, StoryPlan, now
from .verification import eligible

import re

ROLES = ('hook', 'situation', 'conflict', 'explanation', 'key_point_1', 'key_point_2', 'solution', 'summary_cta')
PERCENT = re.compile(r'\d+(?:\.\d+)?\s*%p?')
# 분야별 창작 대사·확인 목록. 사실이 아니라 상황 연출이며, 수치는 쓰지 않는다 (수치는 검증된 사실 카드에만).
SCENES = {
    'housing': {'situation': ('주거비를 따져보는 직장인의 고민', '전세와 월세 중 무엇부터 비교할까?'),
                'conflict': '당장 내는 돈만 비교하면 될까?',
                'checklist': ['발표 기관·기준 시점 확인', '내 계약 조건과 같은지 확인', '보증금·월세·대출이자를 합쳐 비교']},
    'finance': {'situation': ('월급을 관리하는 직장인의 고민', '월급을 어떻게 나눠야 할까?'),
                'conflict': '내 목표와 상품 조건이 다르면?',
                'checklist': ['발표 기관·기준 시점 확인', '가입 대상·한도 조건 확인', '수익보다 비용·위험부터 비교']},
    'economy': {'situation': ('장을 보고 영수증을 보는 직장인', '월급은 그대로인데 장보기는 왜 더 비싸지?'),
                'conflict': '숫자 하나만 보면 놓치는 게 있대!',
                'checklist': ['발표 기관·기준 시점 확인', '내 지출에서 비중 큰 항목 점검', '평균 통계와 내 체감 비교']},
}


def source_label(doc) -> str:
    """페이지 하단 출처: 주소 대신 '발행처 「자료 제목」'. 제목 끝의 사이트 메뉴 경로는 뗀다."""
    from .discovery import publisher
    title = re.split(r'\s+\|\s+', doc.title or '')[0].strip()
    owner = re.split(r'\s*:\s*', doc.title)[-1].strip() if ':' in (doc.title or '') else publisher(doc.url)
    return f'{owner} 「{title}」' if title else owner


def key_number(claim: str) -> str:
    """정보 카드에 크게 보여 줄 수치. 검증된 문장 안의 마지막 퍼센트(대개 전년 대비 값)만 쓴다."""
    found = PERCENT.findall(claim)
    return found[-1].replace(' ', '') if found else ''
STYLES = {'housing': '공감형 하이브리드', 'finance': '교육형 하이브리드', 'economy': '정보형 하이브리드'}


def build_story(topic: Topic, docs, *, fmt='hybrid', pages=8, character_root=None, direction='', at=None) -> StoryPlan:
    if fmt not in ('hybrid', 'insta_toon', 'card_news') or pages != 8:
        raise ValueError('전략 V1 스토리는 hybrid/insta_toon/card_news 8페이지를 지원합니다')
    if not eligible(topic, at):
        raise ValueError('핵심 주장 검증·기한·중복·권리 조건을 먼저 확인해 주세요')
    bible = get_character(topic.character_id, character_root)
    facts = [f for f in topic.facts if f.verification == 'verified']
    if not facts:
        raise ValueError('기획에 사용할 검증된 사실이 없습니다')
    text = [f.claim if f.kind == 'fact' else f'[{"전망" if f.kind == "forecast" else "의견"}] {f.claim}' for f in facts]
    sources = [{'title': e.title, 'url': e.url} for e in docs]
    # 발표일과 (있을 때만) 적용 대상. 빈 값은 '일반 개념' 같은 말로 채우지 않는다.
    scopes = [' / '.join(x for x in (f'{f.as_of} 발표' if f.as_of else '', f'적용: {f.applies_to}' if f.applies_to else '') if x)
              for f in facts]
    labels = {e.evidence_id: source_label(e) for e in docs}
    master = MasterContent(topic=topic.title, title=topic.title, hook=topic.title,
                           subtitle='직장인을 위한 돈과 집 이야기', angle=direction or topic.angle or '선택하기 전 근거와 조건을 함께 확인해요.',
                           story_score=.25 if topic.category == 'economy' else .55,
                           key_points=text, facts=[MasterFact(text=s, source_index=next((i+1 for i,e in enumerate(docs)
                               if f.citations and e.evidence_id == f.citations[0].evidence_id), 0)) for f,s in zip(facts,text)],
                           checklist=SCENES[topic.category]['checklist'],
                           summary=text[0], cta='저장하고 다음 선택 전에 확인해요.',
                           sources=sources, hashtags=['생활경제', '직장인', '경제인스타툰'])
    sc = SCENES[topic.category]
    scenario = (*sc['situation'], sc['conflict'])
    refs = {f.fact_id: [e.url for e in docs if any(c.evidence_id == e.evidence_id for c in f.citations)] for f in facts}
    def fp(index):
        f = facts[min(index, len(facts)-1)]
        return f, list(dict.fromkeys(refs[f.fact_id]))
    rows = [StoryPage(role='hook', page_type='cover', headline=topic.title, body='직장인의 생활경제 선택', layout='cover'),
            StoryPage(role='situation', page_type='comic_scene', headline='이런 고민 해봤나요?', scene=scenario[0], character_id=bible.id,
                      emotion='worried', pose='thinking', dialogue=scenario[1], visual_direction='자체 캐릭터, 빈 말풍선, 글자는 렌더러 합성'),
            StoryPage(role='conflict', page_type='reaction_scene', headline='놓치기 쉬운 조건', scene='판단 기준을 다시 생각하는 창작 상황',
                      character_id=bible.id, emotion='surprised', pose='waving', dialogue=scenario[2], visual_direction='창작 예시. 실제 뉴스 관계자로 표현하지 않음')]
    numbers: dict[int, str] = {}
    for index, role in enumerate(ROLES[3:6]):
        f, urls = fp(index)
        scope = scopes[min(index, len(scopes)-1)]
        body = text[min(index, len(text)-1)] + ('\n' + scope if scope else '')
        numbers[len(rows)] = key_number(f.claim) if f.kind == 'fact' else ''
        use_comic = fmt == 'insta_toon' or (fmt == 'hybrid' and topic.category != 'economy' and index == 0)
        rows.append(StoryPage(role=role, page_type='explanation_scene' if use_comic else 'info_card',
                             headline=('이유를 살펴봐요', '첫 번째 핵심', '두 번째 핵심')[index], body=body,
                             scene='토리가 자료를 가리키며 설명' if use_comic else '', character_id=bible.id if use_comic else '',
                             emotion='confident', pose='pointing', dialogue='조건과 근거를 함께 확인해요.' if use_comic else '',
                             visual_direction='본문은 렌더러에서 합성', source_refs=urls, fact_ids=[f.fact_id]))
    rows += [StoryPage(role='solution', page_type='explanation_scene' if fmt == 'insta_toon' else 'checklist',
                       headline='선택 전 세 가지 확인', body='\n'.join(master.checklist), character_id=bible.id if fmt == 'insta_toon' else '',
                       pose='pointing', dialogue='기준일, 대상, 비용을 확인해요.' if fmt == 'insta_toon' else '',
                       source_refs=list(dict.fromkeys(u for urls in refs.values() for u in urls)), fact_ids=[f.fact_id for f in facts]),
             StoryPage(role='summary_cta', page_type='cta', headline=master.cta, body=master.summary,
                       source_refs=list(dict.fromkeys(u for urls in refs.values() for u in urls)), fact_ids=[f.fact_id for f in facts])]
    if fmt == 'card_news':
        for row in rows:
            if row.character_id:
                row.page_type, row.body = 'hook' if row.role == 'situation' else 'info_card', row.body or row.dialogue
                row.character_id, row.dialogue = '', ''
    elif fmt == 'insta_toon':
        for row in rows[1:-1]:
            if not row.character_id:
                row.character_id, row.page_type, row.dialogue = bible.id, 'explanation_scene', '함께 확인해요.'
    adapted = []
    by_url = {e.url: labels[e.evidence_id] for e in docs}
    for index, row in enumerate(rows):
        # 화면에는 발행처·자료명, manifest/plan 의 source_refs 에는 원문 URL 을 그대로 남긴다
        source = ' / '.join(dict.fromkeys(by_url.get(u, u) for u in row.source_refs))
        if row.character_id:
            adapted.append(ComicPage(type=row.page_type, headline=row.headline, caption=row.body, source=source,
                                     layout=row.layout, panels=[ComicBeat(character_id=row.character_id, scene=row.scene,
                                     emotion=row.emotion, pose=row.pose, dialogue=row.dialogue, background='직장인 생활 공간',
                                     camera='medium', speech_bubble_position='top_right')]))
        else:
            emphasis = numbers.get(index, '')
            adapted.append(CardPage(type=row.page_type, headline=row.headline, body=row.body, layout=row.layout,
                                    source=source, items=master.checklist if row.page_type == 'checklist' else [],
                                    emphasis=emphasis if emphasis and emphasis in row.body else ''))
    comics = sum(isinstance(p, ComicPage) for p in adapted)
    plan = CarouselPlan(format=fmt, template='clean_info' if fmt == 'card_news' else 'comic_hybrid',
                        mix={'card': round((8-comics)/8*100), 'comic': round(comics/8*100)}, pages=adapted, method='topic_strategy_rules')
    return StoryPlan(topic_id=topic.topic_id, format=fmt, title=topic.title, character_id=bible.id,
                     style=STYLES[topic.category] if fmt == 'hybrid' else '스토리형 인스타툰' if fmt == 'insta_toon' else '교육형 카드뉴스',
                     pages=rows, master=master.model_dump(), carousel_plan=plan.model_dump(),
                     provenance={'model': 'none', 'created_at': at or now(), 'config_version': 'topic-strategy-v1',
                                 'sources': sources, 'verification': topic.verification, 'score': topic.score.model_dump() if topic.score else None,
                                 'direction': direction or topic.angle})
