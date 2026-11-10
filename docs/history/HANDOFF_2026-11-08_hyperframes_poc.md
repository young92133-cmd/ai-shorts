# HANDOFF — 현재 상태

> 공통 규칙은 AGENTS.md. 현재 상태는 80줄 이하로 유지한다.
> 이전 원문은 docs/history/HANDOFF_2026-11-06_before_hyperframes_2026-11-08.md에 보존했다.

## 현재 상태 (2026-11-08, Codex) — HyperFrames 1단계 PoC 완료

- 작업 폴더: `shorts-ai-codex`, 브랜치 `codex/shorts-handoff-20261106`, 기준 `7a5d7da`.
- 2026-11-06 인수인계 검증 완료. 이번에는 승인된 설치·10초 PoC만 실제 진행했다.
- 다음 단계는 사용자 영상 확인 후 별도 승인. **기존 Shorts 파이프라인 통합은 아직 금지.**
- 기존 FFmpeg 엔진·Python 가상환경·timeline.json은 변경하지 않았다.
- 다른 worktree와 미커밋 변경·사용자 결과·백업은 보존. commit/push 하지 않았다.

## HyperFrames 설치

- Node `24.22.1`: 기존 Codex 내부 실행 파일을 `.tools/hyperframes/node.exe`로 복사, 원본 보존.
- npm/npx `12.2.2`: 공식 npm 배포본의 SHA-512 무결성 확인 후 `.tools/hyperframes/npm/`에 설치.
- HyperFrames **0.9.23**, GSAP **3.14.2**: `renderers/hyperframes/package.json`·lockfile로 고정.
- 0.9.19 이후 한국어 숫자 검사·렌더 타이밍·페이드인 종료 수정이 포함돼 0.9.23 선택.
- 전용 Chrome Headless Shell `152.0.7977.30`: `.tools/hyperframes/cache/chrome/`.
- 기존 FFmpeg `9.0.1` 사용. Noto Sans KR는 Windows 설치본을 PoC assets/fonts/에 복사, 공식 OFL 동봉.
- 실행 래퍼: `scripts/hyperframes.ps1`. Node/npm·캐시·설정·임시 경로는 프로젝트 전용, 환경 변수는 실행 후 복원.
- Claude Code 플러그인·에이전트 스킬은 설치하지 않았고 유료 API도 호출하지 않았다.

## 10초 PoC 결과

- 영상: `output/hyperframes-poc-20261108/hyperframes-poc-10s.mp4` (773,502 bytes).
- ffprobe: H.264/yuv420p, 1080×1920, 30fps, 300프레임, 정확히 10.000초.
- 오디오: AAC, 48kHz, stereo, 10.000초. 로컬 합성 테스트 톤이며 무음·클리핑 없음.
- 한국어 제목 등장·0→100·막대 3개 순차 성장·마무리 크로스페이드 확인.
- 렌더 엔진 17.2초, 전체 실행 20.711초(2 workers), 관측 최대 작업 집합 합계 2.138 GiB.
- 설치·의존성·PoC·출력 약 570 MiB, 렌더 중 관측 디스크 피크 약 632 MiB(논리 파일 크기).
- 브라우저 엄격 검사: lint/runtime/layout/motion/contrast/craft/audio 오류·경고 모두 0.
- 완성 MP4 300프레임 안전영역 검사 통과: 상단 250·하단 400·우측 150px 침범 없음.
- 실제 디코딩 프레임: 카운터 0·26·50·76·100, 막대 시작 4.167·4.967·5.767초, 최종 높이 96·168·240px.
- 사용 한글 52자 모두 폰트 글리프 존재, 1·5·9초 캡처 육안 확인: 깨짐·잘림 없음.
- 검증 기록·비교 이미지·ffprobe·메모리 샘플은 위 output 폴더. 상세: `docs/HYPERFRAMES_POC_2026-11-08.md`.
- 검증 실행: 기존 공유 Python으로 `renderers/hyperframes/verify_poc.py` (기존 제작 엔진을 import하지 않음).
- 기존 Shorts 전체 테스트는 2026-11-06 **343개 통과**. 엔진 무변경으로 이번에 반복 실행하지 않았다.

## 이미 완료된 Shorts 기능 (재검증·재제작 불필요)

- 주제→Claude 구독 대본→MP4, 대본 검토·수정·승인, 실패 후 resume, 순차 제작.
- 경쟁 채널 CLI analyze/topics/make/auto 및 웹 화면. 짤잉 상세 45편·패턴 5개·추천 5개 분석 완료.
- C: `batch_20261105_232321_ab58` 2/2 완료(25.63·25.51초).
- D: `../shorts-ai-shorts/output/20261106_221220_cad4` 22.2초 완성, 자막 겹침 0.0.
- 주제→검토→수정→MP4 실제 성공 기록 `../shorts-ai-shorts/output/20261105_231559_d127`(29.7초).
- Edge TTS 7.3.1 업데이트·한글 줄바꿈·후킹 화면 수정 완료. 옛 미검증·업데이트 대기 안내는 현재 작업이 아니다.
- 기존 제작 결과·채널 캐시는 `../shorts-ai-shorts/output/`에 있으며 새 worktree로 복사하지 않았다.

## 다음 작업 (승인 후)

1. 이번 영상 확인 → 선택형 HyperFrames 연동 설계·관련 회귀 테스트. 기본 FFmpeg 유지.
2. 기존 timeline.json 확장, presets/render/*.json, 같은 대본 --variants 3 (추가 AI 호출 없이).
3. 공개 이미지의 장면 적합성, 자료가 없을 때의 움직임, 사실 근거, forced_fallback 제어 개선.
4. 메모리 2.14 GiB는 2 workers의 관측치. 긴 영상 통합 전 1 worker·저메모리 모드도 비교 필요.

## 유지 규칙

- 카드뉴스·인스타툰·캐릭터 기능은 제거 상태 유지. app/pipeline/cards.py는 Shorts 공통 그래픽이라 반드시 유지.
- 사용자 데이터·backups·samples·characters·reference·가상환경 삭제 금지.
- 유료 API·commit/push·파이프라인 통합은 별도 승인 필요. C·D 제작 반복 금지.
