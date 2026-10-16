"""무료 렌더링 인스타툰 샘플 (AI·유료 API 호출 0회).

햄토리치 투명 PNG + 코드로 그린 장면 배경 + 의인화 캐릭터(물가·월급) + 말풍선·조명·감정 효과로 8장을 만든다.
사실 문장은 국가데이터처 「2026년 9월 소비자물가동향」(2026-10-02, 공공누리 1유형) 원문 그대로만 쓴다.
캐릭터 상황·대사는 창작 예시다.

    .venv\\Scripts\\python.exe -m scripts.sample_free_instatoon [A|B]   # A 기본 렌더링, B 스토리형
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path

from app.carousel import pipeline as carouselmod
from app.carousel.schema import CardPage, CarouselPlan, ComicBeat, ComicPage, MasterContent, MasterFact
from app.factory import core
from app.pipeline.models import ResearchDoc

SRC = "국가데이터처 「2026년 9월 소비자물가동향」"
URL = "https://mods.go.kr/board.es?mid=a10301010000&bid=213&act=view&list_no=447322"
H = "hamtorich_01"
FACTS = [  # 공식 원문 그대로
    "9월 소비자물가지수는 전월대비 0.3%, 전년동월대비 2.9% 각각 상승",
    "생활물가지수는 전월대비 0.7%, 전년동월대비 2.5% 각각 상승",
    "전년동월대비 식품은 1.6%, 식품이외는 3.1% 각각 상승",
    "신선식품지수는 전월대비 2.7% 상승, 전년동월대비 3.3% 하락",
]


def plan() -> CarouselPlan:
    pages = [
        CardPage(type="cover", label="햄토리치 경제툰", part="1화", headline="월급은 그대로, 물가는 2.9%↑ 내 장바구니 괜찮아?",
                 emphasis="2.9%", body="9월 소비자물가 공식 통계로 확인해요", character_emotion="worried", source=SRC),
        ComicPage(type="comic_scene", headline="월급날 퇴근길", panels=[
            ComicBeat(character_id=H, scene="월급 알림을 보고 신난 햄토리치", emotion="happy", pose="phone",
                      dialogue="월급 들어왔다~ 오늘은 장 보고 가야지!", background="퇴근길 골목 노을", camera="medium",
                      speech_bubble_position="top_left")]),
        ComicPage(type="reaction_scene", headline="마트 계산대", panels=[
            ComicBeat(character_id=H, scene="계산 금액을 보고 놀람", emotion="surprised", pose="standing",
                      dialogue="몇 개 안 샀는데 왜 이렇게 나와?!", background="마트 계산대",
                      partner="tag:물가", partner_emotion="confident", partner_dialogue="헤헤, 나 좀 컸지~")]),
        ComicPage(type="dialogue_scene", panels=[
            ComicBeat(character_id=H, scene="집에 와서 월급에게 하소연", emotion="angry", pose="standing",
                      dialogue="월급아, 너도 좀 올라 봐!", background="원룸 밤",
                      partner="tag:월급", partner_emotion="sad", partner_dialogue="나도 그러고 싶어…"),
            ComicBeat(character_id=H, scene="마음을 가라앉히고 자료를 집어 든다", emotion="thinking", pose="explaining",
                      dialogue="감으로 말고, 공식 통계로 확인해 보자", background="원룸 밤", camera="close_up",
                      speech_bubble_position="top_left")]),
        ComicPage(type="explanation_scene", panels=[
            ComicBeat(character_id=H, emotion="thinking", pose="explaining", dialogue="국가데이터처 9월 발표!",
                      background="원룸 밤 책상", speech_bubble_position="top_right")],
                  caption=FACTS[0], emphasis="2.9%", source=SRC),
        ComicPage(type="explanation_scene", panels=[
            ComicBeat(character_id=H, emotion="happy", pose="pointing", dialogue="자주 사는 물건만 모으면?",
                      background="편의점 밤", speech_bubble_position="top_right",
                      partner="tag:물가", partner_emotion="worried", partner_dialogue="")],
                  caption=f"{FACTS[1]}. {FACTS[2]}", emphasis="2.5%", source=SRC),
        ComicPage(type="comic_scene", headline="주말 장보기", panels=[
            ComicBeat(character_id=H, scene="신선식품 코너에서 신난 햄토리치", emotion="happy", pose="cheering",
                      dialogue="신선식품지수는 1년 전보다 3.3% 하락! 제철 과일부터 담자", background="마트 장보기",
                      partner="tag:물가", partner_emotion="surprised", partner_dialogue="앗, 들켰다…")],
                  source=SRC),
        CardPage(type="cta", headline="여러분 장바구니에서 가장 오른 건?", body="댓글로 알려 주세요. 다음 발표 때 2화로 이어집니다!",
                 items=["저장", "공유", "댓글"], character_emotion="happy", character_pose="cheering", source=SRC),
    ]
    return CarouselPlan(format="insta_toon", template="hamtorich_toon", mix={"card": 25, "comic": 75}, pages=pages,
                        method="handwritten_sample")


def master() -> MasterContent:
    return MasterContent(
        topic="9월 소비자물가와 내 장바구니", title="월급은 그대로, 물가는 2.9%↑ 내 장바구니 괜찮아?",
        subtitle="9월 소비자물가 공식 통계", hook="몇 개 안 샀는데 왜 이렇게 나와?!", story_score=0.75,
        key_points=FACTS, facts=[MasterFact(text=f, source_index=1) for f in FACTS],
        summary=FACTS[0], cta="여러분 장바구니에서 가장 오른 건? 댓글로 알려 주세요",
        hashtags=["햄토리치", "경제툰", "인스타툰", "소비자물가", "장보기"],
        sources=[{"title": SRC, "url": URL}])


def plan_b() -> CarouselPlan:
    """B: 스토리형. 훅 → 상황 → 상대역 등장 → 갈등 → 정보 발견 → 해결 → 반전·결론. 카메라·장면·효과음을 바꿔 가며."""
    pages = [
        # 1. 훅: 실제 장면(마트) 위에 걱정 표정 + 사건형 제목
        CardPage(type="cover", label="햄토리치 경제툰", part="1화", layout="scene:마트 계산대",
                 headline="몇 개 안 샀는데 계산대에서 얼어붙었다", emphasis="얼어붙었다",
                 body="범인은 9월 물가? 공식 통계로 추적!", character_emotion="worried", source=SRC),
        # 2. 상황: 원경(퇴근길) → 얼굴 클로즈업 (컷 전환)
        ComicPage(type="dialogue_scene", headline="월급날 퇴근길", panels=[
            ComicBeat(character_id=H, emotion="happy", pose="phone", dialogue="월급 들어왔다!", sfx="띠링!",
                      background="퇴근길 골목 노을", camera="wide", speech_bubble_position="top_right"),
            ComicBeat(character_id=H, emotion="confident", pose="arms_crossed", dialogue="오늘은 먹고 싶은 거 다 산다!",
                      background="퇴근길 골목 노을", camera="extreme_close_up", speech_bubble_position="top_left")]),
        # 3. 상대역 등장: 계산대에서 물가와 마주침
        ComicPage(type="reaction_scene", headline="마트 계산대", panels=[
            ComicBeat(character_id=H, emotion="worried", pose="standing", dialogue="자, 잠깐… 이게 다 얼마라고요?!",
                      background="마트 계산대", sfx="두둥", partner="tag:물가", partner_emotion="confident",
                      partner_dialogue="반가워~ 나 요즘 좀 컸어!")]),
        # 4. 갈등: 집에서 월급과 다툼 → 털썩 → 의심 (3컷)
        ComicPage(type="comic_scene", panels=[
            ComicBeat(character_id=H, emotion="angry", pose="standing", dialogue="월급아! 너는 왜 그대로야!",
                      background="원룸 밤", partner="tag:월급", partner_emotion="sad", partner_dialogue="나도 억울해…"),
            ComicBeat(character_id=H, emotion="worried", pose="standing", dialogue="이번 달도 빠듯하겠다…",
                      background="원룸 밤", camera="extreme_close_up", sfx="털썩"),
            ComicBeat(character_id=H, emotion="thinking", pose="chin", dialogue="근데 정말 다 오른 걸까?",
                      background="원룸 밤", speech_bubble_position="top_left")]),
        # 5. 정보 발견 1: 공식 발표 원문
        ComicPage(type="explanation_scene", panels=[
            ComicBeat(character_id=H, emotion="thinking", pose="explaining", dialogue="국가데이터처 9월 발표 찾았다!",
                      background="원룸 밤 책상", sfx="찾았다", speech_bubble_position="top_right")],
                  caption=FACTS[0], emphasis="2.9%", source=SRC),
        # 6. 정보 발견 2: 물가를 몰아붙이는 대화 + 원문
        ComicPage(type="explanation_scene", panels=[
            ComicBeat(character_id=H, emotion="happy", pose="pointing", dialogue="자주 사는 것만 보면 어때?",
                      background="편의점 밤", partner="tag:물가", partner_emotion="worried", partner_dialogue="그, 그건…")],
                  caption=f"{FACTS[1]}. {FACTS[2]}", emphasis="2.5%", source=SRC),
        # 7. 해결 + 반전: 주말 장보기, 신선식품은 내렸다
        ComicPage(type="explanation_scene", headline="주말 장보기", panels=[
            ComicBeat(character_id=H, emotion="happy", pose="cheering", dialogue="그럼 제철 과일부터 담자!",
                      background="마트 장보기", sfx="반짝", partner="tag:물가", partner_emotion="surprised",
                      partner_dialogue="앗, 들켰다…")],
                  caption=FACTS[3], emphasis="3.3% 하락", source=SRC),
        # 8. 결론·참여 유도
        CardPage(type="cta", headline="다음 달엔 누가 이길까? 물가 vs 햄토리치",
                 body="여러분 장바구니에서 가장 오른 건? 댓글로! (대사는 창작, 수치는 국가데이터처 원문)",
                 items=["저장", "공유", "댓글"], character_emotion="confident", character_pose="thumbs_up", source=SRC),
    ]
    return CarouselPlan(format="insta_toon", template="hamtorich_toon", mix={"card": 25, "comic": 75}, pages=pages,
                        method="handwritten_sample_b")


async def main(version: str = "A") -> Path:
    cfg = core._run_cfg({"preset": "daily", "llm": "claude", "visuals": "cards"})
    cfg["carousel"] = {**cfg.get("carousel", {}), "image_provider": "none", "image_search": False}
    job = core.output_root() / (dt.datetime.now().strftime("%Y%m%d_%H%M%S") + f"_free_instatoon_sample_{version}")
    out = await carouselmod.run_carousel(
        job, fmt="insta_toon", mode="script", text=master().topic, cfg=cfg, image_search=False,
        inputs={"topic": master().topic, "docs": [ResearchDoc(title=SRC, url=URL, text="\n".join(FACTS))]},
        prepared_master=master(), prepared_plan=plan_b() if version == "B" else plan(), progress=lambda *a: None)
    note = "\n캐릭터 상황과 대사는 이해를 돕기 위한 창작 예시이며, 수치는 국가데이터처 공식 발표 원문입니다.\n"
    with (Path(out["dir"]) / "caption.txt").open("a", encoding="utf-8") as f:
        f.write(note)
    print(json.dumps({k: out[k] for k in ("dir", "pages", "fallback_pages", "plan_method", "master_method")},
                     ensure_ascii=False, indent=2))
    return Path(out["dir"])


if __name__ == "__main__":
    import sys
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "A"))
