# 카드뉴스·인스타툰 PC 프로그램(스튜디오) 계획 (2026-10-16, S1~S4 완료)

목표: 혼자 쓰는 로컬 프로그램. 주제 → 장수·스타일 선택 → 문구·스토리 생성 → 장면 그림 → 미리보기 → 카드별 수정·재생성 → PNG 저장.
쇼츠 기능·CLI·테스트는 그대로 둔다. UI 는 A(기존 FastAPI 에 /studio) 로 승인됨. 페이지가 하나라 `app/studio/studio.html` 한 파일(인라인 CSS·JS).

## 1. 현재 흐름

```
make --format card_news|insta_toon|hybrid  → core._make_carousel → carousel.pipeline.run_carousel
toon --topic --facts-from-topic           → factory.toon.run → story_writer.write_story → run_carousel(prepared_plan)

run_carousel (한 함수에서 끝까지):
  1 gather_inputs (리서치·기사·원고)  2 build_master (Claude 또는 규칙)  3 plan_pages (6~10장)
  4 find_card_images(공개 사진) + CharacterArtist(포즈·마스코트·AI)  5 페이지별 render_page → card_NN.png
  6 manifest.json · plan.json · master.json · sources.json · caption.txt
```

## 2. 구분

| 구분 | 내용 |
|---|---|
| 이미 있음 (그대로 재사용) | 자료 수집·Master·페이지 계획·스토리 작가(규칙/Claude, 사실 검증)·템플릿 4종·렌더러(카드 8종+만화 컷, 실패 시 safe)·캐릭터 등록·포즈 그림·받은편지함·출처 대장·캡션. 결과물(plan.json/master.json)이 이미 파일로 저장됨 |
| 재사용하되 손볼 곳 | `run_carousel` 이 준비→그림→렌더→저장을 한 번에 함. 루프 안의 "페이지 1장 그리기"를 함수로 꺼내야 카드 1장만 다시 그릴 수 있음. `prepared_master/plan` 경로가 이미 있어 "수정한 계획으로 다시 렌더"는 거의 됨 |
| 새로 필요 | ① 프로젝트 단위 엔진(열기·수정·1장 재렌더·장면 재생성·내보내기) ② UI 화면 ③ 장면 재생성용 변형 값(포즈·감정·배경 바꾸기) ④ ZIP 내보내기 |
| 기존 웹 UI | `app/main.py`(FastAPI) + `app/static/app.js`(1,342줄)는 쇼츠 전용. 캐러셀 화면은 없음. 실행기 `AI Shorts 실행.cmd` → `app/launcher.py` → 127.0.0.1:8765 |

## 3. UI 방식 검토

| | A. 기존 FastAPI 에 `/studio` 화면 추가 (추천) | B. Streamlit |
|---|---|---|
| 설치 | 추가 패키지 없음, 기존 실행기 그대로 | streamlit + 의존성 약 100MB 추가, 실행기 따로 |
| 오래 걸리는 작업 | 기존 jobs·SSE 진행률 재사용, 화면이 안 멈춤 | 버튼마다 스크립트 전체 재실행, 비동기(Claude SDK) 처리 어색 |
| 카드별 수정·재생성 | 카드 1장 단위 API 로 자연스러움 | session_state 로 상태 관리, 카드 많으면 느려짐 |
| 개발 속도 | HTML/JS 를 써야 함(작은 파일 하나로 제한) | 빠름 |

추천: **A**. 이미 같은 서버·실행기·파일 제공 경로가 있어 새 설치가 없고, 쇼츠 화면(app.js)과 섞지 않도록 `app/studio/` 에 별도 작은 페이지(`studio.html`·`studio.js`)로 만든다.

## 4. 엔진 분리 (CLI·UI 가 같이 씀)

`app/studio/project.py` — 작업 폴더(output/<id>) 하나 = 프로젝트. 상태는 지금처럼 plan.json·master.json·manifest.json 파일.

| 함수 | 하는 일 | 재사용 |
|---|---|---|
| `create(topic, fmt, pages, template, writer)` | 자료→Master→계획까지(그림 전) | gather_inputs, build_master, plan_pages / write_story |
| `render_all(pid)` | 그림 찾기 + 전체 렌더 | run_carousel(prepared_plan) |
| `update_page(pid, n, fields)` | 카드 n 문구 수정 → plan.json 저장 → n장만 다시 그림 | 새 `render_one` |
| `regenerate_scene(pid, n, change)` | 포즈·감정·배경·카메라를 바꾸거나 다음 후보 그림으로 → n장만 | CharacterArtist, scenes |
| `export(pid)` | PNG 전부 + caption.txt + sources.json 을 ZIP | 기존 파일 |

`run_carousel` 수정은 루프 몸통을 `render_one(...)` 으로 꺼내는 것만(동작 동일, 기존 테스트로 확인). AI 그림(Gemini)은 지금 규칙대로 비용 확인 후에만.

## 5. MVP 화면 (한 페이지, 3단계)

1. **만들기**: 주제 입력 · 형식(카드뉴스/인스타툰/섞기) · 장수(6~10) · 템플릿 · 글 작성(Claude 구독/규칙) → [만들기] + 진행률
2. **미리보기·수정**: 카드 썸네일 줄 → 카드 선택 시 큰 그림 + 오른쪽 수정 칸(제목·본문·항목 / 컷별 대사·감정·자세) → [이 카드 다시 그리기] [장면 바꾸기]
3. **저장**: [PNG 전부 저장(ZIP)] [폴더 열기], 캡션 복사. 왼쪽에 최근 프로젝트 목록.

뺀 것(MVP 이후): 드래그 편집, 카드 순서 바꾸기·추가·삭제, 여러 사용자, 업로드 편집기, 예약 게시.

## 6. 단계 (단계마다 전체 테스트, 커밋은 승인 후)

| 단계 | 내용 | 위험 |
|---|---|---|
| S1 | `render_one` 추출 + `app/studio/project.py` 엔진 + 테스트(모두 mock) | 낮음 — run_carousel 내부만 |
| S2 | API 6개(`/api/studio/...`): 만들기·상태·카드 수정·장면 재생성·ZIP·목록 | 낮음 — 새 경로만 추가 |
| S3 | `studio.html`/`studio.js` 화면, 실행기 첫 화면에 '카드뉴스·인스타툰' 링크 | 낮음 |
| S4 | 실제 1편 확인(Claude 구독 호출 2~3회, 무료 그림) — 사용자 승인 후 | 사용 승인 필요 |
| S5 | HANDOFF·AGENTS 명령표 갱신 | 없음 |
