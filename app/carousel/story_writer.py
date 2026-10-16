"""스토리 작가 + 연출 감독 — 검증된 사실로 B 수준(사건 중심) 인스타툰 8장을 자동 기획한다.

구조: 훅(표지) → 상황 발생 → 상대역 등장 → 갈등 확대 → 정보 발견 → (정보 발견 2) → 해결·반전 → 결론(CTA).
- 기본 `rules`: 무료. 지표별 시나리오 사전 + 대사 변형으로 쓴다.
- 선택 `claude`: 구독 Claude(llm.ask_structured, API 키를 비운 CLI 경로)가 대사·사건을 쓴다. 사용자가 고를 때만.
두 경로 모두 같은 중간 구조(StoryDraft) → validate_story(검증) → direct(연출) → CarouselPlan.
수치·날짜는 검증된 fact ID 의 원문에 있는 것만 허용한다. 사실 상자는 fact 원문을 그대로 넣고, 작가는 바꿀 수 없다.
검증에 실패한 Claude 초안은 자동 채택하지 않는다(StoryRejected).
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from pydantic import BaseModel, Field

from .schema import CardPage, CarouselPlan, ComicBeat, ComicPage, MasterContent, MasterFact

H = "hamtorich_01"
NUM = re.compile(r"\d+(?:[.,]\d+)?")
EMOTIONS = ("neutral", "happy", "surprised", "worried", "thinking", "confident", "sad", "angry")
ROLES = ("situation", "opponent", "conflict", "discovery", "discovery2", "resolution")


class VerifiedFact(BaseModel):
    fact_id: str
    claim: str
    source_title: str = ""
    source_url: str = ""


# ---------- 중간 구조 (작가가 쓰는 것) ----------

class DraftPanel(BaseModel):
    emotion: str = Field(default="neutral", description=" | ".join(EMOTIONS))
    line: str = Field(default="", description="햄토리치 대사 (30자 이내, 숫자는 fact 원문에 있는 것만)")
    partner_emotion: str = Field(default="neutral")
    partner_line: str = Field(default="", description="상대역 대사 (20자 이내). 상대역 없는 컷은 빈 문자열")
    sfx: str = Field(default="", description="효과음 1~4글자 (띠링!, 두둥, 털썩, 반짝 …). 없으면 빈 문자열")
    camera: str = Field(default="", description="wide | medium | close_up | extreme_close_up (비우면 감독이 정함)")
    with_partner: bool = Field(default=False, description="이 컷에 상대역이 함께 나오는가")


class DraftScene(BaseModel):
    role: str = Field(description=" | ".join(ROLES))
    place: str = Field(description="장소 (예: 퇴근길 골목 노을, 마트 계산대, 원룸 밤, 은행 창구, 부동산 중개사무소, 회사 사무실, 카페, 편의점 밤, 아파트 단지)")
    narration: str = Field(default="", description="장면 전환 캡션 (예: 그날 밤, 주말 아침). 8자 이내")
    panels: list[DraftPanel] = Field(description="컷 1~3개")
    fact_ids: list[str] = Field(default_factory=list, description="이 장면에서 보여 줄 검증된 사실 id (정보 발견·해결 장면)")


class StoryDraft(BaseModel):
    title: str = Field(description="표지 훅 제목 (사건 한 문장, 22자 안팎). 숫자는 fact 원문에 있는 것만")
    title_emphasis: str = Field(default="", description="제목 안에서 빨갛게 강조할 부분 (제목에 그대로 포함)")
    subtitle: str = Field(default="", description="표지 부제 (20자 이내)")
    rival_tag: str = Field(description="상대역 의인화 이름 (예: 물가, 금리, 집값, 대출, 월세, 환율). 2~4글자")
    second_tag: str = Field(default="월급", description="갈등을 키우는 두 번째 의인화 이름 (예: 월급)")
    scenes: list[DraftScene] = Field(description="6개: situation, opponent, conflict, discovery, discovery2, resolution 순서")
    ending_question: str = Field(description="마지막 장 질문 (댓글 유도)")
    ending_body: str = Field(default="", description="마지막 장 한두 문장")


class StoryRejected(ValueError):
    """검증 실패한 초안. reasons 에 이유 목록."""

    def __init__(self, reasons: list[str], draft: StoryDraft | None = None):
        super().__init__("; ".join(reasons))
        self.reasons, self.draft = reasons, draft


# ---------- 지표별 시나리오 (무료 규칙 작가) ----------

PROFILES: dict[str, dict[str, Any]] = {
    "물가": {"words": ("물가", "소비자물가", "장바구니", "생활물가", "식품"), "obj": "장바구니", "rival": "월급",
             "pressure": "마트 계산대", "second": "편의점 밤", "resolve": "마트 장보기",
             "hooks": ["몇 개 안 샀는데 계산대에서 얼어붙었다", "장바구니 하나에 월급이 녹는 중"],
             "excite": ["오늘은 먹고 싶은 거 다 산다!", "이번 주 장보기는 플렉스다!"],
             "shock": ["자, 잠깐… 이게 다 얼마라고요?!", "영수증이… 왜 이렇게 길어요?!"],
             "taunt": ["반가워~ 나 요즘 좀 컸어!", "헤헤, 또 만났네?"],
             "solve": ["그럼 장보기 순서부터 바꿔 보자!", "오른 것과 내린 것, 골라서 담자!"]},
    "금리": {"words": ("금리", "기준금리", "이자", "대출"), "obj": "대출 이자", "rival": "월급",
             "pressure": "은행 창구", "second": "카페", "resolve": "은행 창구",
             "hooks": ["대출 이자 안내를 보고 그대로 굳었다", "이자 문자 한 통에 잠이 확 깼다"],
             "excite": ["오늘은 드디어 대출 상담 날!", "내 집 마련, 한 걸음 더!"],
             "shock": ["네? 이자가 이렇게 바뀐다고요?!", "잠깐만요, 다시 계산해 주세요!"],
             "taunt": ["나도 사정이 있다고~", "오르락내리락이 내 일이야!"],
             "solve": ["조건부터 하나씩 비교해 보자!", "고정이냐 변동이냐, 따져 볼게요!"]},
    "집": {"words": ("전세", "월세", "집값", "주택", "아파트", "청약", "보증금", "임대"), "obj": "보증금", "rival": "월급",
           "pressure": "부동산 중개사무소", "second": "원룸 밤", "resolve": "아파트 단지",
           "hooks": ["재계약 문자 한 통에 눈앞이 캄캄해졌다", "집 보러 갔다가 숫자에 놀라 도망쳤다"],
           "excite": ["이번엔 꼭 마음에 드는 집 찾을 거야!", "드디어 이사 준비 시작!"],
           "shock": ["네? 조건이 이렇게 달라졌다고요?!", "이 집이… 이 가격이라고요?!"],
           "taunt": ["요즘 내가 좀 바빠~", "나 쉽게 안 내려가~"],
           "solve": ["공식 자료로 조건부터 비교하자!", "숫자부터 차근차근 확인해 볼게요!"]},
    "월급": {"words": ("월급", "임금", "고용", "취업", "연봉", "소득"), "obj": "통장", "rival": "물가",
             "pressure": "회사 사무실", "second": "편의점 밤", "resolve": "카페",
             "hooks": ["월급날인데 통장이 벌써 비어 간다", "월급 문자 보고 웃다가 울었다"],
             "excite": ["월급날이다! 오늘은 나를 위한 날!", "이번 달은 저축 좀 해 볼까?"],
             "shock": ["어? 벌써 이것밖에 안 남았어?!", "카드값이… 이렇게 나왔다고?!"],
             "taunt": ["난 그대로인데 왜 나만 탓해~", "나도 열심히 일하는 중이라고…"],
             "solve": ["지출부터 나눠서 다시 계획해 보자!", "숫자로 보니까 길이 보여요!"]},
}
DEFAULT_PROFILE = {"words": (), "obj": "지갑", "rival": "월급", "pressure": "회사 사무실", "second": "카페", "resolve": "카페",
                   "hooks": ["뉴스 한 줄에 퇴근길이 멈췄다"], "excite": ["오늘은 기분 좋은 퇴근길!"],
                   "shock": ["이게 무슨 소리예요?!"], "taunt": ["나 몰랐어?"], "solve": ["공식 자료로 확인해 보자!"]}


def profile_for(topic: str, facts: list[VerifiedFact]) -> tuple[str, dict[str, Any]]:
    text = topic + " " + " ".join(f.claim for f in facts)
    best, score = None, 0
    for key, prof in PROFILES.items():
        s = sum(text.count(w) for w in prof["words"])
        if s > score:
            best, score = key, s
    if not best:
        return "이슈", DEFAULT_PROFILE
    return ("물가" if best == "물가" else best if best != "집" else
            next((w for w in ("전세", "월세", "집값", "청약") if w in text), "집값")), PROFILES[best]


def _pick(options: list[str], seed: str, k: int = 0) -> str:
    return options[(int(hashlib.md5(seed.encode()).hexdigest()[:6], 16) + k) % len(options)]


def _agency(fact: VerifiedFact) -> str:
    return fact.source_title.split("「")[0].strip() or "공식 자료"


def _fact_order(facts: list[VerifiedFact]) -> list[VerifiedFact]:
    """첫 사실은 화제(상승·변화), 마지막은 반전(하락·감소)이 오도록."""
    down = [f for f in facts if re.search(r"하락|감소|내렸|줄었|낮아", f.claim)]
    rest = [f for f in facts if f not in down]
    return (rest[:2] + down[:1]) if down else facts[:3]


def rule_draft(topic: str, facts: list[VerifiedFact]) -> StoryDraft:
    """무료 규칙 작가. 대사에는 숫자를 쓰지 않고, 숫자는 표지 제목(첫 사실의 수치)과 사실 상자에만 둔다."""
    tag, prof = profile_for(topic, facts)
    seed = topic
    chosen = _fact_order(facts)
    f1 = chosen[0]
    agency = _agency(f1)
    rival = prof["rival"] if prof["rival"] != tag else "월급"
    disc = [chosen[0]] + ([chosen[1]] if len(chosen) > 1 else [])
    twist = [chosen[2]] if len(chosen) > 2 else []
    scenes = [
        DraftScene(role="situation", place="퇴근길 골목 노을", narration="퇴근길", panels=[
            DraftPanel(emotion="happy", line=_pick(["월급 들어왔다!", "오늘 하루도 끝!", "드디어 퇴근이다!"], seed), sfx="띠링!", camera="wide"),
            DraftPanel(emotion="confident", line=_pick(prof["excite"], seed), camera="extreme_close_up")]),
        DraftScene(role="opponent", place=prof["pressure"], narration=prof["pressure"], panels=[
            DraftPanel(emotion="worried", line=_pick(prof["shock"], seed), sfx="두둥", with_partner=True,
                       partner_emotion="confident", partner_line=_pick(prof["taunt"], seed))]),
        DraftScene(role="conflict", place="원룸 밤", narration="그날 밤", panels=[
            DraftPanel(emotion="angry", line=f"{rival}아, 너는 왜 그대로야!" if tag == "물가" else f"{tag}, 너 때문에 계획이 엉망이야!",
                       with_partner=True, partner_emotion="sad",
                       partner_line="나도 억울해…" if tag == "물가" else "나만 탓하지 마…"),
            DraftPanel(emotion="worried", line=_pick(["이번 달도 빠듯하겠다…", "이러다 계획이 다 꼬이겠어…"], seed), sfx="털썩",
                       camera="extreme_close_up"),
            DraftPanel(emotion="thinking", line="근데… 정말 다 그런 걸까?")]),
        DraftScene(role="discovery", place="원룸 밤 책상", panels=[
            DraftPanel(emotion="thinking", line=f"{agency} 발표 찾았다!", sfx="찾았다")], fact_ids=[f1.fact_id]),
        DraftScene(role="discovery2", place=prof["second"], panels=[
            DraftPanel(emotion="happy", line=_pick(["자세히 보면 이야기가 달라져요!", "평균 말고 하나씩 볼까요?"], seed),
                       with_partner=True, partner_emotion="worried", partner_line="그, 그건…")],
                   fact_ids=[f.fact_id for f in disc[1:]] or [f1.fact_id]),
        DraftScene(role="resolution", place=prof["resolve"], narration="주말 아침", panels=[
            DraftPanel(emotion="happy", line=_pick(prof["solve"], seed), sfx="반짝", with_partner=True,
                       partner_emotion="surprised", partner_line="앗, 들켰다…")],
                   fact_ids=[f.fact_id for f in twist]),
    ]
    # 표지: 사건형 훅 + 첫 사실의 대표 수치 (원문 그대로)
    hook = _pick(prof["hooks"], seed)
    return StoryDraft(title=hook, title_emphasis=hook.split()[-1], subtitle=f"범인은 {tag}? 공식 자료로 추적!",
                      rival_tag=tag, second_tag=rival, scenes=scenes,
                      ending_question=f"다음 달엔 누가 이길까? {tag} vs 햄토리치",
                      ending_body=f"여러분 {prof['obj']}에서 가장 크게 느낀 변화는? 댓글로 알려 주세요!")


# ---------- Claude 작가 (선택) ----------

WRITER_SYSTEM = """당신은 한국 인스타툰 작가입니다. 주인공은 브랜드 캐릭터 '햄토리치'(작지만 똑똑한 금융 친구 햄스터, ~요 체, 다정하고 짧게, 응원하는 말투).
경제 지표·주체는 의인화 캐릭터(예: 물가, 금리, 월급)로 등장해 햄토리치와 티격태격합니다.

반드시 지킬 것:
- 구조: 표지 훅 → situation(상황 발생) → opponent(상대역 등장) → conflict(갈등 확대, 컷 3개) → discovery(정보 발견) → discovery2 → resolution(해결·반전) → 결론 질문.
- 설명만 하는 장면을 만들지 말 것. 모든 장면에 행동·감정·대화가 있어야 한다. 정보는 discovery·discovery2·resolution 의 fact_ids 로만 넣는다.
- 숫자·날짜·통계는 아래 [검증된 사실] 원문에 있는 것만. 대사에 숫자를 넣을 땐 그 장면 fact_ids 의 원문 숫자만. 새 수치·날짜·전망을 만들지 말 것.
- 사실 상자 문장은 시스템이 fact 원문으로 넣는다. 당신은 fact_ids 만 고른다.
- 대사는 짧고 재미있게(햄토리치 30자, 상대역 20자 이내). 실존 인물·기업 이름 금지. 광고·투자 권유 금지.
- 표지 제목은 사건 한 문장(예: '몇 개 안 샀는데 계산대에서 얼어붙었다'), title_emphasis 는 제목 속 일부."""


async def claude_draft(llm: dict[str, Any], topic: str, facts: list[VerifiedFact]) -> StoryDraft:
    from ..pipeline.llm import ask_structured
    listing = "\n".join(f"- {f.fact_id}: {f.claim} (출처: {f.source_title})" for f in facts)
    user = f"[주제] {topic}\n[검증된 사실]\n{listing}\n\n위 구조로 8장 인스타툰을 기획하세요."
    return await ask_structured(llm, WRITER_SYSTEM, user, StoryDraft)


# ---------- 검증 ----------

def validate_story(draft: StoryDraft, facts: list[VerifiedFact]) -> list[str]:
    """수치·날짜·fact id·구조 검사. 빈 목록이면 통과."""
    by_id = {f.fact_id: f for f in facts}
    all_nums = {n for f in facts for n in NUM.findall(f.claim)}
    problems: list[str] = []
    roles = [s.role for s in draft.scenes]
    if roles != list(ROLES):
        problems.append(f"장면 순서가 구조와 다름: {roles}")
    used: set[str] = set()
    for s in draft.scenes:
        bad = [i for i in s.fact_ids if i not in by_id]
        if bad:
            problems.append(f"{s.role}: 검증되지 않은 fact id {bad}")
        used.update(i for i in s.fact_ids if i in by_id)
        scene_nums = {n for i in s.fact_ids if i in by_id for n in NUM.findall(by_id[i].claim)}
        if not 1 <= len(s.panels) <= 3:
            problems.append(f"{s.role}: 컷 수 {len(s.panels)}")
        for p in s.panels:
            for text in (p.line, p.partner_line, s.narration):
                extra = set(NUM.findall(text)) - scene_nums
                if extra:
                    problems.append(f"{s.role}: 근거 없는 숫자 {sorted(extra)} — '{text}'")
            if not p.line.strip():
                problems.append(f"{s.role}: 햄토리치 대사가 비어 있음")
    for label, text in (("표지", draft.title + " " + draft.subtitle), ("결론", draft.ending_question + " " + draft.ending_body)):
        extra = set(NUM.findall(text)) - all_nums
        if extra:
            problems.append(f"{label}: 근거 없는 숫자 {sorted(extra)}")
    if draft.title_emphasis and draft.title_emphasis not in draft.title:
        problems.append("표지 강조어가 제목에 없음")
    if not used:
        problems.append("검증된 사실을 하나도 쓰지 않음")
    explain_only = sum(1 for s in draft.scenes if s.fact_ids and not any(p.with_partner or p.sfx for p in s.panels))
    if explain_only > 2:
        problems.append(f"설명만 하는 장면이 많음 ({explain_only})")
    if not re.fullmatch(r"[가-힣A-Za-z]{2,6}", draft.rival_tag or ""):
        problems.append("상대역 이름이 2~6글자가 아님")
    return problems


# ---------- 연출 감독 ----------

SCENE_WORDS = ("원룸", "거실", "마트", "편의점", "은행", "부동산", "회사", "사무실", "카페", "골목", "거리", "퇴근길",
               "아파트", "지하철", "뉴스", "방", "집")
POSE = {"happy": "pointing", "confident": "thumbs_up", "worried": "standing", "thinking": "chin", "surprised": "cheering",
        "angry": "standing", "sad": "standing", "neutral": "standing"}
SFX_OK = re.compile(r"^[가-힣!?~.…]{1,5}$")


def _place(text: str, fallback: str) -> str:
    return text if any(w in (text or "") for w in SCENE_WORDS) else fallback


def direct(draft: StoryDraft, facts: list[VerifiedFact], *, fmt: str = "insta_toon") -> CarouselPlan:
    """연출: 장소·카메라·포즈·상대역·말풍선·효과·조명(장소의 시간 단어)·전환 캡션을 정한다."""
    by_id = {f.fact_id: f for f in facts}
    src = facts[0].source_title if facts else ""
    tag = "tag:" + draft.rival_tag
    second = "tag:" + (draft.second_tag or "월급")
    prev_place, prev_cam = "", ""
    pages: list[Any] = [CardPage(
        type="cover", label="햄토리치 경제툰", part="1화", layout=f"scene:{_place(draft.scenes[1].place, '마트 계산대')}",
        headline=draft.title, emphasis=draft.title_emphasis, body=draft.subtitle, character_emotion="worried", source=src)]
    for s in draft.scenes:
        place = _place(s.place, "원룸 밤")
        beats = []
        n = len(s.panels)
        for k, p in enumerate(s.panels):
            emo = p.emotion if p.emotion in EMOTIONS else "neutral"
            cam = p.camera if p.camera in ("wide", "medium", "close_up", "extreme_close_up") else ""
            if not cam:
                cam = "wide" if k == 0 and n > 1 and s.role == "situation" else "medium"
            if cam == prev_cam and cam != "medium" and not p.with_partner:
                cam = "medium"          # 같은 특수 구도가 연달아 오지 않게
            prev_cam = cam
            partner = ""
            if p.with_partner:
                # 대사에서 부르는 상대가 두 번째 의인화(예: 월급)면 그 캐릭터를 세운다
                partner = second if (draft.second_tag and draft.second_tag in p.line) else tag
            pos = "top_right" if (k % 2 == 0) else "top_left"
            beats.append(ComicBeat(
                character_id=H, emotion=emo, pose=POSE.get(emo, "standing") if not (s.role == "discovery") else "explaining",
                dialogue=p.line.strip()[:40], background=place, camera=cam if not partner else "medium",
                speech_bubble_position=pos, sfx=p.sfx if SFX_OK.match(p.sfx or "") else "",
                partner=partner, partner_emotion=p.partner_emotion if p.partner_emotion in EMOTIONS else "neutral",
                partner_dialogue=p.partner_line.strip()[:30] if partner else ""))
        if s.role == "situation" and beats:
            beats[0].pose = "phone"
        facts_here = [by_id[i] for i in s.fact_ids if i in by_id][:2]
        headline = s.narration.strip()[:10] if place != prev_place else ""
        prev_place = place
        if facts_here:
            pages.append(ComicPage(type="explanation_scene", headline=headline, panels=beats[:1],
                                   caption=". ".join(f.claim for f in facts_here),
                                   emphasis=_emphasis(facts_here[0].claim), source=facts_here[0].source_title))
        else:
            kind = "reaction_scene" if s.role == "opponent" else "dialogue_scene" if n == 2 else "comic_scene"
            pages.append(ComicPage(type=kind, headline=headline, panels=beats))
    pages.append(CardPage(type="cta", headline=draft.ending_question,
                          body=(draft.ending_body + f" (대사는 창작, 수치는 {_agency(facts[0]) if facts else '공식 자료'} 원문)").strip(),
                          items=["저장", "공유", "댓글"], character_emotion="confident", character_pose="thumbs_up", source=src))
    comics = sum(isinstance(p, ComicPage) for p in pages)
    return CarouselPlan(format=fmt, template="hamtorich_toon", mix={"card": round(100 * (8 - comics) / 8), "comic": round(100 * comics / 8)},
                        pages=pages, method="story_writer")


def _emphasis(claim: str) -> str:
    m = re.findall(r"\d+(?:\.\d+)?%(?:\s*(?:하락|상승))?", claim)
    return m[-1] if m else ""


def master_for(topic: str, draft: StoryDraft, facts: list[VerifiedFact]) -> MasterContent:
    return MasterContent(topic=topic, title=draft.title, subtitle=draft.subtitle, hook=draft.title, story_score=0.75,
                         key_points=[f.claim for f in facts], facts=[MasterFact(text=f.claim, source_index=1) for f in facts],
                         summary=facts[0].claim if facts else "", cta=draft.ending_question,
                         hashtags=["햄토리치", "경제툰", "인스타툰", draft.rival_tag],
                         sources=list({f.source_url: {"title": f.source_title, "url": f.source_url} for f in facts}.values()))


async def write_story(topic: str, facts: list[VerifiedFact], *, writer: str = "rules", llm: dict[str, Any] | None = None,
                      fmt: str = "insta_toon") -> tuple[CarouselPlan, MasterContent, StoryDraft, dict[str, Any]]:
    """(계획, Master, 초안, 보고서). claude 초안이 검증에 실패하면 StoryRejected — 자동 채택하지 않는다."""
    if not facts:
        raise StoryRejected(["검증된 사실이 없습니다"])
    if writer == "claude":
        draft = await claude_draft(llm or {}, topic, facts)
    elif writer == "rules":
        draft = rule_draft(topic, facts)
    else:
        raise ValueError("writer 는 rules | claude")
    problems = validate_story(draft, facts)
    if problems:
        raise StoryRejected(problems, draft)
    plan = direct(draft, facts, fmt=fmt)
    return plan, master_for(topic, draft, facts), draft, {"writer": writer, "validation": "passed", "facts_used":
                                                          sorted({i for s in draft.scenes for i in s.fact_ids})}
