# 경량화·토큰 절약·자동 인수인계 계획 (2026-10-14, 1~4단계 완료 2026-10-16 · 5~6단계 승인 대기)

분석만 했고 코드·파일은 바꾸지 않았다. 각 단계는 승인 후 진행하고, 단계마다 전체 테스트(현재 382개)를 돌린다.

## 현재 측정값 (기준선)

| 항목 | 값 |
|---|---|
| Git 관리 대상 파일(무시 제외) | 223개 |
| Python | app 91파일 17,788줄 (pipeline 9,395 · carousel 3,749 · factory 1,851 · topics 1,616), tests 18파일 5,678줄, scripts 8파일 951줄 |
| Markdown | 3,907줄 — HANDOFF 1,349줄(163KB), IMPLEMENTATION_PLAN 598줄(68KB), AGENTS 288줄(34KB), CLAUDE 288줄(34KB, AGENTS와 거의 같은 복사본) |
| 디스크 | 전체 1,879MB — reference.mp4 1,037MB(Git 제외), .venv 466MB, output 319MB(Git 제외), samples 13MB, characters 10MB, assets 10MB, .git 11MB, app 2MB |
| 테스트 | 382개 통과 (2026-10-09) |
| Git | 원격과 동기화(4ee9e92). 미커밋 33개 = 10-09 Claude 작업(이후 다른 세션이 일부 수정) |

## 발견 사항

1. **토큰 낭비가 가장 큰 곳은 문서다.** CLAUDE.md 와 AGENTS.md 가 거의 같은 288줄을 따로 들고 있어 Claude 는 매 세션 약 1만 토큰을 자동으로 읽고,
   두 파일을 같이 고쳐야 해서 어긋날 위험이 있다. HANDOFF.md 는 기록이 누적돼 전부 읽으면 4~5만 토큰이다.
2. **참조가 0인 함수 8개** (이름 검색 + AST, 테스트·스크립트·웹 정적 파일 포함 확인):
   `pipeline/render.render_clips`(65줄, 유튜브 원본 클립 모드는 권리 문제로 막혀 있음), `pipeline/assets.resolve_visuals`(22), `assets.save_upload`(14),
   `clips.retime_words`(11), `article.credit_line`(8), `run._find_bgm`(7), `carousel/effects.screentone`(8), `carousel/asset_gen.report_json`(2).
   (main.py 의 함수들은 FastAPI 데코레이터로 등록되는 경로라 사용 중 — 제거 대상 아님.)
3. **같은 코드 중복**: 글꼴 로더 4벌(`cards._font` = `images/base._font` 완전 동일, `quote._font`, `carousel/render.font`),
   `_strip_tags` 2벌(`research`, `article` 완전 동일). 나머지 같은 이름 함수(`words_to_lines`, `_info_sync`, `_shade`, `_clamp` …)는 동작이 달라 합치지 않는다.
4. **오래된 개발 스크립트**: `scripts/demo_script_split_mvp.py`, `demo_blueprint_mvp.py`, `verify_visuals.py`, `verify_tts_timeline.py` 는
   문서(HANDOFF·IMPLEMENTATION_PLAN·README)와 테스트 한 곳에서만 언급된다. `verify_factory_v1.py` 는 규칙 문서에서 쓰는 검증 도구라 유지.
5. **디스크**: 가장 큰 것은 Git 밖 사용자 데이터(reference.mp4 1GB, output 319MB). 자동 삭제 대상 아님.

## 단계별 계획

| 단계 | 내용 | 위험 | 예상 효과 |
|---|---|---|---|
| 0 | 현재 미커밋 작업을 먼저 커밋(사용자 승인 시) — 경량화 변경과 섞지 않기 위해 | 낮음 | 되돌리기 기준점 |
| 1 | **문서 단일화**: AGENTS.md = 공통 규칙(명령·권리·비용·테스트·Git·작업 원칙·인수인계 규칙)으로 정리해 줄이고, CLAUDE.md 는 `@AGENTS.md` 가져오기 + Claude 전용 몇 줄(구독 경로·메모리)만 | 낮음 | 자동 로드 약 1만 → 5천 토큰 이하, 규칙 충돌 제거 |
| 2 | **HANDOFF 경량화**: HANDOFF.md 를 '현재 상태' 한 장(≤80줄: 현재 작업·완료·남은 작업·수정 파일·테스트·다음 작업·주의)으로 만들고, 기존 기록은 `docs/history/HANDOFF_2026-09_10.md` 로 그대로 옮김(삭제 없음). IMPLEMENTATION_PLAN 도 완료 단계는 history 로 | 낮음 | 인수인계 읽기 4~5만 → 3천 토큰 |
| 3 | **공통 모듈 통합**: `app/pipeline/fonts.py` 하나로 글꼴 로더 통합(기존 이름은 얇은 별칭으로 유지), `_strip_tags` 를 `article` 하나로 | 낮음 | 중복 4곳 제거, 글꼴 찾기 규칙 한 곳 |
| 4 | **미사용 코드 제거**: 위 8개 함수 삭제(참조 재확인 후) | 낮음~중간 | 약 140줄 |
| 5 | **오래된 스크립트 정리**: MVP 데모 2개·verify 2개를 `scripts/legacy/` 로 이동 또는 삭제(사용자 선택) | 중간 | 4파일 |
| 6 | (선택, 승인 필요) Git 밖 대용량: reference.mp4 를 프로젝트 밖(또는 OneDrive 온라인 전용)으로 이동, output 은 `scripts/backup_outputs.py` 로 ZIP 후 정리 | 사용자 데이터 | 디스크 최대 1.3GB |

하지 않는 것: 파이프라인 구조 변경, 동작이 다른 동명 함수 통합, 웹 UI 경로 정리, 테스트 삭제.

## 앞으로의 공통 작업 원칙 (AGENTS.md 에 넣을 문안)

1. 시작: `git status` → `HANDOFF.md`(현재 상태 한 장)만 읽는다. 전체 저장소를 다시 훑지 않는다. 필요한 파일만 `rg` 로 찾아 읽는다.
2. 개발: 기존 코드 확인 → 재사용 → 중복 방지 → 안 쓰는 코드 정리 → 변경 범위 테스트 → 전체 테스트(커밋 전).
3. 출력: 결과 요약 위주, 긴 로그·파일 전체 출력 금지. 끝난 테스트를 같은 상태에서 반복하지 않는다(코드가 바뀌면 다시).
4. 종료·전환 전: HANDOFF.md '현재 상태'를 갱신(현재 작업·완료·남은 작업·수정 파일·테스트 결과·다음 작업). 자세한 기록은 `docs/history/`.
5. 보호: 다른 세션의 미커밋 변경을 덮어쓰지 않는다. 위험한 삭제·대규모 구조 변경·commit/push 는 사용자 승인 후.
