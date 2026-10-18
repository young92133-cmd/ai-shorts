# HANDOFF — 현재 상태 (한 장)

> 규칙: AGENTS.md '작업 시작 · 종료'. 이 파일은 80줄 이하로 유지하고, 끝난 기록은 `docs/history/` 로 옮긴다.
> 2026-10-08 이전 상세 기록: `docs/history/HANDOFF_2026-09_10.md`, 옛 계획: `docs/history/IMPLEMENTATION_PLAN_2026-09_10.md`.

## 현재 상태 (2026-10-19, Claude)

- 저장소 `young92133-cmd/ai-shorts`, 브랜치 `feature/agent-content-factory`. 2026-10-19 사용자 승인으로 일반 push(강제 push 없음):
  기존 로컬 커밋 `f5e830b`·`288e128`·`c693ac8`(그대로) + 새 커밋 3개 —
  `acc4ac2` 경량화·규칙 단일화, `95d1f2e` 카드뉴스·인스타툰 스튜디오, 그 다음 커밋 = 인스타툰 품질 개선(이 HANDOFF 포함).
  커밋마다 해당 시점 스냅숏으로 전체 테스트(385 · 390 · 395). 확인은 `git status -sb`(ahead/behind 0 이면 일치).
- 계획 문서: `docs/OPTIMIZATION_PLAN_2026-10-14.md`(5·6단계 승인 대기), `docs/STUDIO_PLAN_2026-10-16.md`.

### 완료 (카드뉴스·인스타툰 스튜디오 S1~S3, 2026-10-16)

- 실행: `카드뉴스 스튜디오 실행.cmd` → http://127.0.0.1:8765/studio (쇼츠 화면 왼쪽에도 링크). 추가 설치 없음.
- 엔진 `app/studio/project.py`: create(=core.make) · list_projects · load · update_page · vary_scene(무료 감정·자세·배경 순환) · rerender · export_zip.
  `carousel/pipeline.py` 의 렌더 루프를 `render_kit`/`render_one` 으로 꺼냄(동작 동일) → 카드 1장만 다시 그리기 가능.
- 화면·경로 `app/studio/api.py` + `studio.html`(한 파일). 제작은 별도 스레드, 진행은 1.5초 폴링. `app/launcher.py` 에 `studio` 인자.
- 테스트 `tests/test_studio.py` 5개. 화면 확인: 기존 프로젝트 복사본으로 열기·대사 수정·장면 바꾸기·ZIP 확인 후 복사본 삭제.

- 백업(2026-10-18, 저장소 밖): `../backups/ai-shorts-before-toon-quality-20261018/` = repo.bundle(모든 브랜치·로컬 커밋 3개) +
  uncommitted.patch + untracked.tar + status.txt + 기준 프로젝트 사본. 원본 프로젝트와 사본이 같음을 diff 로 확인.

### 완료 (인스타툰 품질 개선, 2026-10-18 · 무료 렌더만, AI 호출 0)

- 비교: 기준 `output/20261016_225450_987a`(그대로 보존) → 개선본 `output/20261018_235900_qafter`(사본을 새 렌더러로 다시 그림),
  전후 비교 `output/20261018_235900_qafter/insta_toon/before_after.png`.
- 상대역 구별 `carousel/nametag.py`: 몸 모양 SHAPES(월급=지폐 bill, 잔액=동전 coin, 자동이체·카드=카드 card, 그 밖 콩 egg) + 색 추가.
- 배경 `carousel/scenes.py`: 아침 햇살(time morning), '불 꺼진 방'은 전체 어둡게(lights_off), 지하철에 손잡이 고리·연결문·노선도·광고판.
- 구도 `carousel/render.py`: `bubble_layout`/`bubble_bottom` 으로 말풍선 높이를 먼저 재고 두 인물 컷의 인물 위치 결정,
  가로로 넓은 컷은 상반신 구도(주인공 35%, 상대 10% 아래 자름)로 인물을 키움. 말풍선 얼굴 회피 규칙 유지.
- 표정 일치: `characters.pose_match`(exact/similar/substitute) → 컷 기록 `pose_match`, manifest·스튜디오 `pose_gaps`
  (화면 위 "맞는 표정 그림이 없어 비슷한 그림으로 그린 컷" 안내). 이번 결과: 슬픔(6장)·놀람(4장).
- 필요한 새 포즈 8종 우선순위·제작 방법: `characters/hamtorich_01/README.md` '아직 없는 그림'. 새 그림은 만들지 않았다(사용자 제작 필요).

### 완료 (스튜디오 S4 실제 제작 테스트, 2026-10-16)

- 주제 '월급날 직장인에게 벌어지는 웃픈 현실', 인스타툰 8장, 공개 사진 찾기 끔 → `output/20261016_225450_987a/insta_toon/`
  (card_01~08.png, ZIP, 한눈에 보기 `overview.png`). 화면의 '새로 만들기'로 제작, 8장 모두 정상·fallback 0.
- AI 호출: Claude 구독(`claude auth status` = claude.ai / pro, SDK 에서 API 키 비움) 2회(Master·페이지 구성, claude-opus-5). 유료 API·이미지 생성 0.
- 발견·수정(`app/carousel/render.py`): 말풍선·제목 마지막 줄 한 단어 고립 → `balanced()`로 줄 길이 균등,
  클로즈업 컷 아래 말풍선이 입을 가림 → 클로즈업은 같은 쪽 위 말풍선, 두 인물 컷 주인공 머리를 말풍선이 덮음 → 주인공 상자 위 22% 비움.
- 화면에서 8장 제목·본문 수정 → 그 장만 다시 그림 확인, ZIP(PNG 8 + caption + sources) 저장 확인.
- 남은 품질 과제: 감정과 포즈 그림 불일치(슬픔·생각 포즈가 없음, 승인 포즈 8종 한계), 상대역이 모두 같은 이름표 캐릭터,
  '불 꺼진 방' 같은 밤 장면 밝기 미반영, 지하철 배경이 복도처럼 보임.

### 완료 (경량화 1~4단계, 2026-10-16) — 기록: `docs/history/HANDOFF_2026-10-16_optimization.md`

### 수정 파일 (2026-10-19 커밋됨)

AGENTS.md, CLAUDE.md, HANDOFF.md(새로), docs/AGENT_REFERENCE.md(새), docs/history/(이동 2개),
app/pipeline/{fonts(새),cards,quote,images/base,research,article,assets,clips,render,run}.py,
app/carousel/{render,effects,asset_gen,pipeline,nametag,scenes,characters,visuals}.py, app/studio/(새), app/main.py, app/launcher.py,
app/templates/index.html(링크 1줄), 카드뉴스 스튜디오 실행.cmd(새), tests/test_studio.py(새), tests/test_carousel.py(줄 균등·품질 테스트), characters/hamtorich_01/README.md(포즈 목록), docs/STUDIO_PLAN_2026-10-16.md(새)

### 테스트

- 2026-10-16 전체 `unittest discover`: **395개 통과**(2026-10-18 인스타툰 품질 개선 후).
- 글꼴 순서: Windows 에서는 전과 같이 `malgunbd.ttf` 가 먼저 잡힌다. 다른 OS 대체 순서만 하나로 합쳐짐.

## 남은 작업 / 다음 작업

- 다음 후보(승인 후): 카드 순서 바꾸기·추가·삭제, 카드 사진 다시 찾기, toon(검증 사실 기반 스토리 작가) 화면 연결.
- [승인 대기] 최적화 5단계: 옛 MVP 데모·verify 스크립트 4개 `scripts/legacy/` 이동 또는 삭제.
- [승인 대기] 최적화 6단계: Git 밖 대용량(reference.mp4 1GB, output 319MB) 정리 — 사용자 데이터.
- [보류] Gemini 포즈·배경 54장 생성은 중단 상태. `--confirm-cost` 와 사용자 승인 없이는 호출하지 않는다.
  사용자가 `.env` 에 `GEMINI_API_KEY` 를 직접 넣어야 한다(채팅으로 키를 받지 않음).
- 인스타툰: 품질 기준은 `samples/` 의 B 버전. 무료 경로(코드 장면 + ChatGPT 등으로 만든 그림을 `assets/inbox/` 로)가 기본.

## 주의

- 유료 API·commit·push·위험한 삭제·대규모 구조 변경은 사용자 승인 후.
- 다른 세션의 미커밋 변경을 덮어쓰지 않는다. `.env`·키·output·캐시는 커밋하지 않는다.
