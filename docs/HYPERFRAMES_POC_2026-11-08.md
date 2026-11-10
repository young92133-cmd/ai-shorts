# HyperFrames 1단계 — 10초 PoC 실제 제작 결과

2026-11-08, `shorts-ai-codex`, `codex/shorts-handoff-20261106`, 기준 커밋 `7a5d7da`.
사용자 승인 범위인 설치·독립 PoC·검증을 완료했다. 기존 제작 파이프라인 통합은 하지 않았다.

## 설치

| 항목 | 설치 결과 |
| --- | --- |
| Node | 24.22.1, Codex 내부 바이너리를 `.tools/hyperframes/node.exe`로 복사. 원본 수정 없음 |
| npm / npx | 12.2.2, 공식 npm 배포 SHA-512 확인. `.tools/hyperframes/npm/` |
| HyperFrames | **0.9.23**, `renderers/hyperframes/package.json` 및 lockfile에 정확히 고정 |
| GSAP | **3.14.2**, 로컬 JS 사용 |
| Chrome Headless Shell | **152.0.7977.30**, `.tools/hyperframes/cache/chrome/` |
| FFmpeg | 기존 **9.0.1** 사용, 재설치·Python 의존성 변경 없음 |
| 한국어 폰트 | 기존 `C:/Windows/Fonts/NotoSansKR-VF.ttf`를 PoC에 복사, Google Fonts 공식 OFL 동봉 |

0.9.19→0.9.23의 릴리스 변경을 확인했다. 한국어 숫자·조사 단위 검사(0.9.20),
타임라인/렌더 시간 처리(0.9.20–22), 페이드인 종료 상태(0.9.23) 수정이 있어 0.9.23을 선택했다.
Node 24.22.1은 HyperFrames의 Node ≥22와 npm 12.2.2의 Node ^24.15.0 조건을 충족한다.

## 실제 영상

- 파일: `output/hyperframes-poc-20261108/hyperframes-poc-10s.mp4`
- 파일 크기: **773,502 bytes**, 약 **0.738 MiB**.
- SHA-256: `f00c430fd6de47c6609d4866139c0b46861a40addebfacb0a903caed9cc62270`
- ffprobe: **H.264, yuv420p, 1080×1920, 30/1 fps, 300프레임, 10.000000초**.
- 오디오: **AAC, 48,000 Hz, stereo, 10.000000초**.
- 음원은 로컬 FFmpeg로 만든 330Hz 테스트 톤이다. 대본·TTS·음악 생성 API는 호출하지 않았다.

제목: “움직임으로 / 전달하는 숫자”. 0→100 카운트업, 세 막대의 순차 성장,
“한국어도, 움직임도 / 또렷하게.”로 바뀌는 크로스페이드가 들어간다.
이는 테스트 데이터이며 경제·공학 콘텐츠 프리셋이 아니다.

## 측정

| 측정 | 결과 |
| --- | --- |
| HyperFrames 엔진 보고 렌더 시간 | **17.2초** |
| 전체 실행 경과 시간 | **20.711초** (초기화·종료·측정 포함) |
| 렌더 워커 | **2** |
| 프로세스 트리 관측 최대 working set 합계 | **2,295,447,552 bytes / 2.138 GiB** |
| 프로세스 트리 관측 최대 private bytes 합계 | **1,861,869,568 bytes / 1.734 GiB** |
| 설치·캐시·의존성·PoC·출력 논리 파일 크기 | 약 **570 MiB** |
| 렌더 중 관측 논리 파일 크기 피크 | **663,074,122 bytes / 약 632 MiB** |

메모리는 렌더 Node와 그 자손(Chrome·FFmpeg 등)의 합계다. 공유 페이지는 working set에서
중복 계산될 수 있다. 38회 샘플, 샘플 사이 sleep 0.2초, 측정 작업을 포함한 실제 평균 간격 약 0.54초다.
따라서 순간 최대를 보장하는 계측치가 아닌 **관측 피크**다. 디스크는 전용 tools·renderer·output
폴더를 약 1초 간격으로 합산한 논리 크기이며 할당 클러스터 사용량과 다르다.
장시간 영상 통합 전 1 worker·저메모리 모드 비교가 필요하다.

## 검증

- HyperFrames `check --strict`: lint/runtime/layout/motion/contrast/craft/audio 모두 오류 **0**, 경고 **0**.
- 실제 MP4 디코딩 **300프레임**의 상단 250px·하단 400px·우측 150px 배제영역에 전경 침범 없음.
- 숫자: 실제 프레임 1.40/2.07/2.70/3.37/4.00초에서 **0·26·50·76·100** 확인.
- 막대: **4.167·4.967·5.767초**부터 차례로 성장, 최종 디코딩 높이 **96·168·240px**, 되감김 없음.
- 제목 등장과 마무리 전환은 실제 디코딩 픽셀 변화로 확인.
- 한글: 사용한 **52개 한글 글리프 누락 0**, 1·5·9초 캡처 육안 확인에서 깨짐·잘림 없음.
- 음성 트랙 실제 PCM 디코딩: RMS 0.00921, peak 0.01339. 무음·클리핑 없음(조용한 테스트 톤).
- 로컬 미리보기 `http://127.0.0.1:3017/#project/poc`를 띄워 HTTP 200 확인 후 렌더했다.
- 기존 Python 제작 엔진은 변경하지 않아 2026-11-06의 **343개 통과** 검증은 반복하지 않았다.

최초 시각 검사에서 작은 글자·마무리 표시 시간·컨테이너 경고를 수정했다. 영상 검증기는
글자 페이드가 막대와 비슷한 색이 되는 픽셀을 높이로 세지 않도록 바닥에 붙은 연속 영역만 측정한다.

## 산출물과 재실행

- `frames/01s.png`, `frames/05s.png`, `frames/09s.png`: 완성 MP4에서 추출한 원본 크기 캡처.
- `comparison-1s-5s-9s.png`: 3개 시점 비교 이미지.
- `counter-motion.png`: 실제 숫자 변화 비교.
- `verification.json`, `ffprobe.json`, `font-check.json`, `hyperframes-check.json`: 검증 증거.
- `render.log`, `render-metrics.json`, `memory-samples.json`, `disk-usage.json`, `installation.json`: 환경·계측.
- 실행법은 `renderers/hyperframes/README.md`, 래퍼는 `scripts/hyperframes.ps1`.

공식 CLI 초기 실행에서 사용자 홈 `~/.hyperframes/`에 install/run 설정 메타데이터가 생성됐다.
이 상태는 삭제하지 않았다. 이후 래퍼는 캐시·설정·임시 경로를 `.tools/hyperframes/`에 고정하고
환경 변수를 종료 시 복원한다. 전역 npm/PATH, 기존 Node, Python 환경, 기존 FFmpeg 엔진은 수정하지 않았다.

## 다음 단계 — 사용자 결과 확인 후 별도 승인

1. 기본 FFmpeg를 유지한 선택형 렌더러 연결 지점을 설계하고 관련 회귀 테스트를 준비한다.
2. 기존 timeline.json을 확장한다. 새 입력 JSON 체계를 중복 개발하지 않는다.
3. `presets/render/` 및 같은 대본 `--variants 3`은 다음 단계에서 구현한다.
4. 공개 자료 적합성·정적 화면·사실 확인·근거 부족 시 forced_fallback 제어를 순차 개선한다.

이번에는 app/pipeline, timeline.json, Python 의존성을 수정하지 않았고,
Claude Code 플러그인·에이전트 스킬 설치, 유료 API 호출, commit/push도 하지 않았다.

근거: [공식 README](https://github.com/heygen-com/hyperframes/blob/v0.9.23/README.md),
[0.9.23 릴리스](https://github.com/heygen-com/hyperframes/releases/tag/v0.9.23),
[공식 차트 컴포넌트](https://github.com/heygen-com/hyperframes/blob/v0.9.23/registry/components/animated-bar-chart/animated-bar-chart.html),
[Noto Sans KR 및 OFL](https://github.com/google/fonts/tree/main/ofl/notosanskr).
