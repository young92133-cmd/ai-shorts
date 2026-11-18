# HANDOFF — 현재 상태 (한 장)

> 규칙: AGENTS.md '작업 시작 · 종료'. 이 파일은 80줄 이하로 유지하고, 끝난 기록은 `docs/history/` 로 옮긴다.
> 2026-10-08 이전 상세 기록: `docs/history/HANDOFF_2026-09_10.md`, 옛 계획: `docs/history/IMPLEMENTATION_PLAN_2026-09_10.md`.

## 현재 상태 (2026-10-21, Claude)

- 저장소 `young92133-cmd/ai-shorts`, 브랜치 `feature/agent-content-factory`. 2026-10-19~21 일반 push(강제 push 없음):
  `acc4ac2` 경량화 · `95d1f2e` 스튜디오 · `93b03d5` 인스타툰 품질 · `93307ff` 카드 순서·추가·삭제 · `ed75434` 실행 취소·이미지·화면
  · 그 다음 커밋 = V1.0 기준선(카드 종류·다시 실행·단어 보존·사용 안내, 이 HANDOFF 포함). 모두 일반 push.
  확인: `git fetch` 후 `git status -sb` 에 ahead/behind 가 없으면 GitHub 와 일치.
- 계획 문서: `docs/OPTIMIZATION_PLAN_2026-10-14.md`(5·6단계 승인 대기), `docs/STUDIO_PLAN_2026-10-16.md`.

### 지난 기록 (커밋됨)
- 스튜디오 S1~S4·인스타툰 품질 개선·백업 상세: `docs/history/HANDOFF_2026-10-16_18_studio.md`
- 카드 순서·추가·삭제, 실행 취소·이미지 넣기·화면(커밋 93307ff·ed75434): `docs/history/HANDOFF_2026-10-19_20_studio_edit.md`
- 경량화 1~4단계: `docs/history/HANDOFF_2026-10-16_optimization.md`

### 완료 (2026-10-21, 사용자 승인 후 커밋·push) — 스튜디오 V1.0 기능 기준선
- V1.0 = 이 커밋의 기능(만들기·문구/종류/장면 편집·순서/추가/삭제·이미지·실행 취소/다시 실행·ZIP). 사용법 `docs/STUDIO_GUIDE_V1.md`.
  버전은 문서로만 표기(Git 태그·Release 없음, 만들려면 별도 승인). 이후는 새 기능보다 품질·안정성 우선(AGENTS.md).
- 카드 종류 바꾸기: 편집 칸 '카드 종류'(카드 8종, 만화↔카드는 안 함). `studio._retype` 가 새 종류에 필요한 칸만 기존 문구로 채움
  (체크리스트·요약=본문 문장→항목, 비교=항목 반씩), 비교 카드는 왼쪽·오른쪽 제목·항목 편집 칸. 8종×템플릿 2개 렌더 대체 없음 확인.
- 다시 실행(redo): `history/redo/` 목록. 실행 취소 전 지금 상태를 redo 에, 다시 실행 전 지금 상태를 history 에 넣고(`_step`),
  새 편집이면 redo 목록을 `history/undone/` 으로 옮김(삭제 없음). 거절된 편집은 기록을 남기지 않게 검사 순서 수정.
- 렌더 버그: 줄 균등(`balanced`)이 폭을 좁혀 '자동이체부 / 터' 처럼 단어를 자르던 문제 → 가장 긴 단어보다 좁히지 않음 + `fit` 도 단어 보존.
- 실제 제작 5편(스튜디오 API = '새로 만들기'와 같은 경로, Claude 구독 2~4회씩, 유료 API·이미지 생성 0, 각 65~150초, 대체 레이아웃 0):
  카드뉴스 `20261019_232015_b625`(신용점수)·`20261019_232120_c27f`(연말정산), 인스타툰 `20261019_232350_20cb`(점심값)·
  `20261019_232526_4972`(관리비), 혼합형 `20261019_232656_1ae7`(구독료). 각 `<형식>/overview.png`. 렌더 버그 수정 뒤 5편 다시 그림(AI 호출 없음).
- 평가 요약: 혼합형·관리비 툰·카드뉴스 2편은 게시 가능 수준(사람이 수치 확인 후). 점심값 툰은 이야기 연결 약함.
  공통 과제 ① 표정 그림 부족(만화 3편 모두 놀람·슬픔 등 대체) ② 공개 사진 0건 → 카드가 그래픽 위주로 단조
  ③ AI 문구의 구체 수치(판매량·공제율 등)는 게시 전 확인 필요 ④ 출처 이름이 '자료 1' 처럼 불명확한 경우.
- 수정 파일: app/studio/{project,api}.py, studio.html, app/carousel/render.py, tests/test_{studio,carousel}.py,
  docs/STUDIO_GUIDE_V1.md(새), README·AGENTS(안내 한 줄)

### 완료 (2026-10-21, 사용자 승인 후 커밋·push) — 실제 5편 게시 전 품질 검수
- 보고서 `docs/QA_REVIEW_2026-10-21.md`: 카드별 사실 확인(✅/⚠/❓, 금감원·NICE·국세청 해설·아시아경제·국토부·대한상의 근거)·
  표지/본문 불일치·스토리 평가·수정 권장. 사용자 승인(권장 전부) 후 수정본 `output/<id>_qa/` 에만 반영, 바뀐 카드만 다시 그림.
- 비교 `output/qa_2026-10-21_before_after.png`. 원본 5편은 변경 없음. 검증 필요(❓)로 남긴 것: 신용카드 '한도 절반' 기준(문구에서 제거),
  OTT '연 15만 원'(같은 편 예시 요금으로 계산한 16만 원으로 대체), 조사의 '5만 원 이상 37%'(카드 미사용).
- 렌더: 훅 표지 제목도 줄 균등(`render.r_cover_hook`), 회귀 테스트 1개. 새 UI·기능 없음.
- 보고서에 '확인된 사실(공식/언론/해설) · 단순 계산 · 확인되지 않은 주장' 구분과 연말정산 연도 확인(근거=2025년 귀속, 게시 대상=2026년 귀속,
  카드엔 연도 없음, 2027년 1월 국세청 안내로 재확인) 추가.
- 원본·수정본 10편 백업(Git 밖): `../backups/qa-5-decks-20261021/decks_original_and_qa.zip`(175파일, 38MB, SHA256SUMS.json, 내용 대조 OK).

### 진행 (2026-10-21, 미커밋 · 커밋/push 는 승인 후) — V1.0 운영 준비 마무리 (프로그램 코드 변경 없음)
- 게시 묶음 `output/_publish_2026-10-21/`(Git 밖, 수정본에서 복사): 01 신용점수·03 점심값·04 관리비·05 구독료 = 게시 가능,
  02 연말정산 = `_보류`(2026년 귀속 국세청 공식 기준 확인 전). 캡션 수정은 묶음 복사본에만: 연말정산 요약 → "월세 증빙과 부양가족 요건은 직접 챙기기",
  구독료 `#월3만원` → `#구독료정리`. 검사: 해시태그·출처·PNG 일치, 캡션 숫자는 카드와 일치(13월=관용 해시태그, '월 3만 원 이상'은 3만 2천 원과 모순 없음),
  원본·수정본 175파일은 이전 백업 체크섬과 동일(변경 없음).
- 운영 데이터 분리: 공통 양식 `docs/content_log_template.csv`(Git), 실제 기록 `ops_data/content_log.csv`(`.gitignore`, 게시일·조회·저장·공유·댓글 수 열 추가).
  안내 `docs/CONTENT_OPS.md`.
- 백업(새 폴더, 기존 백업 그대로): `../backups/publish-20261021/publish_package_20261021.zip` — 게시 묶음+ops_data+캐릭터 참고판 63파일 12MB,
  SHA256SUMS.json·ZIP_SHA256.txt, testzip·내용 대조 OK. OneDrive 폴더 안·OneDrive 실행 중, 클라우드 업로드 완료 여부는 미확인.
- 캐릭터: 제작 사양 `characters/hamtorich_01/EXPRESSION_SPEC.md`(공통 측정값·4종별 기준 몸/눈/눈썹/입·등록 이름·검수표),
  참고판 `output/_character_refs_2026-10-21/hamtorich_expression_reference.png`. 원본 포즈·bible 변경 없음, 그림은 사용자 제작.

### 테스트

- 2026-10-21 전체 `unittest discover`: **406개 통과**(V1.0 405 + 훅 표지 줄 균등 1).

### 진행 (2026-11-17, Claude, 미커밋) — YouTube 링크 → 화면 캡처 인용 쇼츠 실사용
- 방식: 내장 브라우저로 링크를 열고 `<video>` 프레임을 canvas 로 그려 전체 화면에 띄운 뒤 스크린샷(800x450 파일) → `make --topic … --quote 캡처 --quote-source "제목 | 채널 | URL"`.
  영상 녹화·다운로드는 하지 않는다(정지 화면만). 자막 없는 영상은 `--url` 을 쓰면 V1 이 음성 인식용 오디오를 내려받으므로 topic 모드 + 관찰을 `--instructions` 로 넣었다.
- 코드: `run._choose_benchmark` 근거 게이트가 인용 캡처(이미지)도 근거로 인정(kpop_observation_clip 후보 가능) ·
  `quote._take_images` 캡처를 파일명 단어(예: `b_0m20s_배경_보라.jpg`)와 장면 나레이션이 겹치는 장면에 배치(이전: 파일 순서 → 장면·캡처 어긋남). 테스트 1개 추가.
- 실제: 베스티 '연애의 조건' 인기가요(2026-11-15) → 최종 `output/20261117_222547_451a/final.mp4` 28.5초·5장면, kpop_observation_clip 90점, 인용 3장면(엔딩 의상·댄서 대비·디자인 비교), 검증 통과.
  앞선 2편은 폐기 사유: 캡처-장면 어긋남(`221624_8b47`), 다른 방송(음악중심) 조회수를 이 무대 것처럼 씀 + 주제 날짜 오기(`222155_3a7c`). 캡처 원본 `output/_captures/bestie_20251115/`.
- 팬튜브 결정(사용자): 링크로 준 원본은 막지 않고 내려받아 편집. `make --url L --quote L` → `youtube.download_quote`(재생목록 제외·1080p·무음) →
  `uploads/quote_<id>.mp4`, 출처 자동. 자동 탐색이 찾은 YouTube 는 계속 미다운로드. AGENTS.md '원본 영상 링크 편집'. 테스트 1개 추가(다운로드는 가짜).
- 팬튜브 실제(돌토리 구조 지정): `output/20261118_000850_71b6/final.mp4` 27.5초, 원본 링크 자동 다운로드, 인용 3장면(3:10 엔딩·2:52 대열·3:14 클로즈업), 출처 표기·검증 통과.
  첫 시도 `20261117_235847_97b2` 는 장면-구간 어긋남 → `quote._scene_prefer`(문구 속 시각 '삼 분 십사 초'·근거 설명 단어로 장면별 근거 구간) 수정, 테스트 2개.
- 팬 클립(2026-11-18, 사용자 요청 + 돌토리 화면 재확인): 새 명령 `fanclip --url L` (`app/pipeline/fanclip.py`, `core.fanclip`). 원본 영상·소리만,
  위 2줄 제목·영상 위 검정 박스 자막·아래 `출처 - 채널 · 제목`(없으면 거부), Pretendard(`assets/fonts`, OFL). AI 1회로 구간·제목·자막 선택. 실제 `output/20261118_213341_dcc8/final.mp4` 29.2초.
  AGENTS.md: 팬튜브 기본 = fanclip. 테스트 `tests/test_fanclip.py` 4개.
- 팬 클립 대본 학습(2026-11-18): 구독 대비 조회수 높은 연예 쇼츠 4곳(연예소식뉴스 1.4만/중앙값 28만, 아이돌탐정 5.2만/49만, 디테일 9.5천/9.7만,
  잠깐만아이돌 1.1만/8.8만) 프레임 판독 → `benchmarks/sources/*.json` 4개·BENCHMARKS 현황판. `fanclip.SYSTEM` 이야기형 자막·반전·한줄평·괄호 속마음(voice),
  ㅋㅋ 2번 제한, 긴 자막 두 줄, 기본 20초. 실제 `output/20261118_220036_cfb0/final.mp4` 20.3초. 테스트 test_fanclip 5개 통과. 전체 415개 중 414 통과(기존 topics 1개 실패, 무관).
- 테스트: 전체 414개 중 413 통과, `test_topics...test_cli_rank_approve_create_dry_run` 1개 실패 — 이 변경과 무관(변경을 빼도 실패, 날짜 의존 추정, 별도 작업 제안).

### 완료 (2026-11-18, Claude, 커밋) — 영상 연출 도구 13종 설치 (렌더 연결은 아직 없음)
- PC: Node.js 26 LTS·uv·Blender 5.3 (winget). `motion/` = Remotion 4.0.545(+lottie·three)·anime.js·motion·three·three-gpu-pathtracer·jolt-physics·postprocessing·three.quarks·tweakpane·react 19
  (`npm install`, node_modules·out 은 `motion/.gitignore`), Remotion 2초 테스트 렌더 OK. Remotion Skills 13개 `.claude/skills/remotion-*`. Manim 0.22.1 → `.venv`(기존 패키지 변경 없음).
- Blender MCP: 애드온 `motion/blender/blender_mcp_addon.py` 설치·활성(localhost:9876, 외부 자산 서비스 기본 꺼짐), Claude Code local MCP `blender`(uvx blender-mcp) 연결 확인.
- Remotion 라이선스: 개인·3인 이하 회사 무료. 다음: fanclip 렌더를 Remotion 으로(자막 팝업·원·화살표) — 사용자 요청 시.

- 베스티 팬 클립 최신본(벤치마크 대본 규칙): `output/20261118_223447_bc27/final.mp4` 22초. 3번 장면 댄서 구간만 58~62초로 수동 조정 후 재렌더.
  설치 방법 요약 `motion/README.md`. 전체 테스트 415개 중 414 통과(기존 topics 1개 실패, 무관).

## 남은 작업 / 다음 작업 (V1.0 판단 단계 — 새 기능 추가 보류)

- [별도 브랜치] 캐릭터·그림체 확장 시제품: 작업 폴더 `../shorts-ai-styles`(브랜치 `feature/character-styles`, 미커밋). 상세 그 폴더의 `docs/CHARACTER_STYLES_2026-10-21.md`.
- V1.0 전 권장: 햄토리치 감정 포즈(슬픔·놀람·무표정·생각) 그림 추가(목록 `characters/hamtorich_01/README.md`, 사용자 제작),
  게시 전 수치 확인 습관(카드에 나온 숫자를 출처와 대조), 카드뉴스는 직접 찍은 사진·그림을 '이미지 넣기'로 보강.
- [승인 대기] 최적화 5단계: 옛 MVP 데모·verify 스크립트 4개 `scripts/legacy/` 이동 또는 삭제.
- [승인 대기] 최적화 6단계: Git 밖 대용량(reference.mp4 1GB, output 319MB) 정리 — 사용자 데이터.
- [보류] Gemini 포즈·배경 54장 생성은 중단 상태. `--confirm-cost` 와 사용자 승인 없이는 호출하지 않는다.
  사용자가 `.env` 에 `GEMINI_API_KEY` 를 직접 넣어야 한다(채팅으로 키를 받지 않음).
- 인스타툰: 품질 기준은 `samples/` 의 B 버전. 무료 경로(코드 장면 + ChatGPT 등으로 만든 그림을 `assets/inbox/` 로)가 기본.

## 주의

- 유료 API·commit·push·위험한 삭제·대규모 구조 변경은 사용자 승인 후.
- 다른 세션의 미커밋 변경을 덮어쓰지 않는다. `.env`·키·output·캐시는 커밋하지 않는다.
