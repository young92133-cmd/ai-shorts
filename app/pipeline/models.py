"""파이프라인 전반에서 쓰는 데이터 모델."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------- Claude가 반환하는 구조 ----------

class Scene(BaseModel):
    narration: str = Field(description="이 장면에서 읽을 한국어 나레이션 1~2문장")
    image_prompt: str = Field(description="이 장면의 배경 이미지 생성용 영어 프롬프트. 실제 인물 이름 금지")
    on_screen_text: str = Field(description="화면에 크게 띄울 핵심 키워드 (2~6단어). 없으면 빈 문자열")


class Script(BaseModel):
    topic: str = Field(description="영상 주제 한 줄")
    scenes: list[Scene] = Field(description="첫 장면은 훅, 마지막 장면은 마무리. 6~10개")
    titles: list[str] = Field(description="유튜브 제목 후보 3개. 각 30자 이내")
    description: str = Field(description="유튜브 설명란 텍스트")
    hashtags: list[str] = Field(description="# 없이 태그 5~10개")
    sources: list[str] = Field(description="참고한 출처 URL 목록. 없으면 빈 배열")

    def full_narration(self) -> str:
        return " ".join(s.narration for s in self.scenes)


class StyleProfile(BaseModel):
    """벤치마킹할 채널에서 뽑아낸 스타일 지침."""
    name: str = Field(description="이 스타일의 이름 (예: 'OO채널 뉴스 요약형')")
    hook_pattern: str = Field(description="첫 3초 훅을 만드는 공식. 실제 예시 문장 1~2개 포함")
    structure: str = Field(description="영상의 전개 구조를 순서대로. 예: 훅 → 배경 → 핵심 → 반전 → 마무리")
    emotional_arc: str = Field(description="시작부터 끝까지 시청자의 감정이 어떻게 바뀌는지, 구간별 유도 방법")
    tone: str = Field(description="말투와 어조. 존댓말/반말, 속도감, 감정 표현 정도")
    sentence_style: str = Field(description="문장 길이와 리듬. 한 장면당 문장 수, 평균 길이")
    pacing: str = Field(description="장면 수와 장면당 길이, 전환 속도")
    cta: str = Field(description="마무리와 시청자 유도 방식")
    notes: str = Field(description="그 밖에 따라 할 만한 특징. 없으면 빈 문자열")


class StyleAnalysis(BaseModel):
    """참고 영상들을 분석한 결과."""
    profile: StyleProfile
    findings: list[str] = Field(description="참고 영상에서 관찰한 근거. 각 항목은 한 문장")


class AutoPlan(BaseModel):
    """자동 모드: 소스를 보고 이 영상을 어떻게 만들지 먼저 정한다."""
    angle: str = Field(description="이 소재를 어떤 각도로 풀지 한 문장")
    hook_type: str = Field(description="이 소재에 가장 잘 맞는 훅 유형과 그 이유")
    structure: str = Field(description="추천하는 장면 전개 순서")
    scene_count: int = Field(description="적정 장면 수 (6~10)")
    visual_mode: Literal["images", "broll"] = Field(description="images=생성/수집 이미지 슬라이드쇼, broll=실제 영상 짜깁기")
    reason: str = Field(description="위 구성을 고른 이유")


class ClipSegment(BaseModel):
    start: float = Field(description="원본 영상 시작 초")
    end: float = Field(description="원본 영상 끝 초")
    reason: str = Field(description="이 구간을 고른 이유")


class ClipPlan(BaseModel):
    segments: list[ClipSegment] = Field(description="시간순 1~3개, 합계 45~60초")
    titles: list[str]
    description: str
    hashtags: list[str]


class SourceVideo(BaseModel):
    """짜깁기에 쓸 소스 영상."""
    url: str
    title: str = ""
    duration: float = 0.0
    channel: str = ""
    path: str = ""          # 내려받은 뒤 채워짐
    used: float = 0.0       # 이 소스에서 쓴 총 길이(초)


class BrollPick(BaseModel):
    scene_index: int = Field(description="이 구간을 쓸 장면 번호 (0부터)")
    source_index: int = Field(description="소스 영상 번호 (0부터). 쓸 만한 구간이 없으면 -1")
    start: float = Field(description="소스 영상에서의 시작 초")
    end: float = Field(description="끝 초")
    reason: str = Field(description="이 구간을 고른 이유 한 문장")


class BrollPlan(BaseModel):
    picks: list[BrollPick] = Field(description="장면마다 하나씩. 맞는 화면이 없으면 source_index 를 -1 로")
    notes: str = Field(description="전체적으로 참고할 점. 없으면 빈 문자열")


class TrendPick(BaseModel):
    keyword: str = Field(description="선택한 트렌드 키워드")
    reason: str = Field(description="이 카테고리에 맞는 이유")
    search_query: str = Field(description="리서치용 검색어")


# ---------- 내부 처리용 ----------

class SourcedImage(BaseModel):
    """링크(기사)에서 가져온 이미지."""
    path: str
    src_url: str = ""
    page_url: str = ""
    site: str = ""
    caption: str = ""
    width: int = 0
    height: int = 0

    def credit(self) -> str:
        return f"출처: {self.site}" if self.site else ""


class Asset(BaseModel):
    """사용자가 직접 올린 파일."""
    path: str
    kind: Literal["image", "video"]
    name: str = ""
    duration: float = 0.0          # 영상일 때
    preview: str = ""              # 영상의 대표 프레임 (비전 분석·썸네일용)
    description: str = ""          # 비전 분석 결과


class AssetMatch(BaseModel):
    """첨부 파일을 어느 장면에 쓸지."""
    asset_index: int = Field(description="첨부 파일 번호 (0부터)")
    scene_index: int = Field(description="배치할 장면 번호 (0부터). 쓸 장면이 없으면 -1")
    reason: str = Field(description="그렇게 고른 이유 한 문장")
    fit: int = Field(description="적합도 1~5. 3 미만이면 쓰지 않는다")


class AssetPlan(BaseModel):
    matches: list[AssetMatch] = Field(description="첨부 파일마다 하나씩. 같은 장면에 둘을 넣지 않는다")


class AssetDescription(BaseModel):
    description: str = Field(description="이미지에 무엇이 보이는지 한국어 한두 문장. 인물은 '남성 1명'처럼 특정하지 말 것")
    keywords: list[str] = Field(description="검색용 키워드 3~6개")


class SceneVisual(BaseModel):
    """장면 하나에 쓸 비주얼이 어디서 왔는지."""
    scene_index: int
    kind: Literal["upload", "sourced", "generated", "card"] = "generated"
    path: str = ""
    credit: str = ""               # 화면 하단에 띄울 출처 문구
    note: str = ""                 # 로그·UI 설명용


class Word(BaseModel):
    text: str
    start: float
    end: float


class SceneAudio(BaseModel):
    index: int
    path: str
    duration: float
    words: list[Word]  # 절대 시각(전체 나레이션 기준)
    offset: float = 0.0


class ResearchDoc(BaseModel):
    title: str
    url: str
    text: str
    published: str = ""


JobMode = Literal["topic", "url", "auto"]
