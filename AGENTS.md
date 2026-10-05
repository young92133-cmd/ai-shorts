# AI 콘텐츠팩토리 — Codex / Claude Code 공통 작업 규칙

이 프로젝트는 한국어 9:16 유튜브 쇼츠를 만드는 **범용 AI 콘텐츠팩토리**다.
**이 채팅이 메인 화면**이다. Codex와 Claude Code는 사용자의 자연어 요청을 아래 명령으로 바꿔 실행하고, 결과 JSON을 쉬운 말로 알려준다.
웹 UI(`AI Shorts 실행.cmd` → http://127.0.0.1:8765)는 결과 확인·세부 수정·미리보기용 보조 화면이다.

**현재 범위(2026-10-01): V1 기능과 실사용 검증.** 영상 품질 고도화(2E 모션·고급 자막, BGM/효과음 추천, 레퍼런스 복제, Shot 세분화, AI 영상, 스타일팩)는 V2로 미룬다. 최신 완료 상태·실제 산출물은 `HANDOFF.md` 맨 위를 읽는다. V2는 사용자의 별도 요청 전에는 시작하지 않는다.

2026-10-01 V1 검증 기록: 기존 95개 포함 자동 테스트 132개, Claude 실제 제작 10편·직접 대본 2편, 입력 6종과 두 편 순차 검토/resume 통과. 유료 OpenAI 실호출은 하지 않았다. 새 변경의 GitHub push는 별도 요청 전에는 하지 않는다.

```
Claude Code / Codex (채팅) ─→ app/factory (명령층) ─→ app/pipeline (제작 엔진) ←─ Web UI (보조)
```

## 명령 (프로젝트 폴더에서, 가상환경 파이썬으로)

`.venv\Scripts\python.exe -m app.factory <명령>` 을 실행한다. 결과는 stdout JSON 한 덩어리이고, 진행 로그는 stderr로 나온다.
종료 코드는 0 성공, 1 제작 실패, 2 요청 오류(없는 프로젝트·잘못된 값·아직 할 수 없는 단계)다.

| 명령 | 하는 일 |
|---|---|
| `make --topic "주제" [--seconds 45]` | 주제로 조사 → 대본 → 장면 → 음성 → 화면 → 자막 → MP4 |
| `make --url "링크" [--seconds 50]` | 유튜브·기사 링크 내용을 참고해 새 대본으로 제작 (원본 영상·글은 화면에 안 씀) |
| `make --auto` | 요즘 화제 소재를 AI가 골라 제작 |
| `make --script "완성 대본"` / `--script-file 파일` | 완성 대본 직접 입력 (보조 기능) |
| `make --reference-video 파일 [--hint "메모"]` | 참고 영상 업로드 분석 → 새 대본 → MP4 (원본은 화면에 쓰지 않음) |
| `make ... --format information\|story\|issue` | 정보형 / 스토리·사연형 / 일반 이슈형 기본 지침 |
| `make ... --llm claude\|openai\|auto` | AI 공급자 선택 (기본 Claude 구독) |
| `make ... --review` | **대본까지만** 만들고 승인 대기로 멈춤 |
| `make ... --benchmark auto\|off\|<profile id>` | 콘텐츠 구조 선택. 기본 auto(8개 중 자동 선택), off는 기존 V1 구성 |
| `make ... --style "이름"` / `--preset daily` | 스타일·분야 기본값 지정 (`styles`로 목록 확인) |
| `make ... --asset 파일 --note "근거" --confirm-rights` | 내가 권리를 가진 사진·영상을 장면 화면 후보로 |
| `resume [id]` | 멈춘/실패한 프로젝트를 저장된 대본으로 이어서 MP4까지 (조사·대본 다시 안 함) |
| `status [id]` | 진행 상태 (id 생략 = 가장 최근 프로젝트 + 최근 목록) |
| `inspect [id] --part script\|scenes\|visuals\|benchmark\|files\|all` | 대본·장면 시간·화면 선택 이유·구조 선택 기록·파일 |
| `edit-scene [id] --scene 3 --narration "…" --emphasis "…"` | 렌더 전 장면 문장/강조문구 수정 |
| `set-visual [id] --scene 3 --card number_card` | 렌더 후 장면 화면을 카드로 바꾸고 다시 렌더 |
| `set-visual [id] --scene 3 --file 사진 --note "근거" --confirm-rights` | 장면 화면을 권리 확인된 사진으로 |
| `rerender [id]` | 저장된 재료로 영상만 다시 렌더 (조사·대본·음성 다시 안 함) |
| `styles` / `trends` | 스타일·프리셋 목록 / 화제 키워드 |
| `trends --limit 5` | 번호와 `candidates_id`가 있는 후보 5개를 파일로 보존 |
| `batch --select 2 4 --candidates ID` | 해당 후보 목록의 2·4번을 순서대로 제작 |
| `batch --topic "주제" --count 3` | 같은 주제에서 다른 관점으로 3편 순차 제작 |
| `batch --topic "첫 주제" --topic "둘째" [--review]` | 여러 주제 순차 제작 (검토 옵션이면 편마다 대본 저장 후 멈춤) |
| `batch-status [ID]` / `batch-resume [ID]` | 순차 제작 조회 / 저장 대본을 한 편씩 이어서 완성 |
| `export [id] [--pack] [--capcut]` | 완성 파일 목록 / 편집 재료 zip / CapCut 프로젝트 |

장면 번호는 사용자에게 보이는 대로 1부터 센다. 카드 종류: hook_card, statement_card, focus_card, quote_card, number_card, trend_card, compare_card, summary_card.

## 자연어 → 명령

말투가 달라도 의도로 판단한다. 아래는 예시다.

| 사용자 말 | 실행 |
|---|---|
| "고양이가 상자를 좋아하는 이유로 45초 쇼츠 만들어줘", "이걸로 쇼츠 만들어줘" | `make --topic "…" --seconds 45` |
| "이 링크 50초 영상으로 만들어" | `make --url "…" --seconds 50` |
| "요즘 뜨는 걸로 하나 만들어줘" | `make --auto` (또는 `trends`로 후보를 보여주고 고르게) |
| "대본까지만 만들어", "대본 먼저 보여줘" | `make … --review` → 대본을 장면별로 보여준다 |
| "대본 괜찮네 계속해", "좋아, 계속해" | `resume` (가장 최근 대기 프로젝트) |
| "2번 장면 문장 이렇게 바꿔줘" (렌더 전) | `edit-scene --scene 2 --narration "…"` 후 다시 보여준다 |
| "3번 장면 화면 바꿔줘" | 렌더 후면 `set-visual --scene 3 --card …` (내용에 맞는 카드 선택). 사용자가 사진을 주면 권리를 물어본 뒤 `--file` |
| "완성본 다시 뽑아줘" | `rerender` |
| "어디까지 됐어?" | `status` |
| "장면별로 보여줘", "왜 이 화면 골랐어?" | `inspect --part visuals` |
| "파일 어디 있어?", "캡컷으로 보내줘" | `export` / `export --capcut` |
| "무슨 스타일 있어?" | `styles` |
| "오늘 화제 소재 5개 찾아줘" | `trends --limit 5` → 반환된 번호·후보 id를 대화에 남긴다 |
| "그중 2번, 4번으로 각각 만들어줘" | `batch --select 2 4 --candidates <대화에서 선택한 목록 id>` |
| "이 주제로 쇼츠 3개 만들어줘" | `batch --topic "…" --count 3` |
| "이 참고 영상 파일로 만들어줘" | `make --reference-video "파일"` |
| "중간 확인 없이 45초로 완성해" | `make --topic "…" --seconds 45` (`--review` 없음) |
| "두 대본 다 좋아. 계속 만들어" | 해당 `batch-resume ID` |

## 기본 흐름과 멈추는 때

- **기본은 끝까지 자동**이다. 사용자가 대본 확인을 요청하지 않았으면 `make`로 MP4까지 만든다.
- 사용자가 "대본 먼저", "대본까지만", "확인하고 싶어"라고 하면 `--review`로 멈추고 대본을 보여준 뒤 승인(`resume`)을 기다린다.
- 확인 없이 **자동으로 계속해도 되는 것**: 재시도 가능한 실패 후 `resume` 제안, 조회(`status`/`inspect`/`styles`), 사용자가 요청한 `rerender`.
- **반드시 먼저 물어볼 것**:
  - 유료 API로 바꾸기(OpenAI·ElevenLabs·Typecast·이미지 생성 등)
  - 권리가 불분명한 파일을 화면에 쓰기
  - 여러 편 연속 제작
  - 업로드·게시
  - 기존 결과 삭제
- 한 번에 한 편만 만든다. 영상 한 편은 보통 3~6분 걸린다. 명령 실행에는 넉넉한 제한 시간(10분)을 준다.
- 여러 편은 **명시적 요청이 있을 때만**, 한 편씩 순차로 만든다(한 번에 최대 10편). 한 편 실패해도 성공한 영상은 보존한다. 후보 번호는 사용자가 보고 고른 `candidates_id`에 연결한다. 다른 검색의 최근 목록으로 바꾸지 않는다.
- `resume`에서 id를 생략하면 가장 최근의 이어 만들 수 있는 대기 프로젝트를 선택한다. 대화에서 id가 알려져 있으면 항상 지정한다. 직접 대본도 Factory에서는 `--review`를 지정했을 때만 멈춘다(기존 웹 UI의 강제 검토는 별도).

## 자료 권리 규칙 (꼭 지킨다)

- 영상 화면에 쓸 수 있는 것:
  - 사용자 본인 채널 영상
  - 사용자가 직접 만든 사진
  - AI가 생성한 이미지
  - 앱이 그린 카드
  - 무료 스톡(pexels·pixabay)
  - 공공누리 1유형(kogl_type0/1)
- 다른 사람의 영상·기사·댓글·이미지는 **내용 참고용**이다. 화면에 그대로 넣지 않는다.
- 사용자가 준 파일은 권리 근거(`--note`)를 확인하고 `--confirm-rights`를 붙인다. 확인되지 않은 파일은 엔진이 거부한다. 우회하지 않는다.
- 렌더 전 권리 검사(`sources.json`)는 엔진이 강제한다.

## 무료·유료 API

- 기본 설정은 무료다.
  - 대본: Claude Code 구독 로그인
  - 음성: Edge TTS
  - 화면: 앱 카드와 업로드 자료
- API 키가 필요한 유료 기능은 사용자가 원할 때만 켠다.
- Factory LLM 모드는 `claude`, `openai`, `auto`다. `claude`는 `ANTHROPIC_API_KEY`·API 토큰을 SDK 환경에서 비워 **구독 로그인**만 쓴다. Anthropic API로 자동 전환하지 않는다.
- OpenAI는 **사용자 명시적 허용 + 키 설정**이 모두 있어야 한다. 허용된 요청에만 `--allow-openai`를 붙이거나, 사용자가 허용한 경우 `config.yaml`의 `llm.allow_paid_openai: true`를 쓴다. 키가 있다는 이유만으로 허용하지 않는다. 허용을 임의로 추가하지 않는다.
- `auto`는 Claude부터 시도한다. 사용량 한도·인증·명확한 일시적 서비스 오류에서만 위 OpenAI 조건을 확인하고 전환한다. JSON/스키마·거부·대본 품질 때문에 전환하지 않는다. 한 프로젝트에서 전환한 뒤에는 같은 성공 공급자를 사용한다.
- Factory는 이미지 API를 끄고 기본 TTS를 Edge로 정한다. 환경의 Gemini/OpenAI 키만으로 비전·음성 인식 요금을 발생시키지 않는다. 참고 영상은 기본 로컬 Whisper CPU int8로 분석한다(`faster-whisper`, 첫 모델 다운로드 필요). CUDA는 필요하지 않고 원본 언어를 자동 감지한다. `requirements.txt`의 PyAV 호환 조건을 유지한다.
- `project_state.json`의 `ai_calls`, `ai_provider_used`, `ai_providers_used`가 실제 결과다. `none`은 성공한 AI 호출이 없다는 뜻이다. 대본 수동 입력의 규칙 기반 분할을 AI 성공으로 보고하지 않는다.
- API 키, `.env`, 토큰, 비밀번호는 읽어서 출력하거나 커밋하거나 채팅에 쓰지 않는다.

## 결과 위치

- 프로젝트마다 `output/<project_id>/` 폴더가 생긴다.
- 폴더에 들어가는 파일:
  - 영상과 설명: `final.mp4`, `thumb.jpg`, `meta.txt`(제목·설명·해시태그·출처)
  - 대본과 상태: `script.json`(대본), `project_state.json`(상태)
  - 장면 기록: `blueprint.json`(장면별 시간·화면 결정), `visuals.json`(화면 선택 기록), `timeline.json`(렌더 재료)
  - 권리 대장: `sources.json`
  - 음성과 이미지: `audio/`, `scenes/`
- 완성되면 `job.json`도 남는다. 웹 UI를 다시 켜면 목록에 보인다.
- 사용자에게는 `final_video` 경로, 길이, 해상도, 장면별 화면 요약을 알려준다.

## 실패했을 때

- JSON의 `status`가 `failed`이면 `message`(오류)와 `failed_at`(멈춘 단계)을 쉬운 말로 설명한다.
- `next_action`이 `resume`이면 대본은 살아 있다는 뜻이다. 원인(인터넷·음성 서버 등)이 해결되면 `resume`한다. 조사·대본은 다시 하지 않는다.
- `next_action`이 `make`이면 대본 전에 실패한 것이다. 주제나 링크를 확인하고 새로 `make`한다.
- `ffmpeg`가 없거나, Claude 로그인이 풀렸거나(`claude-login.cmd`), 인증·권한 문제가 생기면 우회하지 않는다. 사용자가 할 일만 안내한다.

## 개발 규칙

- **제작 엔진(`app/pipeline`)을 새로 만들거나 갈아엎지 않는다.** 기능은 엔진에 작게 추가하고, 채팅용 동작은 `app/factory`에 둔다.
- 웹 UI와 factory는 같은 엔진을 쓴다. 엔진은 UI(`app/main.py`, `app/jobs.py`)를 import하지 않는다.
- 개발 중에는 유료 API·실제 샘플 제작을 하지 않는다. 테스트는 가짜(mock)로 돈다. 실제 제작은 사용자가 요청할 때만 한다.
- `make` 를 부르는 테스트는 `run.bench_auto.ask_structured` 도 반드시 가짜로 막는다(`tests/test_factory.py` FactoryTestCase 참고). 막지 않으면 기본 benchmark auto 가 실제 Claude 를 호출한다.
- 2026-10-01 V1 요청은 서로 다른 실제 영상 최소 5편 검증을 허용한다. 유료 API는 여전히 미승인이다. 모든 실사용·회귀 테스트가 통과한 뒤에만 V1 완료 로컬 커밋을 만든다. 새 변경의 push는 하지 않는다(시작 시 `c6cd645` 백업 push만 승인됨).
- 테스트: `.venv\Scripts\python.exe -m unittest tests.test_blueprint tests.test_reference_workflow tests.test_script_split tests.test_sources tests.test_timeline_export tests.test_tts_timeline tests.test_visual_resolver tests.test_factory`
- 전체 테스트: `.venv\Scripts\python.exe -m unittest discover -s tests -q` (V1·Benchmark·Benchmark×V1 통합 `tests/test_benchmark_auto.py` 포함 228개).
- Git 규칙:
  - force push 하지 않는다.
  - 기존 커밋·원격 브랜치를 수정하거나 삭제하지 않는다.
  - 비밀정보는 커밋하지 않는다.
  - push는 사용자가 요청할 때만 한다.
- 진행 기록은 `IMPLEMENTATION_PLAN.md`(계획)와 `HANDOFF.md`(작업 인계)에 남긴다.

## Benchmark × V1 자동 통합 (2026-10-05, 기본값)

`make`(topic·url·auto·reference-video)는 **기본으로 `--benchmark auto`** 다. 사용자는 profile 이름을 몰라도 된다.
"○○ 주제로 쇼츠 만들어줘", "이 유튜브 참고해서 만들어줘: URL" → 그냥 `make --topic …` / `make --url …` 를 실행한다.

내부 흐름: 조사 → **Content Brief(AI 1회)**: verified_facts / inference 분리, 시청 질문 후보 2~3개(View Potential 5항목×20점), 8개 profile 9기준 점수
→ **Auto Router**(가중합 0~100 + 게이트: 권리 확인 영상이 필요한 kpop_observation_clip·physics_comparison_simulation·ranked_moments 는 그런 영상이 없으면 제외, 필수 근거 슬롯 부족 시 제외, 기준 45점 미만이면 `illustrated_fact_explainer` fallback)
→ 선택 profile 에 맞는 보충 조사 1회 → **구조 주입 대본**(장면별 beat_role·시간·글자 예산·훅/결론/마지막 질문, 사실·추론·창작 분리) → 기존 장면 설계 + `apply_scene_plan`(장면 역할·카드 성격·강조 길이) → 기존 Edge TTS·자막·카드·렌더.
기존 구성 분석(`make_plan`)은 benchmark 가 켜지면 건너뛰므로 AI 호출 수는 그대로 3회(brief·대본·장면)다.

- 점수는 **현재 자료로 어떤 구조가 경쟁력 있는지 고르는 내부 판단값**이다. 사용자에게 조회수·성공 확률이라고 말하지 않는다.
- 결과: `project_state.json` 의 `benchmark`(mode, selected_profile, candidate_scores, top3, viewer_question, reason_to_watch, claim, view_potential_score, selection_reason, fallback_used, narration_mode, scene_roles, quality) + 전체 기록 `benchmark_decision.json`(사실·추론·후보·원본 분석). `inspect --part benchmark` 로 본다.
- `resume`·`rerender`·`batch-resume` 은 저장된 결정을 그대로 쓰고 다시 고르지 않는다. 완성 대본(`--script`)은 `not_applicable`, 스타일 지정(`--style`)은 auto 일 때 스타일을 따른다.
- 사용자에게 결과를 알릴 때: 고른 구조 이름, 시청 질문, 선택 이유, 상위 3개 점수, fallback 여부와 quality 경고를 쉬운 말로 전한다.
- 유튜브·기사 URL 은 분석 참고용이다(`source_analysis`). 원본 문장·장면 순서를 복제하지 않고, 타인 영상을 내려받아 화면에 쓰지 않는다.
- 이번 단계에 없음: Clip Analyzer(권리 확인 내 영상의 하이라이트 자동 선택), 자동 게시, 채널 크롤링, Global Trend Radar, 조회수 예측, 성과 학습.

| 사용자 말 | 실행 |
|---|---|
| "이 주제로 쇼츠 만들어줘" | `make --topic "…"` (benchmark auto 기본) |
| "이 유튜브 참고해서 쇼츠 만들어줘: URL" | `make --url "URL"` |
| "비교형/사건 순서형으로 만들어줘" 처럼 구조를 명시 | `make --topic "…" --benchmark <profile id>` (예: event_timeline_story) |
| "예전 방식(구조 선택 없이)으로 만들어줘" | `make --topic "…" --benchmark off` |
| "왜 이 구성으로 만들었어?" | `inspect <id> --part benchmark` |

## Benchmark 인벤토리와 오프라인 경로 (2026-10-05)

현재 기준은 shorts-ai의 오프라인 Benchmark Engine이다. `docs/BENCHMARKS.md`와 `benchmark sources/profiles`를 먼저 확인한다.
별도 shorts-ai-benchmark-v2는 별도 컨셉 작업이므로 사용자가 그쪽 구현을 요청하지 않으면 임의로 합치지 않는다.

사용자가 "이 채널 벤치마킹해줘"라고 하면 최소한 source 분석을 구조화하고, 기존 profile 중복/variation/새 profile 필요성을 판단해
`benchmarks/sources`와 `docs/BENCHMARKS.md`에 관찰 깊이/상태/다음 작업을 기록한다. 말로만 분석을 끝내지 않는다.
새 production 코드는 분석 요청만으로 자동 변경하지 않는다. "반영/업데이트/구현" 요청이 있으면 load/선택/실제 pipeline/테스트를 검증해 연결한다.
source와 profile은 양방향 연결하며 채널 수와 profile 수를 구분한다. 사례별 시청 이유/질문/hook/claim/근거/payoff/길이/리듬/음성/자막/반복/후속/시각 전략을 추출한다.
관찰한 사실, 목록만 나온 스타일, 제안한 제작 변형, 실제 검증한 경로를 구분하고 미확인 성과/날짜/인물/반응을 추측하지 않는다.
타 채널 로고/워터마크/정확한 폰트/색상/그래픽/원문 대본/장면을 복제하거나 원본을 자동 다운로드하지 않는다.

자연어 요청과 실행:

| 사용자 요청 | 처리 |
|---|---|
| "이 주제로 curiosity_update_story 적용해서 만들어줘" | 기본: `make --topic "…" --benchmark curiosity_update_story` (조사·나레이션 포함). 사용자가 근거 JSON을 직접 준 경우에만 오프라인 `benchmark plan --profile … --input …` → `benchmark render ID` |
| "이 영상으로 kpop_observation_clip 방식으로 만들어줘" | 권리 확인 로컬 영상의 관찰/타임코드를 기존 kpop JSON으로 기록 → 같은 plan/render |
| "physics_comparison_simulation 방식으로 제작해줘" | 직접 만든 실험 영상/조건/고정 환경을 확인 → physics 양식 → plan/render; 시뮬레이션 영상 생성은 미지원임을 알려준다 |
| "레스기처럼 순위로 묶어줘" | 채널 복제 대신 ranked_moments, N위부터1위 근거 클립과 순위 기준을 기록 |
| "건축 원리 설명/발언 맥락/숫자 정보/사건 시간 순서" | 각각 mechanism_explainer / quote_context_story / illustrated_fact_explainer / event_timeline_story의 근거 JSON → plan/render |
| "계획만 먼저 보여줘" | plan/inspect 결과를 보여주고 멈춘다 |
| "벤치마크 계속/다시 렌더" | 대화에 알려진 benchmark ID로 `benchmark render ID`; V1 resume를 사용하지 않는다 |

Benchmark 입력 양식은 예시이며 실제 분석/사실이 아니다. 사용자의 사실/영상 입력으로 교체한다. URL(reference)은 provenance 문자열이고 엔진은 접속하지 않는다.
오프라인 `benchmark plan/render` 경로의 이야기 profile은 narration 없는 자체 카드 adapter다(위 V1 자동 통합은 나레이션 포함). 번역/Blender/고급 지도 생성/Global Trend Radar는 아직 없다.
source/profile/코드/문서를 함께 갱신하고 기존 V1 전체 테스트와 Benchmark 회귀 테스트를 실행한다. 테스트/실렌더/흥행 확인을 서로 대신 보고하지 않는다.
