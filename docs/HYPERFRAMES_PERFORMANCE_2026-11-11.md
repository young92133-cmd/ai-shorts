# HyperFrames 3.1 — 렌더링 병목 분석·성능 검증 (2026-11-11)

## 결과와 적용 결정

동일한 저장 쇼츠로 반복 측정했고, 애니메이션/해상도/인코더 화질을 낮추지 않았다.
A 평균 **88.639초**, B 평균 **67.052초**로 전체 시간이 **24.35% 단축**됐다.
진단 옵션을 뺀 실제 운영 명령의 최종 B는 **68.589초 / 2.896GiB**였다.
**1차 60초·2.2GiB 및 2차 40초·2GiB 목표는 모두 미달**이다. 빠른 경로의 메모리는 오히려 늘었다.

- 적용: HyperFrames 캡처 worker를 1~2로 제한하면서 이 32GB PC의 config를 **workers: 2**로 설정.
  오래된 직접 호출에서 설정이 없으면 기존 1을 유지한다. `low_memory: true`면 전달 worker도 1이다.
  기존 OS lock은 유지해 동시 렌더 작업은 여전히 1개다. RAM을 줄이려면 `workers: 1`을 쓴다.
- 적용: 자막 크기 계산이 이미 존재하는 700-weight Noto font 캐시를 재사용. HTML/자막 바이트가 A/B 동일함을 확인했다.
- 유지: 기본 렌더러 ffmpeg, HyperFrames의 H.264 libx264/software **delivery(high), CRF15, fast**, 30fps, 1080×1920.
- 미채택: 브라우저 GPU 끄기, GPU 인코더 기본화, 이미지 시퀀스 변환. 느리거나 전체 이득이 작거나 품질/호환성 조건이 달랐다.
  이미지 시퀀스 실험 코드는 운영 소스에서 제거하고 output/rejected-experiments에만 보존했다.
- CPU 인코더를 유지한 worker 2는 공식 CLI가 병렬 screenshot 경로를 선택한다. 기존 worker 1의 drawElement 경로와 캡처 구현은 다르다.
  지원되는 CLI 설정만 운영에 적용했고, HyperFrames/Node 패키지 파일을 수정하지 않았다.

## 현재 작업 보호

- branch `codex/shorts-handoff-20261106`, HEAD **f0a7d85db3fa739715543060d964da929d2290f0** 유지.
- 작업 시작 시 3단계 미커밋·미추적 전체 소스 247파일을 `../backups/hyperframes-phase31-20261111-222507/`에 보존.
  `source-tree.zip` 39,405,095 bytes, `working.patch`, 파일별 SHA `manifest.json`, 새 폴더 복구 안내 `RESTORE.txt` 포함.
  ZIP testzip와 모든 파일 SHA를 검증했다. Git metadata/도구/캐시/인증/생성 영상은 백업 소스 트리에서 제외하고 기존 위치에 보존했다.
- 기존 3단계 MP4와 다른 worktree/백업은 삭제·덮어쓰기하지 않았다. 새 결과는 프로젝트의 고유 renders/ 경로다.
- 이번 작업에서 Commit/Push/이력 변경은 없다. FFmpeg render.py, TTS 모듈(tts/), cards.py, PoC와 버전 lock을 유지했다.
- 대본·TTS·공개 소스 재생성/다운로드, 유료 API 호출, 플러그인·의존성 설치 없음.

## 계측 방법과 조건

`scripts/profile_hyperframes.py`는 실제 factory rerender CLI를 호출한다. 원본 timeline을 수정하지 않고 실험 자식에서
공식 --debug/--workers/--gpu/--no-browser-gpu만 제어한다. 최종 운영 검증은 일반 `scripts/compare_renderers.py`로 별도 실행했다.

- 공식 --debug의 perf-summary.json과 Render:trace로 compile/probe/extract/audio/capture/setup/encode/assemble 측정.
- PID+생성 시각으로 실제 자식만 추적. 프로세스별 CPU core-seconds, working set/private, GetProcessIoCounters를 약 0.2초마다 수집.
- 시스템 CPU와 PhysicalDisk(_Total) read/write bytes/sec도 PDH로 기록했다. 사용자 다른 프로세스를 중단하거나 설정을 바꾸지 않았다.
- I/O transfer count에는 파일·pipe·기타가 포함된다. 이를 프로세스별 **물리 디스크 I/O**라고 단정하지 않는다.
  물리 디스크 카운터는 시스템 전체이고 렌더에 독점 귀속할 수 없다. ETW 등의 프로세스별 실제 디스크 추적은 수행하지 않았다.
- WS는 공유 페이지가 중복될 수 있는 프로세스 합계다. 샘플 사이 종료한 프로세스/피크 CPU·I/O는 누락될 수 있다.
- 선택적인 Puppeteer public Page RPC 계측은 함수 본문·화면 문구·URL·인증·프레임 payload를 저장하지 않는다.
  paint kick→프레임 callback 지연과 준비 RPC를 측정했으며, JPEG 압축 CPU와 base64/IPC 각각을 분리한 값은 아니다.
- 같은 프로젝트/대본/음성/원본/폰트/라이브러리/delivery 품질을 유지했다. worker 수는 의도한 실험 변수다.
  A/B 입력 index.html·shorts.html·caption-map.json 바이트가 동일하다. A 반복 MP4도 기존 3단계 MP4와 SHA 일치: {'A-profile': True, 'A-repeat': True}.
- 파생 MP4 캐시는 예열해 재사용했지만 공식 추출 프레임 캐시는 실제 카운터상 매회 hit0/miss1이었다. 완전한 warm-cache 실험으로 표현하지 않는다.
- 다른 PC 부하는 통제하지 못했다. 아래 system CPU 수치가 다르므로 단축률을 정밀한 인과 효과로 단정하지 않는다.
  같은 debug 조건에서 A/B 각각 2회 반복했고 실패한 실험도 남겼다. 과거 83.253초 기록은 당일 대조군 평균과 구분한다.

## 반복 A/B와 실제 운영 결과

| 실행 | CLI 전체 초 | 렌더 초 | 캡처 구간 초 | 집계 capture FPS | 피크 WS GiB | 렌더 CPU/12논리CPU | 시스템 CPU 평균 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A-profile | 90.101 | 87.339 | 72.498 | 12.26 | 2.033 | 18.33% | 35.67% |
| A-repeat | 87.177 | 84.824 | 71.802 | 12.38 | 2.108 | 18.48% | 37.59% |
| B-profile | 68.134 | 65.800 | 52.221 | 17.02 | 2.890 | 21.82% | 57.71% |
| B-repeat | 65.970 | 63.532 | 50.168 | 17.72 | 2.876 | 21.66% | 60.55% |

- 기존 3단계 과거 기록: 전체 83.253 / render81.295초 / 2.242GiB. 같은 날 통제된 A 평균은 88.639초다.
- 최종 B 일반 명령: 전체 **68.589초**, render **66.438초**, tree WS **2.896GiB**, private **2.599GiB**.
- 최종 B CPU 합 174.828 core-seconds, 평균 1 core 기준 254.89%, 12논리CPU 기준 21.24%.
- 전체 시간/889 기준 평균 77.153ms/출력프레임. 이 값에는 초기화가 포함되므로 개별 캡처 지연과 구분한다.
- A 반복 총 CPU 평균 195.750 vs B 174.945 core-seconds.
  병렬화로 평균 CPU 사용률과 메모리는 늘었고 총 CPU 시간은 줄었다. 메모리 2.2GiB 목표를 만족하는 개선은 아니다.

## 병목별 실제 시간과 측정 한계

A-repeat을 대표 기준으로 사용한다. 아래 값에는 병행·포함 관계가 있어 전부 더하면 전체 시간과 맞지 않는다.
특히 A의 capture와 encode는 병행 구간이며 두 시간을 더하지 않는다.

| 요청 항목 | 측정 결과 | 범위/한계 |
| --- | --- | --- |
| HyperFrames CLI 초기화 | render CLI 83.156s - 엔진 77.409s = 5.747s | CLI 시작·사전 검사·종료·debug 보존 등의 합. 순수 초기화만 분리한 값 아님 |
| Chrome Headless 시작 | capture setup 2.191s | 브라우저 시작/연결/캡처 준비의 합. 순수 OS 시작 완료 시간을 분리하지 못함 |
| HTML/CSS/JavaScript 로딩 | A 로그 page.goto 1ms→641ms, 약0.640s | HTML 파싱·블로킹 JS·리소스를 함께 포함. JS만의 CPU 시간 아님 |
| 한글 폰트/이미지 | A init 로그 media+fonts ready 1547ms 시점, 직전 단계1532ms | 준비 대기15ms가 전체 폰트 로딩 시간이라는 뜻이 아님. 개별 font/image decode 시간 미분리 |
| 애니메이션 계산 | 공식 seek+이미지 준비 평균 8ms/호출, before-capture 7ms | 순수 GSAP 계산 외에 RPC/준비 포함. Node/PIL export 0.479s→B 0.276s |
| 프레임 캡처 | A 71.802s / 889 = 80.767ms, 12.38FPS | 캡처·전달·대기 포함 전체 구간. B 50.168s, 17.72FPS |
| 전달/인코딩 | A encode 71.772s 병행, drain wait 합 2.834s | Page worker callback 지연은 JPEG+base64/IPC 결합. FFmpeg만의 속도를 병목 전체로 단정할 수 없음 |
| 오디오 합성 | A 2.195s / B 2.528s | setup과 병행. 기존 원본 음성 재사용 |
| 최종 MP4 저장 | A assemble 1.021s / B 0.934s | mux/faststart 등 포함. 순수 디스크 write 시간은 미분리 |

B의 encodeMs 0.192s는 병렬 캡처 이후 마무리 단계의 값이다. 실제 H.264 인코딩 전체가 그 시간만 걸렸다는 뜻이 아니다.
프로세스 CPU 표에 작업 중 인코더 비용도 남아 있다. 초기화·폰트만의 문제라고 판단할 근거는 없고,
확인된 주된 병목은 **브라우저의 프레임 캡처·JPEG 결과 전달이 이어지는 경로**다.
실험 중 단일 짧은 video의 before-capture hook 때문에 전체 배치 경로가 비활성화되는 구조도 확인했으나,
이를 우회한 이미지 시퀀스는 추가 비용 대비 전체 이득이 작아 채택하지 않았다.

### A 기준: 관측 CPU 상위 6개 프로세스

| PID / 실행 파일 | CPU core-seconds | 개별 피크 WS MiB | 논리 read MiB | 논리 write MiB |
| --- | ---: | ---: | ---: | ---: |
| 4172 / ffmpeg.exe | 68.781 | 508.6 | 291.6 | 6.0 |
| 23336 / chrome-headless-shell.exe | 59.125 | 432.3 | 12.1 | 117.4 |
| 2356 / node.exe | 21.234 | 342.8 | 515.4 | 333.7 |
| 39544 / chrome-headless-shell.exe | 9.641 | 94.0 | 136.6 | 402.9 |
| 13980 / chrome-headless-shell.exe | 9.328 | 533.0 | 1.1 | 1.1 |
| 38060 / ffmpeg.exe | 2.031 | 101.2 | 0.9 | 6.2 |

### B 최적화: 관측 CPU 상위 6개 프로세스

| PID / 실행 파일 | CPU core-seconds | 개별 피크 WS MiB | 논리 read MiB | 논리 write MiB |
| --- | ---: | ---: | ---: | ---: |
| 14824 / ffmpeg.exe | 55.312 | 515.5 | 211.2 | 6.2 |
| 32780 / node.exe | 26.594 | 270.8 | 616.6 | 457.0 |
| 10236 / chrome-headless-shell.exe | 14.797 | 77.5 | 12.0 | 143.8 |
| 13896 / chrome-headless-shell.exe | 14.766 | 77.6 | 12.1 | 144.6 |
| 4584 / chrome-headless-shell.exe | 10.469 | 816.6 | 4.7 | 1.2 |
| 36512 / chrome-headless-shell.exe | 10.328 | 824.9 | 4.6 | 1.2 |

각 프로세스의 전체 표는 해당 실행 processes.json, 시계열은 samples.json에 있다.
개별 peak를 더한 값은 같은 시점의 tree peak와 같지 않다. 물리 디스크의 렌더 단독 병목 여부는 이 자료만으로 확정하지 않는다.

## GPU·기타 실험

| 실험 | 전체 초 | WS GiB | 결정 |
| --- | ---: | ---: | --- |
| browser-software | 109.079 | 1.592 | 느려서 미채택. 메모리 감소만 확인 |
| workers2-rpc | 67.934 | 2.885 | 병렬 CPU 경로 검토 근거 |
| hardware-encoder | 84.005 | 1.686 | AMF 사용 확인, 기본값 미채택 |
| workers2-hardware | 70.537 | 2.475 | CPU 경로보다 시간 이득 없어 미채택 |
| sequence-experiment | 93.307 | 2.275 | DOM/로딩 비용이 늘어 미채택 |
| sequence-single | 85.001 | 2.230 | 전체 이득 작아 미채택 |
| sequence-callback | 79.192 | 2.233 | 전체 이득 작고 경로 복잡해져 미채택 |

브라우저 하드웨어 GPU는 기존 AMD D3D11 경로에서 사용됐다. 별도 --gpu 인코딩 MP4에서
`Lavc63.1.101 h264_amf` 태그로 실제 하드웨어 인코더 사용도 확인했다.
AMF의 constant QP15는 software CRF15와 같은 품질 척도가 아니며 파일도 약9.4MB로 달랐다.
호환성과 기존 인코더 품질을 지키기 위해 최종 기본값은 CPU libx264다. GPU 실험을 최종 개선 폭에 섞지 않았다.
진단 RPC 모듈의 초기 Windows file-URL 오류는 수정했으며 실패 로그를 보존했다.

## 영상 품질·회귀 테스트

- 최종 **403개 전체 테스트 통과 / 125.685초**, 실패·skip 없음. 기존396 + 신규7.
- 신규: 기본 worker1/최대2/잘못된 값/low-memory1, 글꼴 재로딩 방지·700-weight 크기 일치, 프로세스 CPU/I/O 중복 집계·PID 재사용.
- FFmpeg 기본값과 기존 렌더러/타임라인/폴백·오류/출력 보존 테스트를 유지했다. FFmpeg render.py/TTS 모듈(tts/)/cards.py는 수정하지 않았다.
- A/B index.html·shorts.html·caption-map.json **바이트 동일**. 자막/제목/전체 배경/비교 패널/숫자·막대·강조선·줌·전환을 제거하지 않았다.
- 1080×1920·30fps·H.264+AAC·29.633333초·889프레임, 최종 **7,104,910 bytes**.
- 실제 889프레임 비교 SSIM **0.998259** (최저 프레임 0.995823), PSNR **52.419dB**.
  미세한 캡처/인코더 양자화 차이가 있으나 낮은 품질 설정을 쓰지 않았다. 원본 프레임과 완전한 lossless 동일 출력이라는 뜻은 아니다.
- 단어49개 시각 그대로, MP4 하이라이트 588/588 프레임 일치, 음성 지연0ms·상관0.999998124.
- 제목·단계 성장 실제 픽셀 변화 확인, 공식 strict7항목 오류0·경고0.
- DOM889시점 안전영역 이탈0·제목/자막 겹침0·page error0, Noto 정상 로드.
- 같은1/4/9/16/22/28초를 캡처해 A/B contact sheet와 안전선 버전을 확인했다. 한글 깨짐·잘림·장면 누락은 관찰되지 않았다.
- 원본37파일/timeline/TTS 바이트, 저장된 A/이전 output, PoC/lock/다른 worktree를 보존했다. 새 AI·TTS 호출0.

## 실제 결과와 재현

- 최종 B: `output/20261109_hf_comparison/renders/rerender_e9749c6bdb144e1ca83778bc3b1bc139/final.hyperframes.mp4`
- SHA-256: `a5bdfc00dff7c2087648117e22c698b56b14fbd16d207a5808d9446d2750c0c9`
- [4·9·22초 A/B 비교](../output/hyperframes-stage31-20261111/comparison/comparison-4s-9s-22s.png)
- [1·16·28초 A/B 비교](../output/hyperframes-stage31-20261111/comparison/comparison-1s-16s-28s.png)
- `output/hyperframes-stage31-20261111/measurement-summary.json`: 전체 요약.
- A-profile/A-repeat/B-profile/B-repeat: perfs/stages/adapter-stages/processes/samples/result.
- B-delivery: 실제 운영 명령/ffprobe/strict/DOM/자막·음성 검증. comparison: SSIM/PSNR/프레임 비교.

```powershell
# 보고서 위치는 새 이름을 사용한다. 기존 보고서/영상은 덮어쓰지 않는다.
../shorts-ai/.venv/Scripts/python.exe -B scripts/profile_hyperframes.py --report output/my-profile --debug --workers 2
./scripts/factory.ps1 rerender PROJECT_ID --renderer hyperframes
```

## 변경 파일과 남은 과제

- app/pipeline/hyperframes.py: 글꼴 캐시 재사용, worker 검증/제한·설정 기록.
- config.yaml: HyperFrames workers2. ffmpeg 기본값 유지, low_memory면1.
- scripts/compare_renderers.py: 선택적 프로세스별 I/O/이름/생성시각 시계열.
- scripts/profile_hyperframes.py, hyperframes_rpc_profile.mjs, verify_hyperframes_performance.py: 진단·프로세스/물리 디스크 문맥·화질 비교.
- tests/test_hyperframes_performance.py: 성능 관련7개. README/HANDOFF/본 보고서와 이력 보완.

다음 우선순위는 **메모리 증가 없이 캡처·전달을 줄이는 공식 엔진 개선**이다.
현재0.9.23의 JPEG/base64/IPC와 단일 video 주입 경로를 패키지 수정 없이 크게 줄이기에는 한계가 있었다.
자체 엔진 포크·검증 우회·프레임 생략·해상도/CRF 저하는 하지 않았다. 버전 변경은 별도 호환성 실험이 필요하다.
콜드/웜 캐시와 외부 PC 부하를 더 엄밀히 통제한 반복 계측, 실제 물리 디스크/codec CPU 세부 추적도 후속 과제다.
경제·공학 프리셋·--variants 3·카드뉴스/인스타툰 복원은 하지 않았다. 이 지점에서 멈추고 Commit/Push는 별도 승인 후 진행한다.
