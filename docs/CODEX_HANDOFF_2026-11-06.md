# Codex 인수인계 — 2026-11-06 (Claude Code → Codex)

> 이 문서와 `HANDOFF.md` 맨 위만 읽으면 된다. 전체 저장소를 다시 훑지 않는다. 규칙 원본은 `AGENTS.md`.

## 1. 저장소 · 브랜치
- `https://github.com/young92133-cmd/ai-shorts`, 브랜치 **`feature/shorts-only`** (기준 `feature/agent-content-factory` 96bc82a 에서 분기).
- 작업 폴더 `../shorts-ai-shorts` (git worktree). 다른 worktree(`shorts-ai`, `shorts-ai-styles`, `shorts-ai-benchmark-v2`)의 미커밋 변경은 이 브랜치와 무관 — 건드리지 않는다.

## 2. 프로젝트 방향이 바뀌었다
**유튜브 AI Shorts(9:16 MP4) 자동 제작 전용 개인 PC 프로그램**이다. 2026-11-05 사용자 결정으로 아래를 **제거**했다. **다시 추가하거나 복원하지 않는다**(사용자가 명시적으로 요청할 때만).
- 카드뉴스·인스타툰·혼합형(hybrid/all) 제작, 카드뉴스 스튜디오 `/studio`, 햄토리치 등 캐릭터·포즈·그림체 기능, 카드 전용 렌더러·API·CLI(`toon`, `characters`, `make --format card_news…`, `topics plan`)·테스트.
- 삭제한 코드: `app/carousel/`, `app/studio/`, `app/factory/{toon,intent}.py`, `tests/test_{carousel,studio}.py`, `scripts/sample_free_instatoon.py`, `카드뉴스 스튜디오 실행.cmd`, `assets/inbox/`.
- 옛 문서는 `docs/history/carousel_2026-10/`, 옛 코드는 브랜치 `feature/agent-content-factory` 와 `../backups/shorts-only-before-20261105/RESTORE.md`.
- **유지(공통 코드):** `app/pipeline/cards.py` — 쇼츠 장면 화면 카드(hook/statement/number/compare…)를 그린다. 카드뉴스 코드가 아니다. `characters/`·`samples/` 파일도 사용자 결정으로 보존(코드에서 안 씀).
- output 의 예전 카드 프로젝트는 `core.LEGACY_FORMATS` 로 알아보고 "이어 만들 수 없음"만 안내한다.

## 3. 구조와 주요 위치
```
채팅 → app/factory (명령층) → app/pipeline (제작 엔진) ← 웹 UI app/main.py · jobs.py · static/app.js · templates/index.html
                  ├ app/topics (주제 수집·검증·승인 → brief.shorts_brief → core.make)
                  └ factory/channels → pipeline/channels (경쟁 채널 벤치마킹 → 추천 주제 → make/batch)
```
| 기능 | 위치 |
|---|---|
| 제작 한 편 | `app/factory/core.py` `make` / `resume` / `rerender` / `edit_scene` |
| 엔진 전체 흐름 | `app/pipeline/run.py` `run_pipeline` |
| 콘텐츠 구조 자동 선택(8 profile) | `app/pipeline/bench_auto.py`, `benchmarks/v1/integration.yaml` |
| 대본 분할·화면 문구 | `app/pipeline/script_split.py` `short_phrase` / `analyze_scene` |
| 장면 카드 그림 | `app/pipeline/cards.py` `render_card` / `fit_text` |
| 공개 자료 탐색·권리 | `app/pipeline/source_resolver.py`, `sources.py` |
| 음성 | `app/pipeline/tts/` (edge 기본) |
| 자막·렌더 | `subtitles.py`(ASS) → `timeline.py` `render_timeline` → `render.py`(ffmpeg) |
| 순차 제작 | `app/factory/batch.py` |
| 채널 벤치마킹 | `app/pipeline/channels.py`(수집·지표·AI 패턴·비교·겹침 감시), `app/factory/channels.py`(명령·캐시) |

## 4. 실행
```
..\shorts-ai\.venv\Scripts\python.exe -m app.factory make --topic "주제" [--review] [--seconds 30]
..\shorts-ai\.venv\Scripts\python.exe -m app.factory resume <project_id>
..\shorts-ai\.venv\Scripts\python.exe -m app.factory batch --topic "A" --topic "B"
..\shorts-ai\.venv\Scripts\python.exe -m app.factory channel analyze @채널 [--refresh] [--no-ai]
..\shorts-ai\.venv\Scripts\python.exe -m app.factory channel topics <channel_id>      # → candidates_id
..\shorts-ai\.venv\Scripts\python.exe -m app.factory batch --select 2 --candidates <candidates_id>
```
웹 화면: `AI Shorts 실행.cmd` (http://127.0.0.1:8765, 사이드바 '경쟁 채널 분석').
Codex 환경은 `./scripts/factory.ps1 <명령>` (AGENTS.md '명령' 절).

## 5. 환경
- Python 3.12, 가상환경은 **`../shorts-ai/.venv` 를 공유**(이 worktree 에는 .venv 없음). ffmpeg 9.0.1(PATH).
- `edge-tts==7.3.1` 로 올림 (7.2.8 은 2026-11 Microsoft 서버 403). `requirements.txt` 는 `>=7.3.1`.
- AI: Claude Code **Pro 구독** 로그인(`claude auth status` → authMethod claude.ai). `loggedIn: true` 여도 OAuth 만료가 있을 수 있음 → 사용자에게 `claude-login.cmd` 안내.
- YouTube Data API 키 없음 → 채널 수집은 공개 페이지 메타데이터(yt-dlp, 로그인·다운로드 없음). 댓글은 미수집.

## 6. 테스트
`..\shorts-ai\.venv\Scripts\python.exe -m unittest discover -s tests -q` → 2026-11-06 **343개 통과**. 외부 서비스는 전부 mock.
`make` 를 부르는 테스트는 `run.bench_auto.ask_structured`·`run.source_resolver.resolve` 도 mock(AGENTS.md).

## 7. 실제 검증 결과 (실영상)
| 검증 | 결과 |
|---|---|
| 완성 대본 → MP4 (AI 없이) | `output/20261105_223157_b176` 27.0초. TTS 403 실패 → resume 으로 완성 |
| 주제 → 대본 검토 → 장면 수정 → 승인 → MP4 | `output/20261105_231559_d127` 29.7초, 공개 CC0 영상·CC BY 사진 포함 |
| 서로 다른 주제 2편 순차 | `batch_20261105_232321_ab58` 25.6초·25.5초 |
| 채널 분석 | 짤잉 @zzal_ing: 목록 150 · 상세 45 · 공개 자막 6, 패턴 5개 · 새 주제 5개 (Claude 1회/분석) |
| 벤치마킹 기반 쇼츠(D) | 1차 `20261106_220410_91bf` 는 분야가 빠져 야구로 조사됨 → `search_query` 추가 후 2차 `output/20261106_221220_cad4` 22.2초 성공(K팝 신인 걸그룹 근황, 원본 자막 겹침 0.0) |
모든 결과는 1080×1920 · 30fps · H.264 + AAC. output 은 Git 에 없다(사용자 PC 에만).

## 8. 남은 문제
- 영상 소스 장면 적합성: 영어 문서 표 같은 약한 공개 이미지가 뽑히기도 함. K팝처럼 공개 자료가 없으면 전부 자체 카드라 정적임.
- 벤치마킹 D 영상의 사실(수상·차트)은 블로그 출처뿐 — 게시 전 사람이 확인.
- 패턴 구조를 강제해도 근거가 부족하면 다른 구조로 fallback 될 수 있다(`benchmark.mode: forced_fallback`).
- 채널 분석에서 컷 편집·자막 디자인은 영상을 받지 않으므로 '미수집'(지어내지 않음).

## 9. HyperFrames 계획 (0단계 분석만 완료, **설치 안 함 — 사용자 승인 대기**)
- 기존 FFmpeg 렌더러가 기본값. `render_timeline` 에 `renderer: ffmpeg | hyperframes` 선택형 추가 예정, 새 모듈 `app/pipeline/hyperframes.py`.
- 입력은 **기존 `timeline.json` 확장**(scene type·animation·강조 단어·sfx). 새 JSON 체계를 따로 만들지 않는다.
- 렌더 프리셋 `presets/render/<id>.json` (기존 `presets/*.yaml` 은 콘텐츠 프리셋이라 이름 충돌 방지). 경제(다큐 톤·숫자 그래프)·공학(도면·하중 흐름) 예정.
- 폰트 `assets/fonts/NotoSansKR-VF.ttf`. 안전영역 상단 250·하단 400·우측 150px. BGM 덕킹은 ffmpeg `sidechaincompress` 로 미리 믹스.
- `--variants 3`: 같은 timeline 을 프리셋 2종 + 훅 문구 교체로 3개 렌더(AI 추가 호출 없음).
- 필요: Node.js 22+(현재 미설치), 공식 CLI(`npx hyperframes`, 버전 고정), Claude Code 플러그인. **Node·플러그인·브라우저 다운로드는 승인 전 실행 금지.** OpenMontage(AGPL) 코드는 복사 금지.

## 10. 다음 작업 우선순위
1. (승인 후) HyperFrames 1단계: Node 22 설치 → 10초 PoC(1080×1920·30fps·한글·카운트업·막대 차트·안전영역) → 렌더 시간 보고.
2. 장면 소스 적합성 개선(`source_resolver` 평가 기준: 글자 많은 외국어 문서 이미지 감점 등).
3. 공개 자료가 없을 때 카드 화면을 덜 정적으로.

## 11. 지켜야 할 것
- 유료 API(OpenAI·ElevenLabs·이미지 생성 등)·commit·push·삭제는 사용자 승인 후. `.env`·키는 읽거나 출력·커밋하지 않는다.
- output·reference.mp4·.venv·backups·samples·characters 삭제 금지. 강제 push·이력 재작성 금지.
- 벤치마킹: 원본 대본·영상 복사 금지, 성과 보장 표현 금지, 비공개 지표를 만들지 않는다.
