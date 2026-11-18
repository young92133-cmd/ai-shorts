# HANDOFF — 현재 상태

> 규칙 원본: AGENTS.md. 현재 상태 80줄 이하.
> 직전 2단계 기록: docs/history/HANDOFF_2026-11-10_hyperframes_stage2_saved.md.
> 최신 상세: docs/HYPERFRAMES_STAGE3_2026-11-10.md (2단계 기준은 HYPERFRAMES_INTEGRATION_2026-11-09.md).

## 현재 상태 (2026-11-10, Codex) — 3단계 품질 개선·C 실제 검증 완료, 성능 목표 미달

- 폴더 shorts-ai-codex / 브랜치 codex/shorts-handoff-20261106.
- 승인된 작업 A: 2단계 Commit·일반 Push 완료. SHA **f0a7d85db3fa739715543060d964da929d2290f0**.
- 로컬 HEAD와 origin Codex SHA 일치 최종 확인. main 8cbc5b5 / feature/shorts-only 7a5d7da 보존.
- **3단계 변경은 미커밋·미스테이징·미푸시**. 이번 작업 범위 종료, 후속 개발/저장은 별도 요청을 따른다.
- ffmpeg 기본값·기존 render.py/tts.py/cards.py 유지. 쇼츠 제작/승인/resume/순차·채널 벤치마킹 기능 보존.
- 경제·공학 프리셋과 --variants 3은 미구현. 카드뉴스·인스타툰·캐릭터 기능 복원 없음.

## 3단계 변경 구조

- hyperframes_layout.py 신규: 일치하는 기존 blueprint/script 힌트와 권리 대장으로 native 텍스트 카드·비교 문구·구간 구조 표시.
- hyperframes.py: adaptive/legacy, 전체 배경과 텍스트 안전영역 분리, 로컬 파생 영상 캐시, 음성 단독 직접 재사용.
- config.yaml: renderer=ffmpeg 유지. HF layout=adaptive, safe_area={left:72,top:250,right:150,bottom:400}, cache_media=true, low_memory=false.
- scene.html·HF README 보완. 정적 배경은 기존 cards._background로 1회 생성하고 글자/모션은 HTML 레이어로 분리.
- 원본 timeline.json은 수정 안 함. layout-map/HTML 등은 렌더별 파생 진단 자료.
- scripts/compare_renderers.py: 새 보고서 경로·Windows PID 생성 시각 검증 계측. 새 DOM/MP4 검증 스크립트 2개.
- tests/test_hyperframes_layout.py 16개 + test_render_measurement.py 3개 추가.
- 텍스트 이스케이프·로컬 경로/권리 검사, 고유 출력·오류 로그·명시 폴백·동시 render 1개/worker 1개 유지.

## 실제 A/B/C 결과 (같은 난방비 쇼츠 / AI·TTS 재생성 0)

- 프로젝트 output/20261109_hf_comparison. 원본 ../shorts-ai-shorts/output/20261105_231559_d127 보존.
- A/B는 이전 완성 결과 재사용. 둘의 MP4 SHA도 이전 기록과 동일, A는 원본 FFmpeg와 바이트 동일.
- **C: output/20261109_hf_comparison/renders/rerender_63d59d74eeec40a3b99a80ad0fbd69c0/final.hyperframes.mp4**
- 3개 모두 H.264+AAC / 1080×1920 / 30fps / 889프레임. C 29.633333초, 7,115,425 bytes.
- 전체/렌더 시간: A 18.111/17.066초, B 48.528/47.461초, C 83.253/81.295초.
- tree working-set 피크: A 1.087 / B 2.413 / C 2.242GiB. C 평균 machine CPU 19.01% / 12논리CPU.
- **40초·2GiB 목표 미달**. capture/encode 약 67.8초가 남은 병목. 속도 개선 성공으로 취급하지 않는다.
- A/B는 구 PID-only 계측, C는 생성 시각 보정 v2·예열 캐시. PC 부하/시점도 달라 엄밀한 성능 비교 한계 있음.
- 초기 C 실험의 CPU/RSS는 PID 재사용 오염 가능성이 있어 평가에서 제외; 실패/실험 산출물은 보존.
- native 카드 5장, 제목 최대104px/미디어84px, 강조선/화살표/3구간 성장·순차 비교·fade·완만한 줌.
- 새 통계 생성 없음. 구간 그림 높이는 비율이 아님을 표시. 작은 외국어 표 자료 적합성·해상도 한계는 여전함.

## 테스트·품질·보호

- 최종 전체 **396개 통과 / 113.332초**, 실패·skip 없음(기존377 + 신규19).
- 단어 49개·자막21큐 원시 시각 재사용, 최대2줄 지원(이 실제 샘플은1줄), MP4 하이라이트 588/588 일치.
- C 음성 지연0ms / 상관0.999998124. 원본37파일·timeline/TTS 바이트·기존 AI 호출 기록 보존.
- 공식 strict 7항목 오류0·경고0. render.log WARN0. 큰 Noto 로컬 비인라인 안내2줄은 정상 파일 제공/로드 확인.
- 별도 브라우저889시점 안전영역 이탈0·제목/자막 겹침0·page error0. 실제 1/4/9/16/22/28초 캡처 확인.
- 결과·검증·비교 이미지: output/hyperframes-stage3-accepted-20261110/.
- 다른 worktree5개 기존 변경 지문·PoC/lock14파일 보존 확인. 기존 백업/사용자 MP4 덮어쓰기·삭제 없음.
- Node24.22.1/npm12.2.2/HF0.9.23/Chrome152.0.7977.30/FFmpeg9.0.1/Noto 유지. Python 환경·플러그인 설치 변경 없음.
- .tools/node_modules/Chrome/캐시/output MP4는 Git 제외. 유료 API·새 대본·TTS 호출 없음.

## 다음 우선순위 / 제한

- 현재 지점에서 멈춤. 다음 요청 시 캡처/인코딩·메모리 병목을 화질 유지 조건으로 개선하고 cold/warm 통제 비교.
- 공개 자료 적합성, 벤치마킹 사실 확인, forced_fallback 제어는 별도 미해결 작업. 이번 저장 대본의 요금 사실을 새로 검증하지 않음.
- 장문2줄·실제 BGM/SFX·긴 영상/다양한 원본 비율 추가 검증 필요.
- GitHub 추가 Commit/Push, 경제·공학 프리셋·variants 및 대형 기능은 별도 승인/요청 전 진행하지 않음.
