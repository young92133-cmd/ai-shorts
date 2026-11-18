# HyperFrames 3단계 — 실제 화면 품질·성능 비교 (2026-11-10)

> 이 문서는 3단계 기준 기록이다. 이후 3.1단계 병목·반복 계측·최신 설정/테스트 결과는
> [2026-11-11 성능 보고서](HYPERFRAMES_PERFORMANCE_2026-11-11.md)를 따른다. 기존 영상과 이 검증 기록은 보존했다.

## 완료 범위와 GitHub 복구 지점

작업 A에서 검증된 2단계를 먼저 저장한 뒤 3단계를 시작했다.
- 저장소: https://github.com/young92133-cmd/ai-shorts
- 브랜치: `codex/shorts-handoff-20261106`
- 커밋: `f0a7d85db3fa739715543060d964da929d2290f0`
- 메시지: `feat: integrate optional HyperFrames renderer with validated PoC`
- 일반 Push 성공. 작업 종료 시에도 로컬 HEAD/원격 Codex SHA 일치 확인.
- 원격 main `8cbc5b5d4c30461c255b0de72535cb81c1651e63`, feature/shorts-only `7a5d7daac687d23c84934183f1a9dac611cd4dc1` 보존.
- A 직전 전체 377개 통과 / 125.829초. 41개 파일 약 12.9MB만 명시적으로 선별 저장.
- 어댑터/선택 기능/테스트, PoC 소스·설정·폰트 라이선스, package/lock, 설치 안내, 인수인계/검증 문서를 저장했다.
- Node/npm 실행 파일, Chrome, node_modules, .tools/캐시, output MP4/산출물, 사용자 자료·가상환경·인증 파일은 제외했다.
- **3단계 변경은 Commit/Push하지 않았다.** HEAD와 원격 복구 지점은 여전히 위 2단계 커밋이다.

3단계는 같은 저장 프로젝트의 C 최종 MP4까지 제작·검증했다. 화면 품질 개선은 확인했지만,
**전체 40초 / 관측 메모리 2GiB 목표는 달성하지 못했다.** 이를 성능 성공으로 보고하지 않는다.

## 변경 파일과 구조

| 파일 | 역할 |
| --- | --- |
| app/pipeline/hyperframes_layout.py (신규) | 기존 장면의 선택적 메타데이터 검증, native 텍스트·숫자/비교 문구, 안전영역, 보수적 이미지 배치 |
| app/pipeline/hyperframes.py | adaptive/legacy 선택, 레이어 연결, 정적 배경 1회 생성, 미디어 파생 캐시, 단일 음성 직접 연결 |
| config.yaml | ffmpeg 기본값 유지, adaptive·safe_area·cache_media·low_memory 설정 |
| renderers/hyperframes/scene.html | adaptive CSS 삽입 지점 |
| scripts/compare_renderers.py | 고유 보고서 위치, PID+프로세스 생성 시각으로 계측 계보 검증 |
| scripts/verify_hyperframes_layout.mjs (신규) | 전용 Chrome으로 889개 시점의 실제 글자 범위·겹침·폰트 검사 |
| scripts/verify_hyperframes_stage3.py (신규) | 저장 A/B 보존·ffprobe·실제 픽셀 애니메이션/자막·음성 비교·contact sheet |
| tests/test_hyperframes_layout.py (신규) | 기존 V1, native 메타데이터, 한국어·경로·안전영역·크롭·오디오/캐시 16개 |
| tests/test_render_measurement.py (신규) | Windows 재사용 PID의 무관한 프로세스 제외 3개 |
| renderers/hyperframes/README.md | 새 설정·동작·검증 명령과 계측 한계 |
| HANDOFF.md / 통합 보고서 / 이 보고서 / docs/history/ | 현재 상태와 2단계 기록 보존 |

기존 `app/pipeline/render.py`, `tts/`, `cards.py`는 수정하지 않았다.
`timeline.json`은 새 입력 구조로 대체하거나 저장·수정하지 않는다. `layout-map.json` 등은 렌더 폴더의 파생 진단 자료다.
기존 렌더러 선택·폴백·동시 렌더 1개·고유 출력/오류 로그 계약을 유지한다.

## 실제 화면 변화

- 카드 5장을 작은 PNG로 넣는 대신, 시간·파일 정체성·대본/강조문구가 일치하고 기존 권리 대장의 generated인 경우에만 HTML 문구로 분리했다.
  힌트가 없거나 오래됐으면 원래 raster를 유지한다. 임의의 이미지에서 글자를 추측하거나 OCR하지 않는다.
- 배경은 1080×1920 전체 사용. 주요 글자만 기본 x=72~930, y=250~1520 안에 둔다.
  `safe_area`로 관리하고 불가능한 좁은 영역은 거부한다.
- native 제목 최대 104px, 미디어 제목 최대 84px. 비교 문구 2개를 큰 패널에 순차 등장시킨다.
  기존 key_number는 원문 그대로 보존한다. 강조선·화살표, 완만한 줌, 저장 blueprint의 fade를 재사용한다.
- 저장 시각 설명에 있던 `3단`만 구조 그림으로 표현했다. 높이는 요금 비율이 아니라는 28px 설명을 표시한다.
  새로운 통계·금액·비율을 생성하지 않았다. 이 샘플의 key_number는 비어 있어 가짜 수치 카운트업을 넣지 않았다.
- 가로 영상은 원래 비율/디코딩 해상도를 유지한다. 전체가 보이는 큰 전경과 첫 프레임을 흐린 정적 배경으로 사용한다.
  샘플 854×480의 전경 폭은 1080px 수준이다. 직접 stage 자식인 timed video로 원래 3초 offset을 유지한다.
- 낮은 해상도/가로 사진은 전체 피사체를 보존한다. 기하학적으로 25% 넘는 크롭은 피하며, 작은 사진 전경은 기본 2.5배 + 최대 1.8% 움직임으로 제한한다.
  충분한 해상도의 세로 사진만 제한된 중심 크롭을 쓴다. 의미 기반 피사체 탐지는 아직 없다.
- 권리·출처가 일치하는 원래 parent를 통해 합성 사진의 배경과 제목을 분리했다. 새 공개 자료 다운로드는 없다.
- Noto Sans KR·기존 49개 단어 시각을 그대로 사용. 약 14자·단어/문장 경계·최대 2줄, 자막 등장과 단어별 하이라이트를 유지한다.
  이 실제 샘플은 21큐 모두 1줄이다. 장문 2줄은 자동 테스트로 별도 검증했다.
- 정적 native 배경은 기존 Shorts `cards._background`를 재사용해 1회 렌더한다. 본문/제목/자막/도형 모션은 별도 HTML 레이어다.

## A/B/C 실측

A/B는 저장된 원래 MP4와 계측 기록을 재사용했고 덮어쓰거나 재제작하지 않았다.
모두 H.264 + AAC, 1080×1920, 30fps, 889프레임이다.

| 결과 | 길이(초) | 렌더 단계(초) | CLI 전체(초) | 피크 tree WS(GiB) | 평균 CPU/12논리CPU | 파일 bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A 기존 FFmpeg | 29.660340 | 17.066 | 18.111 | 1.087 | 35.73% | 5,834,397 |
| B HyperFrames 2 | 29.633333 | 47.461 | 48.528 | 2.413 | 17.19% | 5,907,302 |
| C HyperFrames 3 최종 | 29.633333 | 81.295 | 83.253 | 2.242 | 19.01% | 7,115,425 |

C의 관측 CPU 합은 189.891 core-seconds, 1 core 기준 평균 228.09%,
피크 private 합계 1.900GiB, 361회 샘플이다.
실제 renderer=hyperframes, fallback=none, 오류 없이 완료했다.
C SHA-256: `0a26b476bd887607e285149ef25437d1a0fba23b926dbfb4888f36a8b8464f75`.

- 렌더 버전·해상도·delivery 품질·worker 1·하드웨어 GPU/drawElement 경로는 B와 동일하게 유지했다.
  Python/FFmpeg 9.0.1·Node 24.22.1·npm 12.2.2·HyperFrames 0.9.23·Chrome 152.0.7977.30도 유지했다.
- C는 같은 재료의 **예열된 로컬 파생/추출 캐시**를 사용한다(미디어 준비 기록 cache_hit=true).
  A/B는 지난 11월 9일 기록이다. 측정 시점의 PC 부하·캐시 조건을 통제한 동시 비교가 아니다.
- 계측 v2는 Windows PID뿐 아니라 생성 시각으로 부모/자식 정체성을 검증한다.
  구 PID-only 방식이 재사용 PID에 연결된 무관한 프로세스를 포함해 100% 초과 machine CPU를 보고하는 오류가 발견돼 수정했다.
  초기 C 시도들의 CPU/RSS는 최종 평가에서 제외했다. A/B의 과거 CPU/RSS도 구 방식이므로 엄밀한 직접 비교에는 한계가 있다.
- WS는 프로세스 트리 합계로 공유 페이지가 중복될 수 있다. 0.2초 sleep 기반 샘플이므로 그 사이 끝난 짧은 프로세스 CPU/피크는 누락될 수 있다.
- 저메모리 screenshot 강제 후보는 CLI 전체 124.093초로 더 느렸다. 메모리 이득도 신뢰성 있게 확인하지 못해 기본값으로 채택하지 않았다.
  큰 세로 영상으로 미리 재인코딩하던 후보는 버리고 원본 해상도로 디코딩한다. 최종은 low_memory=false, cache_media=true.
- 최종 CLI trace: compile 약 1.3초, extract 0.9초, audio 2.5초, setup 2.5초,
  **capture 67.8초 / encode 67.7초(병행)**, assemble 0.9초. 남은 주된 병목은 프레임 캡처/인코딩이다.
- B 대비 글자와 배경이 커졌으나 전체 실행은 느려졌다. 목표 40초·2GiB는 미달이며 성능 개선 완료로 간주하지 않는다.

## 실제 검증 결과

- 최종 전체 **396개 통과 / 113.332초**, 실패·skip 없음(기존 377 + 신규 19).
- FFmpeg 기본값·기존 필터/ASS 계약·렌더 선택·V1 호환·명시 폴백/취소/오류 격리 회귀 검증 유지.
- 원본 프로젝트 37파일 SHA, timeline 바이트, TTS 파일 바이트 보존. 새 AI·TTS 호출 0.
- A SHA는 기존 원본 final.mp4와 일치하고, A/B 각각 이전 검증 SHA와 일치한다.
- C 실제 MP4 889프레임 디코딩. 단어 내부 하이라이트 **588/588 프레임** 일치, 누락 0.
- 음성 8kHz 상호상관: C 지연 **0ms**, 상관 0.999998124. A/B도 지연 0ms.
- 실제 영상 제목 밝은 픽셀 0→21,936, 세 단계 성장 픽셀 2→28,576→129,075로 애니메이션을 확인했다.
- 공식 check --strict: lint/runtime/layout/motion/contrast/craft/audio **7개 항목 오류0·경고0**.
- final render.log WARN 0. check 로그의 큰 글꼴 비인라인 안내 2줄은 로컬 파일로 제공되는 Noto 9.9MB 관련이다.
  폰트 로드 성공·외부 CDN 요청 없음 확인. Node/HyperFrames 업데이트 알림은 설치 변경이 아니다.
- 최종 별도 브라우저 DOM 감사: 889개 시점의 텍스트 범위 이탈0, 제목/자막 겹침0, 폰트 로드 성공, page error0.
  배경은 안전영역 밖을 채워도 정상이다. 독립 child-template DOM 감사이며, 실제 producer strict 검사/MP4 픽셀 검사/육안 캡처와 함께 판단했다.
  사진 속 원래 외국어 글자를 OCR로 검증했다는 뜻은 아니다.
- 실제 1/4/9/16/22/28초 캡처와 안전선 contact sheet를 확인했다. 새 한글 제목/자막의 깨짐·잘림은 관찰되지 않았다.
- 원본 PoC/lock 14파일과 다른 worktree 5개의 기존 변경 지문도 보존 확인했다. 백업 삭제 없음.

## 결과 파일

- A: `output/20261109_hf_comparison/renders/rerender_ad41ade184164e2992febbe77b6f6ccd/final.ffmpeg.mp4`
- B: `output/20261109_hf_comparison/renders/rerender_dc16083aa23e4fc0b2fb056c5df4e571/final.hyperframes.mp4`
- **C: `output/20261109_hf_comparison/renders/rerender_63d59d74eeec40a3b99a80ad0fbd69c0/final.hyperframes.mp4`**
- 검증/계측/ffprobe/로그/샘플: `output/hyperframes-stage3-accepted-20261110/`
- 비교: [4·9·22초](../output/hyperframes-stage3-accepted-20261110/comparison-4s-9s-22s.png),
  [1·16·28초](../output/hyperframes-stage3-accepted-20261110/comparison-1s-16s-28s.png), 각 `-safe.png` 안전선 버전.
- 이전 실패/실험 로그·영상은 `output/hyperframes-stage3-20261110`, `-fast-20261110`, `-final-20261110`, `-verified-20261110`에 보존했다.
  평가용 C는 위 accepted 결과 하나다. 미커밋 개인 산출물이므로 GitHub에는 올라가지 않았다.

## 남은 문제와 다음 우선순위

1. 전체 화면 화질을 유지하면서 캡처/인코딩 67.8초 병목과 메모리 피크를 개선한다. 동일 조건에서 캐시 cold/warm을 나누고 반복 계측해야 한다.
2. 작은 220×277 외국어 표 사진은 원본 적합성/해상도 한계가 남아 있다. 렌더 배치 변경이 자료 선정/사실 검증을 해결한 것은 아니다.
3. 이 테스트는 저장 내용 보존 검증이다. 전기요금 수치나 벤치마킹 근거를 새로 사실 확인하지 않았고 콘텐츠 forced_fallback도 바꾸지 않았다.
4. 실제 장문 2줄, 복수 BGM/효과음/덕킹, 긴 영상·다양한 원본 비율 사례를 늘린다. 현재 선택 데이터가 없는 BGM/SFX는 오류 없이 처리하며 단위 테스트는 유지한다.
5. 경제·공학 프리셋·--variants 3은 구현하지 않았다. 3단계 GitHub 저장도 승인 전에는 하지 않는다.

기존 FFmpeg 엔진·TTS·cards.py, 사용자 output/백업, 다른 브랜치/worktree는 유지한다.
카드뉴스·인스타툰·캐릭터 기능 복원, 플러그인 설치, 유료 API 호출은 없었다.
