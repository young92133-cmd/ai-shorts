# 스튜디오 편집 기능 기록 (2026-10-19~20, 커밋 93307ff·ed75434, HANDOFF 에서 옮김)

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

