# HANDOFF — 현재 상태

> 규칙 원본: AGENTS.md. 현재 상태 80줄 이하. 이전 PoC 상태는 docs/history/HANDOFF_2026-11-08_hyperframes_poc.md.
> 상세 결과: docs/HYPERFRAMES_INTEGRATION_2026-11-09.md.

## 현재 상태 (2026-11-09, Codex) — HyperFrames 2단계 최소 통합 완료

- 폴더 `shorts-ai-codex`, 브랜치 `codex/shorts-handoff-20261106`, 기준 `7a5d7da`.
- 2026-11-10 작업 A: 이 2단계 성공 상태의 선별 Commit·일반 Push 승인. 원격 SHA 일치 후에만 3단계 시작.
- 기본 렌더러 **ffmpeg** 유지, `make`·`rerender --renderer hyperframes` 선택 가능.
- `--renderer-fallback none|ffmpeg`; 기본 none. 실제 사용 렌더러·폴백·실패 로그 기록.
- 기존 timeline.json 그대로 재사용. 새 제작에서 선택적 `render` 설정만 확장, 재렌더는 원본 timeline을 수정하지 않음.
- 재렌더 결과는 프로젝트 renders/의 고유 경로. 기존 final.mp4·썸네일·사용자 데이터는 보존.
- 3단계 품질·성능 개선도 사용자 승인됐으나 이 2단계 복구 지점의 원격 저장 전에는 시작하지 않는다.

## 변경 파일 / 구조

- `app/pipeline/timeline.py`: 공통 선택/기록/출력 보호, 원래 FFmpeg 호출 유지(ASS만 새 렌더 폴더에 저장).
- `app/pipeline/hyperframes.py`: 로컬 HTML 어댑터·자막·오디오 믹스·경로/HTML 검증·동시성/오류 격리.
- `renderers/hyperframes/timeline.html`, `scene.html`: 하위 합성 템플릿. 별도 콘텐츠 입력 JSON 체계 없음.
- `app/factory/core.py`, `__main__.py`, `app/pipeline/run.py`, `config.yaml`: 옵션·상태·새 결과 경로 연결.
- `app/pipeline/sources.py`: 선택 효과음도 권리 대장 검사. 기존 render.py·TTS 코드는 수정하지 않음.
- `tests/test_hyperframes.py` 34개 추가. 기존 mock/날짜 fixture 5개 보완, 기존 343개 유지.
- `scripts/compare_renderers.py`, `verify_renderer_comparison.py`: 실제 CLI 비교·계측·완성 영상 검증.

## 설치 / 보호

- Node 24.22.1·npm/npx 12.2.2·HyperFrames **0.9.23**·GSAP 3.14.2·Chrome 152.0.7977.30 그대로 사용.
- 도구/캐시 `.tools/hyperframes/`, Node 의존성 `renderers/hyperframes/node_modules/` — Git 제외.
- 기존 Noto Sans KR/OFL·GSAP은 PoC의 로컬 파일 재사용. Python 환경·플러그인·스킬 추가 설치 없음.
- HyperFrames 동시 렌더 1개·worker 1개. 실패해도 기존 FFmpeg 경로 유지. 유료 API 호출 없음.
- 시작 상태와 성공 PoC 원본/결과 40파일 백업: `../backups/hyperframes-phase2-20261109/` (ZIP·patch·SHA).
- 다른 worktree/미커밋 변경 및 `../shorts-ai-shorts/output` 원본 보존. PoC 소스·잠금·설정·결과 유지.

## 실제 쇼츠 비교 완료 (대본·TTS 재생성 없음)

- 원본 `../shorts-ai-shorts/output/20261105_231559_d127` 난방비 쇼츠를 `output/20261109_hf_comparison`으로 복제.
- FFmpeg: `renders/rerender_ad41ade184164e2992febbe77b6f6ccd/final.ffmpeg.mp4` (위 복제 프로젝트 기준).
- HyperFrames: `renders/rerender_dc16083aa23e4fc0b2fb056c5df4e571/final.hyperframes.mp4`.
- 둘 다 H.264+AAC·1080×1920·30fps·889프레임. 길이 A 29.660340초 / B 29.633333초.
- **FFmpeg 결과는 기존 완성 MP4와 바이트·SHA까지 동일** (a088ab95…457c241b).
- 렌더 단계 A 17.066초 / B 47.461초, CLI 전체 A 18.111초 / B 48.528초.
- 관측 최대 메모리(프로세스 트리 working set 합계) A 1.087 GiB / B 2.413 GiB.
- 파일 크기 A 5,834,397 / B 5,907,302 bytes. 평균 CPU(12논리CPU) A 35.73% / B 17.19%.
- 단어 시간 49개·자막21큐 재사용, 오디오 지연 둘 다 0ms(8kHz 비교), 새 AI 호출 0.
- HyperFrames 완성 889프레임 안전영역 침범0, 하이라이트 검증 588/588 프레임 일치, 한글 깨짐·잘림 없음.
- 최종 브라우저 엄격 검사 7항목 오류0·경고0. 1/4/9/16/22/28초 실제 MP4 캡처 확인.
- 기록·비교 이미지: `output/hyperframes-comparison-20261109/` (verification·ffprobe·metrics·samples·logs).
- 한계: HF는 여백이 많고 원본 카드 내부 글자가 작다. 원래 외국어 표 이미지의 낮은 적합성도 그대로다.

## 테스트 / 다음 작업

- 최종 전체 **377개 통과 / 70.058초** (기존343 + 신규34), 실패·skip 없음.
- FFmpeg 그래프/ASS 보존, 선택/명시 폴백/실패/취소/잠금, V1호환, 경로보안/HTML이스케이프, 자막·오디오 테스트 포함.
- 다음: 안전영역 안 화면 활용도·메모리/전처리 최적화·장문2줄/BGM/SFX 실제 사례 검증.
- 소스 적합성·사실 확인·콘텐츠 forced_fallback 제어는 별도 미해결 작업.
- **경제·공학 프리셋과 --variants 3은 아직 구현하지 않았다.**

## 기존 완료 기능 / 공통 제한

- 기존 Shorts 제작·대본검토·resume·순차제작·채널 벤치마킹 완료. C·D는 재제작하지 않음.
- 카드뉴스·인스타툰·캐릭터 복원 금지. app/pipeline/cards.py는 Shorts 공통 그래픽이므로 유지.
- output·backups·reference·samples·characters·가상환경 보존. 유료 API·commit/push는 별도 승인.
