# HANDOFF — 현재 상태

> 규칙 원본: AGENTS.md. 현재 상태 80줄 이하.
> 직전3단계 기록: docs/history/HANDOFF_2026-11-11_before_hyperframes_stage31.md.
> 최신 상세: docs/HYPERFRAMES_PERFORMANCE_2026-11-11.md. 3단계 비교는 HYPERFRAMES_STAGE3_2026-11-10.md.

## 현재 상태 (2026-11-11, Codex) — 3.1 성능 실험·최적화·실전 검증 완료, 목표 미달

- shorts-ai-codex / codex/shorts-handoff-20261106 / HEAD **f0a7d85db3fa739715543060d964da929d2290f0** (2단계 복구 커밋).
- 3단계와3.1 변경은 **미커밋·미스테이징·미푸시**. 원격/다른 브랜치는 수정하지 않음.
- 시작 시 3단계 tracked+untracked247파일을 ../backups/hyperframes-phase31-20261111-222507/에 ZIP·patch·SHA·복구 안내로 보존/검증.
- ffmpeg 기본값·기존 render.py·tts/·cards.py·PoC/lock·사용자 출력·다른 worktree 보존.

## 3.1 적용 내용 / 현재 설정

- hyperframes.py: 기존 Noto700 font 캐시를 자막 측정에도 재사용. worker1~2 검증과 runtime-settings.json 기록.
- config.yaml: HF **workers:2** (이32GB PC의 빠른 CPU 인코딩 경로), layout=adaptive/cache_media=true/low_memory=false.
- 기본 렌더러는 ffmpeg 그대로. 오래된 직접 HF 호출에서 workers가 없으면1, low_memory=true면전달1.
- 동시 렌더 작업1개 OS lock 유지. worker2는 RAM 약2.9GiB 사용; 절약하려면 workers:1로 설정.
- delivery/high·libx264 software CRF15/fast·1080×1920·30fps 유지. GPU 인코더를 기본화하지 않음.
- scripts/compare_renderers.py 선택적 per-PID CPU/WS/private/논리I/O 확장.
- 새 scripts/profile_hyperframes.py·hyperframes_rpc_profile.mjs·verify_hyperframes_performance.py: 공식debug/단계/RPC/물리디스크문맥/화질 비교.
- tests/test_hyperframes_performance.py 신규7개. 효과 작거나 불리한 이미지시퀀스 실험은 운영코드에서 제거, output에만 보존.

## 실측 / 한계

- 같은 저장 프로젝트 output/20261109_hf_comparison 사용. 새 대본·TTS·원본 소스 생성/유료 API 호출0.
- A 반복90.101/87.177초 → B68.134/65.970초, 평균 **88.639→67.052초 / 24.35% 단축**.
- A/B 품질/재료/debug 조건 동일. worker 수는1→2 실험변수. 외부 PC 부하(system CPU)가 달라 엄밀한 통제실험 한계 있음.
- 파생영상 캐시 hit, 공식 추출프레임 캐시 카운터는hit0/miss1. 완전한 추출 캐시예열로 해석하지 않음.
- 최종 일반명령 B: 전체 **68.589초** / render **66.438초** / WS **2.896GiB**, 평균 CPU 21.24%/12논리CPU.
- **60초·2.2GiB / 40초·2GiB 모두 미달**. 속도는 개선됐으나 메모리는 증가. 품질/안정성 우선으로 기록.
- A 핵심구간 캡처·전달·인코딩 약72초(인코딩병행), B 반복50~52초. A encoder drain wait합2.83초.
- 초기화·폰트가 주병목이라는 근거 없음. 순수폰트/애니메이션 CPU/물리디스크write는 분리계측 안했으며 추정치로 단정 안함.
- GetProcessIoCounters는 pipe포함 논리I/O, PDH PhysicalDisk는 시스템전체. 실제 개별프로세스 물리디스크I/O로 오해 금지.
- 브라우저GPUoff109.079초, AMF84.005초,2worker+AMF70.537초. AMF동작확인했으나 최종기본값은CPU호환경로.

## 결과 / 검증

- 최종B: **output/20261109_hf_comparison/renders/rerender_e9749c6bdb144e1ca83778bc3b1bc139/final.hyperframes.mp4**
- H.264+AAC / 29.633333초 /1080×1920/30fps/889프레임/7,104,910bytes.
- A/B index.html·shorts.html·caption-map 바이트동일. 전체배경·큰제목·비교패널·숫자/차트/강조선·줌·전환 유지.
- 889프레임 SSIM **0.998259**, PSNR **52.419dB**. 미세한 캡처/인코딩 차이는 있으며 lossless동일하다는 뜻 아님.
- 단어49개 원시시각 유지, 실제MP4 하이라이트588/588·음성지연0ms/상관0.999998124.
- strict7항목 오류0/경고0. DOM889시점 안전영역이탈0·제목/자막겹침0·pageerror0·Noto로드성공.
- 최종 전체 **403개 통과 /125.685초**, 실패·skip없음 (기존396+신규7).
- 검증/계측/과정로그: output/hyperframes-stage31-20261111/. A/B 비교이미지 comparison/.
- 이전영상·원본37파일/timeline/TTS·PoC/의존성/백업 보호. Node/Chrome/Python설치·플러그인 변경 없음.

## 다음 우선순위 / 종료

- 여기서중지. 메모리증가 없는 공식 캡처/전달 개선·보다 통제된cold/warm반복이 다음 과제.
- 로컬3단계+3.1 저장은 아직 승인안됨. Commit/Push 금지상태 유지.
- 공개자료 적합성·벤치마킹 사실검증·forced_fallback·실제장문2줄/BGM/SFX는 여전히별도 과제.
- 경제·공학 프리셋·--variants3·카드뉴스/인스타툰/캐릭터 복원은 구현하지 않음.
