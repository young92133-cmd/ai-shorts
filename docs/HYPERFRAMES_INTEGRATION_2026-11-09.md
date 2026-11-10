# HyperFrames 2단계 — 기존 AI Shorts 최소 통합

2026-11-09, `shorts-ai-codex` / `codex/shorts-handoff-20261106`, 기준 `7a5d7da`.
Node 24.22.1 / npm 12.2.2 / HyperFrames **0.9.23** / Chrome Headless Shell 152.0.7977.30 / FFmpeg 9.0.1.
설치 버전·잠금 파일·PoC는 이번 작업에서 바꾸지 않았다. 새 버전 알림은 있었으나 자동 업데이트하지 않았다.

## 변경 구조

- `app/pipeline/timeline.py`: 공통 렌더러 선택, 출력 덮어쓰기 방지, 요청/실제 렌더러·폴백·실패 기록.
  기존 FFmpeg 본문은 `_render_ffmpeg`로 분리했으며 ASS의 저장 위치만 새 렌더 폴더로 바뀐다.
- `app/pipeline/hyperframes.py`: V1 timeline → 로컬 HTML 어댑터, 경로/시간/텍스트 검증,
  기존 단어 시간 재사용, 자막 줄 구성·하이라이트, 영상 구간/정지 처리, 별도 오디오 믹스, 프로세스 제한·로그.
- `renderers/hyperframes/{timeline,scene}.html`: 루트와 하위 합성 템플릿. 콘텐츠 입력 JSON을 새로 만들지 않는다.
- `app/pipeline/run.py`: 제작·재렌더 공통 렌더러 설정 전달. 재렌더는 고유 경로에 MP4·썸네일을 남긴다.
- `app/factory/{core,__main__}.py`: `make`·`rerender`에 `--renderer`, `--renderer-fallback`, 실제 결과 경로/렌더러 기록.
- `config.yaml`: 기본 ffmpeg, 기본 fallback none, 선택형 HyperFrames 설정.
- `app/pipeline/sources.py`: 선택형 효과음도 기존 권리 대장 검사에 포함.
- `tests/test_hyperframes.py`: 신규 **34개**. 기존 343개 테스트는 삭제하지 않았다.
- `scripts/compare_renderers.py`, `scripts/verify_renderer_comparison.py`: 실제 CLI 비교·계측·완성 파일 검증.
- 기존 렌더 엔진 `app/pipeline/render.py`와 TTS 코드는 수정하지 않았다.

## 보호·입력·실패 처리

- 시작 당시 미커밋 파일과 PoC 결과 40개를 `../backups/hyperframes-phase2-20261109/`에 ZIP·patch·SHA로 보존했다.
- PoC 소스·설정·package-lock·성공 결과를 유지했다. Node·node_modules·브라우저·캐시·output은 Git 제외.
- 다른 worktree의 status/diff 해시 및 원본 프로젝트 전체 파일 SHA를 비교한다. commit/push 하지 않았다.
- 입력은 기존 timeline.json. 새 `render` 설정만 선택적으로 추가하며, 기존 파일은 그대로 읽을 수 있다.
- HTML·캡션 맵·미디어 manifest는 재생성 가능한 렌더 산출물이다.
- HTML 텍스트는 `html.escape`, 색상/시간은 검증한 값만 사용. AI 문구를 JS에 삽입하지 않는다.
- 경로는 잡 폴더·저장소 assets·명시적 신뢰 폴더 안의 로컬 미디어만 허용한다.
  Windows 절대/상대 경로와 한글/공백을 지원하며 URL·UNC·디바이스·드라이브 상대·상위 탈출을 거절한다.
- 자막은 기존 단어 start/end를 보존하고 약 14자·최대 2줄·단어/문장 경계를 우선한다. 긴 단어는 축소해서 유지한다.
- BGM·효과음 없음은 정상 처리, 경로를 줬는데 파일이 없으면 명확한 오류. 덕킹은 HyperFrames 전용 사전 믹스 옵션.
- 동시 HyperFrames 렌더 1개, Chrome worker 1개. OS lock과 자체 프로세스 트리 종료로 실패·취소를 격리한다.
- 폴백은 기본 none. 명시적으로 ffmpeg를 켠 경우만 도구/실행 오류에 대체한다. 보안·입력 검증 오류는 대체하지 않는다.
- 새 출력/sidecar를 독점 생성한다. 실패 로그와 attempt는 보존하며 이전 MP4·썸네일·timeline을 덮어쓰지 않는다.

## 실제 비교 대상

- 원본: `../shorts-ai-shorts/output/20261105_231559_d127` (난방비 쇼츠, 공개 계량기 영상 + 카드 + CC BY 사진).
- 읽기 전용 원본에서 `output/20261109_hf_comparison`으로 37개 파일을 복제했다.
- 복제본의 권리 대장 경로/id만 새 위치에 맞췄고, timeline·대본·장면·음성은 재사용했다.
- **대본/AI/TTS 재생성 0회**. 원본 AI 기록과 복제본 기록이 같고, 음성·원본 파일 SHA도 유지됐다.

### A. 기존 FFmpeg

`output/20261109_hf_comparison/renders/rerender_ad41ade184164e2992febbe77b6f6ccd/final.ffmpeg.mp4`

### B. HyperFrames

`output/20261109_hf_comparison/renders/rerender_dc16083aa23e4fc0b2fb056c5df4e571/final.hyperframes.mp4`

| 측정 | FFmpeg | HyperFrames |
| --- | --- | --- |
| 해상도 / fps | 1080×1920 / 30 | 1080×1920 / 30 |
| 비디오 / 오디오 | H.264 / AAC 44.1kHz | H.264 / AAC 48kHz |
| 비디오 프레임 수 | 889 | 889 |
| 컨테이너 길이 | 29.660340초 | 29.633333초 |
| 공통 렌더 단계 시간 | **17.066초** | **47.461초** |
| CLI 전체 실행 | **18.111초** | **48.528초** |
| 관측 CPU 시간 | 77.656 core-seconds | 100.109 core-seconds |
| 평균 CPU (12 논리 CPU 전체 대비) | 35.73% | 17.19% |
| 관측 최대 작업 집합 합계 | **1.087 GiB** | **2.413 GiB** |
| 관측 최대 private bytes 합계 | 1.199 GiB | 2.004 GiB |
| 파일 크기 | **5,834,397 bytes / 5.564 MiB** | **5,907,302 bytes / 5.634 MiB** |

시간은 로컬 미디어 전처리·음성 믹스·렌더·공개 파일 생성을 포함한다. CLI 전체에는 설정·썸네일·상태 저장도 포함한다.
두 렌더는 동시에 실행하지 않았다. CPU/메모리는 자손 프로세스까지 샘플링한 관측치로,
공유 메모리가 작업 집합 합계에서 중복될 수 있고 샘플 사이에 종료한 짧은 프로세스의 CPU는 누락될 수 있다.
HyperFrames의 평균 CPU 비율이 낮아도 전체 CPU 시간은 더 크고, 이번에는 렌더가 느리며 메모리도 더 사용했다.

## 완성 MP4 검증·화면 비교

- **FFmpeg 결과가 원본 완성 MP4와 바이트 단위로 동일**하다.
  SHA-256: `a088ab95572873559eac4741ca693656f11cb9e5b2448f964adb82bd457c241b`.
- HyperFrames SHA-256: `a2707075a7e44b057e48b6c87fb0b32b3a7a80571c2cf8cef633b89bbd34df43`.
- 길이 차이 약 **27ms**, 비디오 프레임 수는 동일. 원본 timeline의 29.629초 및 프레임/AAC 경계 차이다.
- 나레이션 대비 오디오 상호상관 지연 **둘 다 0ms**(8kHz로 비교). 상관계수 FFmpeg 0.99913 / HyperFrames 0.999998.
- 단어 타이밍 **49개**, 자막 큐 **21개** 재사용. 이 콘텐츠는 최대 1줄이며 어댑터의 최대 허용은 2줄.
- 실제 HyperFrames MP4 **889프레임**에서 상단250·하단400·우측150px 배제영역 전경 침범 없음(픽셀 차이 허용치40).
- 단어 내부 시점 588프레임 중 **588프레임**에서 하이라이트 색 확인. 자막 시간/글자 누락 없음.
- 실제 생성 HTML의 최종 `check --strict`: lint/runtime/layout/motion/contrast/craft/audio **오류 0·경고 0**.
- 이미지·영상·출처 표시를 1·4·9·16·22·28초 캡처로 확인했다. 한글 깨짐/잘림은 보이지 않는다.
- FFmpeg는 기존 풀 프레임/블러 배경/카라오케 표현을 그대로 유지한다.
- HyperFrames는 Noto Sans KR의 흰 문장·현재 단어 하이라이트와 큰 출처 표기가 명확하다.
  안전영역에 원본 카드를 contain으로 넣어 **카드 내부 글자와 화면 자료가 작고 여백이 많다**.
  이 단계에서 기존 카드 화면을 새 모션그래픽으로 재작성하지 않았다.
- broll의 컷 경계는 유지하며 이미지에는 작은 줌을 쓴다. 경제·공학 스타일/차트/variants는 개발하지 않았다.
- 원래 선택된 외국어 표 이미지의 낮은 장면 적합성은 그대로다. 소스 선택 품질을 이번 렌더 통합으로 해결했다고 보지 않는다.

## 테스트

최종 **377개 통과 / 70.058초**: 기존 343개 + 추가 34개. 실패·skip 없음.
기존 렌더 mock 3개는 안전한 출력 계약에 맞춰 가짜 MP4를 만들고 새 ASS 위치를 검사하도록 보완했다.
날짜에 의존하던 채널 캐시·주제 승인 테스트 2개는 신선도/고정 fixture 시각을 명시했다.
기존 채널·주제 기능의 운영 코드는 변경하지 않았고 검사 조건을 제거하지도 않았다.

실제 검증 기록은 `output/hyperframes-comparison-20261109/`:
`verification.json`, `hyperframes-strict-check.json`, 각 ffprobe·result·CPU/메모리 samples·로그,
`comparison-4s-9s-16s.png`, `comparison-safe-guides.png`, `frames/`.

## 다음 단계 (별도 요청/승인 후)

1. 카드/실영상의 안전영역 안 배치와 화면 활용도를 개선한다. 작은 원본 카드 글자를 새 타이포로 바꿀지는 별도 설계한다.
2. 긴 영상에서 메모리 피크·미디어 재인코딩/복사를 줄이고 자막 2줄 장문·복수 BGM/효과음 실제 사례를 추가 검증한다.
3. 장면 적합성·사실 검증·forced_fallback 콘텐츠 구조 제어는 남은 별도 작업이다.
4. 경제·공학 프리셋 및 `--variants 3`은 **아직 구현하지 않았다**. commit/push도 별도 승인 필요.

공식 참조: [V0.9.23 합성 규칙](https://github.com/heygen-com/hyperframes/blob/v0.9.23/skills/hyperframes/references/format.md),
[자막 규칙](https://github.com/heygen-com/hyperframes/blob/v0.9.23/skills/hyperframes/references/captions.md).
