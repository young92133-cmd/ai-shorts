# HANDOFF — 현재 상태 (한 장)

> 규칙: AGENTS.md '작업 시작 · 종료'. 이 파일은 80줄 이하로 유지하고, 끝난 기록은 `docs/history/` 로 옮긴다.
> 2026-10-08 이전 상세 기록: `docs/history/HANDOFF_2026-09_10.md`, 옛 계획: `docs/history/IMPLEMENTATION_PLAN_2026-09_10.md`.

## 현재 상태 (2026-10-19, Claude)

- 저장소 `young92133-cmd/ai-shorts`, 브랜치 `feature/agent-content-factory`. 2026-10-19 일반 push 2회(강제 push 없음):
  `acc4ac2` 경량화 · `95d1f2e` 스튜디오 · `93b03d5` 인스타툰 품질 · `93307ff` 카드 순서·추가·삭제 + 실제 제작 버그 수정.
  2026-10-20: 그 다음 커밋 = 실행 취소·이미지 넣기·화면 개선(이 HANDOFF 포함), 사용자 승인 후 일반 push.
  확인: `git fetch` 후 `git status -sb` 에 ahead/behind 가 없으면 GitHub 와 일치.
- 계획 문서: `docs/OPTIMIZATION_PLAN_2026-10-14.md`(5·6단계 승인 대기), `docs/STUDIO_PLAN_2026-10-16.md`.

### 지난 기록 (커밋됨)
- 스튜디오 S1~S4·인스타툰 품질 개선·백업 상세: `docs/history/HANDOFF_2026-10-16_18_studio.md`
- 경량화 1~4단계: `docs/history/HANDOFF_2026-10-16_optimization.md`

### 완료 (2026-10-19, 사용자 승인 후 커밋·push)

- 실제 제작(스튜디오 '새로 만들기', Claude 구독 각 3회, 유료 API·이미지 생성 0, 공개 사진 검색은 무료지만 맞는 사진 0):
  카드뉴스 8장 `output/20261019_002939_0340/card_news` · 혼합형 8장(카드4+만화4) `output/20261019_003120_1108/hybrid`,
  각 폴더 `overview.png`(한눈에 보기)·ZIP. fallback 0. 기존 인스타툰 결과는 그대로(백업과 diff 일치).
- 새 편집: 카드 순서 바꾸기(◀ 앞으로/뒤로 ▶)·카드 추가(+ 카드 / + 만화 컷, 카드뉴스는 만화 불가)·삭제(3~10장).
  `studio/project.py` `_restructure`: plan 순서 변경 → 사진·업로드 고정 그림도 같이 이동 → 전체 새 번호로 다시 그림 →
  남는 옛 card_NN 정리 → manifest·sources·caption 다시 씀. 바꾸기 전 plan·manifest 는 `<형식>/history/` 에 보존.
  manifest·출처·캡션 쓰기는 `carousel/pipeline.write_results` 하나(제작·1장 수정·구조 편집 공용, 사진 크레딧 장 번호 자동 갱신).
- 시연(카드뉴스 프로젝트): 7장 제목 수정 → 6장 앞으로 → 7장 뒤 카드 추가·문구 저장 → 삭제 → 원래 순서로 → ZIP.
  plan·manifest·PNG 파일명·ZIP 내용 일치 확인.
- 실제 결과에서 고친 렌더 버그(`carousel/render.py`): 인용 카드에 인용문이 본문 칸에만 있으면 큰 따옴표만 남던 문제,
  훅 표지 부제가 캐릭터 밑으로 들어가 잘리던 문제(캐릭터 실제 왼쪽 끝까지로 줄이고 3줄 허용).
- 수정 파일: app/carousel/{pipeline,render}.py, app/studio/{project,api}.py, studio.html, tests/test_{studio,carousel}.py

### 완료 (2026-10-20, 사용자 승인 후 커밋·push) — 스튜디오 사용성
- 실행 취소: `history/` 저장 시점을 그대로 실행 취소 목록으로 씀. 문구 수정·장면 바꾸기·순서·추가·삭제·이미지 넣기/빼기 전에
  저장 → `studio.undo` 가 마지막 시점으로 전체 다시 그림(`_render_pages`, 순서 편집과 같은 경로), 쓴 시점은 `history/undone/` 으로 이동.
- 이미지 직접 넣기·교체·빼기: `studio.set_image/clear_image`. 권리 확인(화면 확인창) 필수, PNG·JPG·WEBP 20MB,
  확장자와 실제 형식 일치·4천만 화소 이하(엔진에서 검사), 저장 이름은 앱이 만듦(사용자 파일명은 표시용 이름만),
  `uploads/studio/` 로 복사 + 출처 대장 등록(`core._own_rights`). 그 페이지 manifest `image`(upload·name) 로 남아 순서 변경·다시 그리기·실행 취소에도
  따라감. 만화 페이지는 첫 컷 그림으로 쓰임(`pipeline.render_one`). `_page_record` 가 upload·name 을 버리던 문제 수정.
- 화면: 편집 버튼을 미리보기 옆 세로 줄로, 미리보기·편집 칸을 창 높이에 맞춤(저장 버튼 고정), 상단 '↶ 실행 취소(n)',
  `/studio#<프로젝트>/<장>` 바로 열기, `/studio` 캐시 안 함. 1280×800 에서 페이지 높이 1,621→838px.
- 확인: 실제 스튜디오(복사본 프로젝트)에서 이미지 넣기 → 순서 이동(이미지 따라감) → 실행 취소 2회 → 원본과 문구·PNG 8장 바이트 동일, ZIP=파일. 복사본은 삭제.
- 수정 파일: app/studio/{project,api}.py, studio.html, app/carousel/pipeline.py, tests/test_studio.py

### 테스트

- 2026-10-20 전체 `unittest discover`: **402개 통과**(실행 취소·이미지 넣기·만화 이미지 3개 추가, API·업로드 검증 테스트 확장).
- 글꼴 순서: Windows 에서는 전과 같이 `malgunbd.ttf` 가 먼저 잡힌다. 다른 OS 대체 순서만 하나로 합쳐짐.

## 남은 작업 / 다음 작업

- 다음 후보(승인 후): 카드 종류 바꾸기(새 카드는 info_card 고정), 공개 사진 다시 찾기, 다시 실행(redo),
  감정 포즈 그림 추가(목록 `characters/hamtorich_01/README.md`), toon(검증 사실 스토리 작가) 화면 연결.
- [승인 대기] 최적화 5단계: 옛 MVP 데모·verify 스크립트 4개 `scripts/legacy/` 이동 또는 삭제.
- [승인 대기] 최적화 6단계: Git 밖 대용량(reference.mp4 1GB, output 319MB) 정리 — 사용자 데이터.
- [보류] Gemini 포즈·배경 54장 생성은 중단 상태. `--confirm-cost` 와 사용자 승인 없이는 호출하지 않는다.
  사용자가 `.env` 에 `GEMINI_API_KEY` 를 직접 넣어야 한다(채팅으로 키를 받지 않음).
- 인스타툰: 품질 기준은 `samples/` 의 B 버전. 무료 경로(코드 장면 + ChatGPT 등으로 만든 그림을 `assets/inbox/` 로)가 기본.

## 주의

- 유료 API·commit·push·위험한 삭제·대규모 구조 변경은 사용자 승인 후.
- 다른 세션의 미커밋 변경을 덮어쓰지 않는다. `.env`·키·output·캐시는 커밋하지 않는다.
