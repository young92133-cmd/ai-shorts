# AI 콘텐츠팩토리 — Codex / Claude Code 공통 작업 규칙

이 프로젝트는 한국어 9:16 유튜브 쇼츠를 만드는 **범용 AI 콘텐츠팩토리**다.
**이 채팅이 메인 화면**이다. Codex와 Claude Code는 사용자의 자연어 요청을 아래 명령으로 바꿔 실행하고, 결과 JSON을 쉬운 말로 알려준다.
웹 UI(`AI Shorts 실행.cmd` → http://127.0.0.1:8765)는 결과 확인·세부 수정·미리보기용 보조 화면이다.

**현재 상태(2026-10-08):** V1 제작 엔진 + Benchmark 8개 구조 자동 선택(`--benchmark auto`) + Source Resolver(`--visuals auto`)
+ Clip Analyzer + 인용·재가공 모드(transformative_quote, `--quote`) + 자막 정렬 + 카드뉴스·인스타툰 캐러셀(`--format`).
최신 완료 상태·실제 검증·한계는 `HANDOFF.md` 맨 위, benchmark 현황은 `docs/BENCHMARKS.md` 맨 위가 기준이다.
새 대형 기능(Global Trend Radar·Localization·Vision Clip Analyzer·성과 학습·자동 게시)은 사용자의 별도 요청 전에는 시작하지 않는다.

```
Claude Code / Codex (채팅) ─→ app/factory (명령층) ─→ app/pipeline (제작 엔진) ←─ Web UI (보조)
```

## 명령 (프로젝트 폴더에서, 가상환경 파이썬으로)

Topic Strategy V1: `topics collect/rank/recommend/calendar/approve/plan/create`가 추가됐다.
상세 CLI·검증 조건·원문/승인 보존은 `docs/TOPIC_STRATEGY.md`. 발행 API는 없고 `topics published`는 사람이 게시한 이력 기록이다.
번호 선택은 결과의 `selection_id`를 유지한다. `topics rank --ai` 외에는 전략 평가에 LLM을 호출하지 않는다.
개발 검증은 `tests/test_topics.py`; 실제 뉴스/Claude/API/PNG 샘플은 사용자 요청 없이 반복하지 않는다.

`.venv\Scripts\python.exe -m app.factory <명령>` 을 실행한다. 결과는 stdout JSON 한 덩어리이고, 진행 로그는 stderr로 나온다.
종료 코드는 0 성공, 1 제작 실패, 2 요청 오류(없는 프로젝트·잘못된 값·아직 할 수 없는 단계)다.

| 명령 | 하는 일 |
|---|---|
| `make --topic "주제" [--seconds 45]` | 주제로 조사 → 대본 → 장면 → 음성 → 화면 → 자막 → MP4 |
| `make --url "링크" [--seconds 50]` | 유튜브·기사 링크 내용을 분석해 새 대본으로 제작 (원본은 자동 다운로드하지 않음. 화면 인용은 `--quote` 로 준 파일) |
| `make --url "링크" --quote 영상·캡처 [--quote …]` | 분석·비평·비교·해설용 인용(transformative_quote). 출처는 링크에서 자동 기록 |
| `make --auto` | 요즘 화제 소재를 AI가 골라 제작 |
| `make --script "완성 대본"` / `--script-file 파일` | 완성 대본 직접 입력 (보조 기능) |
| `make --reference-video 파일 [--hint "메모"]` | 참고 영상 업로드 분석 → 새 대본 → MP4 (기본은 분석 전용, `--quote-reference` 를 붙이면 근거 장면에 인용) |
| `make ... --format card_news\|insta_toon\|hybrid\|all` | 카드뉴스·인스타툰·하이브리드 PNG(1080x1350) / all = 쇼츠+하이브리드 (아래 '카드뉴스 · 인스타툰' 절) |
| `make ... --tone information\|story\|issue` | 정보형 / 스토리·사연형 / 일반 이슈형 기본 지침 (예전 `--format 톤값`도 동작) |
| `characters [list\|show ID\|add --file]` | 인스타툰 캐릭터(Character Bible) 목록·보기·등록 |
| `make ... --llm claude\|openai\|auto` | AI 공급자 선택 (기본 Claude 구독) |
| `make ... --review` | **대본까지만** 만들고 승인 대기로 멈춤 |
| `make ... --benchmark auto\|off\|<profile id>` | 콘텐츠 구조 선택. 기본 auto(8개 중 자동 선택), off는 기존 V1 구성 |
| `make ... --visuals auto\|cards` | 화면 자료. 기본 auto(권리 확인 가능한 공개 영상·사진 자동 탐색), cards는 자체 카드만 |
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
| "이 영상으로 분석 쇼츠 만들어줘", "이 영상 재가공해서 만들어줘", "이 장면들 써서 비교해줘" (파일·캡처 있음) | `make --url "URL" --quote 파일 …` 또는 `make --reference-video 파일 --quote-reference` (라이선스를 묻지 않음) |
| "중간 확인 없이 45초로 완성해" | `make --topic "…" --seconds 45` (`--review` 없음) |
| "두 대본 다 좋아. 계속 만들어" | 해당 `batch-resume ID` |

## 작업 요청 규칙 (벤치마킹 · 반영 · 저장)

| 사용자 말 | 할 일 |
|---|---|
| "이 채널 벤치마킹해줘" | ① 실제 영상·목록 분석 ② `benchmarks/sources/<id>.json` 으로 구조화(채널명은 source 로만) ③ 기존 8개 profile 과 비교해 같은 구조인지·variation 인지·새 profile 이 필요한지 판단 ④ `docs/BENCHMARKS.md` 현황판에 analyzed/registered/profile/pipeline/tests/real video 상태와 다음 작업 기록. 분석만으로 코드를 바꾸지 않는다 |
| "프로그램에 반영해줘" | 기존 profile 의 variation 으로 통합하는 것을 먼저 검토하고, 정말 다른 구조일 때만 새 profile. `benchmarks/v1/integration.yaml`(beats·research_needs·source_strategy·evidence_roles) 갱신 → router·대본·장면 연결 → 테스트 → 현황판 상태 갱신. source 마다 profile 을 하나씩 만들지 않는다 |
| "저장해줘" | 전체 테스트 → `git status`·`git diff` 확인 → 비밀정보·output·미디어 제외 확인 → 새 commit → 현재 브랜치 일반 push. amend·rebase·squash·force push 금지 |

- 새 benchmark 를 분석·반영하면 `docs/BENCHMARKS.md` 맨 위 현황판을 반드시 같이 갱신한다. "분석됨"을 "구현됨"으로 적지 않는다.
- 실제 영상 검증 결과는 output 의 `project_state.json`·`verify_factory_v1.py --verify` 로 확인된 것만 기록한다.

## 기본 흐름과 멈추는 때

- **기본은 끝까지 자동**이다. 사용자가 대본 확인을 요청하지 않았으면 `make`로 MP4까지 만든다.
- 사용자가 "대본 먼저", "대본까지만", "확인하고 싶어"라고 하면 `--review`로 멈추고 대본을 보여준 뒤 승인(`resume`)을 기다린다.
- 확인 없이 **자동으로 계속해도 되는 것**: 재시도 가능한 실패 후 `resume` 제안, 조회(`status`/`inspect`/`styles`), 사용자가 요청한 `rerender`.
- **반드시 먼저 물어볼 것**:
  - 유료 API로 바꾸기(OpenAI·ElevenLabs·Typecast·이미지 생성 등)
  - 해설 없이 외부 영상을 그대로 보여 주는(재업로드에 가까운) 구성 요청 — 인용·해설 중심으로 바꾸자고 제안한다
  - 여러 편 연속 제작
  - 업로드·게시
  - 기존 결과 삭제
- 한 번에 한 편만 만든다. 영상 한 편은 보통 3~6분 걸린다. 명령 실행에는 넉넉한 제한 시간(10분)을 준다.
- 여러 편은 **명시적 요청이 있을 때만**, 한 편씩 순차로 만든다(한 번에 최대 10편). 한 편 실패해도 성공한 영상은 보존한다. 후보 번호는 사용자가 보고 고른 `candidates_id`에 연결한다. 다른 검색의 최근 목록으로 바꾸지 않는다.
- `resume`에서 id를 생략하면 가장 최근의 이어 만들 수 있는 대기 프로젝트를 선택한다. 대화에서 id가 알려져 있으면 항상 지정한다. 직접 대본도 Factory에서는 `--review`를 지정했을 때만 멈춘다(기존 웹 UI의 강제 검토는 별도).

## 자료 권리 규칙 (꼭 지킨다, 2026-10-07 transformative_quote 반영)

**원칙: 외부 자료의 직접 재업로드를 기본 동작으로 하지 않는다. 다만 분석·비평·비교·해설 목적의 필요한 인용은
transformative_quote source로 처리할 수 있다. 라이선스, 인용 목적, 사용 범위 및 source 정보를 기록한다.**
재사용 라이선스가 없다는 이유만으로 외부 영상·캡처를 막지 않는다. 원본을 감상하게 하는 것이 아니라 우리 분석을 이해시키는 것이 목적이다.

- 화면 자료 상태: `licensed`(재사용 라이선스·권리 확인) · `public_domain`(CC0·퍼블릭 도메인·NASA 제작) ·
  `transformative_quote`(라이선스는 확인되지 않았지만 비평·분석·비교·해설·뉴스/근황·장면 관찰·사실 검증을 위한 인용 후보) ·
  `reference_only`(사용 제한 표기 등으로 현재 구성에서 화면 사용이 부적절) · `unknown`.
- 사용자가 "이 영상으로 분석 쇼츠 만들어줘", "이 영상 재가공해서 만들어줘", "이 장면들 써서 비교해줘" 라고 하면
  **재사용 라이선스를 묻지 않고** 인용 제작 의도로 처리한다: `make --url "URL" --quote 영상또는캡처 [--quote 캡처2]`.
  출처는 `--url` 에서 자동으로 채운다(제목·채널). URL 없이 파일만 주면 `--quote-source "제목 | 채널 | URL"`.
  참고 영상 파일 자체를 인용하려면 `make --reference-video 파일 --quote-reference`.
- 인용 사용 방식(엔진이 강제): 근거 역할 장면(profile `evidence_roles`)에만 배치, 훅·마지막 질문은 자체 카드,
  필요한 최소 구간만 재생하고 장면 나머지는 정지 화면 + 우리 해설(나레이션·자막), 원본 소리 없음, 화면 하단 `인용: 채널 · 제목`.
  캡처 2장이 비교 장면에 오면 전/후 비교 레이아웃. 같은 원본 구간 반복 금지.
- **고정 초 규칙("3초면 안전")을 만들거나 말하지 않는다.** 엔진의 한도는 상대 비율이다:
  장면 길이의 60%까지 재생 · 완성 영상에서 인용 영상 비중 40% 이하 · 한 원본의 30% 이하 사용 · 인용 장면 75% 이하.
- 렌더 전 `quote.guard` 가 해설 존재·출처 표기·비중·중복·viewer_question 연결을 검사하고, 문제가 있으면 구간을 줄이거나(정지 화면) 카드로 바꾼다. 결과는 `quote_plan.json`.
- **권리 판단과 다운로드 기술 제한은 별개다.** YouTube 는 약관상 자동 다운로드를 하지 않는다(`media_status: not_downloaded_platform_terms`).
  링크 분석(메타데이터·자막·benchmark·viewer_question·근거 구간 타임스탬프)은 그대로 하고, 화면 인용은 사용자가 준 로컬 영상·캡처로 한다.
  링크만 받았고 화면에 원본 장면이 꼭 필요하면 "해당 구간 영상이나 캡처 파일을 주시면 인용으로 넣겠다"고만 안내한다(권리 질문은 하지 않는다).
- Source Resolver(`make` 기본 `--visuals auto`)는 공개 자료를 찾아 상태를 판정한다. profile `source_strategy` 순서로 검토:
  실제 장면이 근거인 구조(K-pop·근황·사건·발언·순위·실험) = licensed → public_domain → transformative_quote → generated → card,
  정보 설명형(mechanism·illustrated) = licensed → public_domain → generated → transformative_quote → card.
  자동 탐색 결과의 인용 후보는 근거 장면이고 장면 주장을 실제로 보여 줄 때(evidence_fit ≥ 7)만 쓴다.
- 처리 순서: discover → inspect → rights classify → 화면 후보(licensed/public_domain/transformative_quote)일 때만 ingest → Clip Analyzer. reference_only·unknown 은 내려받지 않는다.
- 사용자 본인 영상/사진, 직접 만든 자료, AI 생성 이미지, 앱 카드, 공공누리 1유형은 기존처럼 `--asset 파일 --note … --confirm-rights` 로 쓴다.
- 렌더 전 권리 검사(`sources.json`)는 엔진이 강제한다. 우회하지 않는다. `sources.json` 에는 화면에 쓴 자료
  (usage=visual/transformative_quote, rights_status, rights_basis, purpose, attribution{title, channel, url}, scene_ids, clip_ranges, media_status)와
  참고만 한 자료(usage=reference_only/research)가 모두 남는다.
- 결과를 알릴 때: 장면별로 어떤 자료를 어떤 상태(licensed/public_domain/transformative_quote)로 썼는지, 인용 구간과 정지 화면 처리, `quote_plan.json` 의 조정 내용을 쉬운 말로 전한다.
  인용은 법적 판단(공정이용·정당한 인용)을 대신하지 않으므로, 게시 전 사용자가 최종 확인한다는 점도 한 줄로 알린다.

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
- `make` 를 부르는 테스트는 `run.bench_auto.ask_structured` 와 `run.source_resolver.resolve` 도 반드시 가짜로 막는다(`tests/test_factory.py` FactoryTestCase 참고). 막지 않으면 기본 benchmark auto·visuals auto 가 실제 Claude·공개 API 를 호출한다.
- 캐러셀 형식 `make` 테스트는 추가로 `app.carousel.master.ask_structured`·`app.carousel.planner.ask_structured` 를 막는다(`tests/test_carousel.py` CarouselMakeTests 참고).
- 실제 제작(Claude 구독 호출)은 사용자가 요청했거나 렌더 경로가 바뀌어 최소 확인이 필요할 때만 한다. 유료 API 는 사용자 승인 없이 쓰지 않는다.
- 테스트: `.venv\Scripts\python.exe -m unittest tests.test_blueprint tests.test_reference_workflow tests.test_script_split tests.test_sources tests.test_timeline_export tests.test_tts_timeline tests.test_visual_resolver tests.test_factory`
- 전체 테스트: `.venv\Scripts\python.exe -m unittest discover -s tests -q` (V1·Benchmark·Source Resolver·인용 모드·캐러셀·전략 `tests/test_topics.py` 포함 364개). 2026-10-08 기준 364개 통과·skip 0. ffmpeg 가 없는 PC 에서는 실제 ffmpeg 테스트 3개가 skip 된다(`test_quote_mode`, `test_source_resolver` 2개).
- 인용 모드 테스트는 `quote.clip_analyzer.analyze` 도 가짜로 막는다(`tests/test_quote_mode.py` 참고).
- Git 규칙:
  - force push 하지 않는다.
  - 기존 커밋·원격 브랜치를 수정하거나 삭제하지 않는다.
  - 비밀정보는 커밋하지 않는다.
  - push는 사용자가 요청할 때만 한다("저장해줘" 포함, 위 작업 요청 규칙).
- 진행 기록은 `IMPLEMENTATION_PLAN.md`(계획)와 `HANDOFF.md`(작업 인계)에 남긴다.

## Benchmark × V1 자동 통합 (2026-10-05, 기본값)

`make`(topic·url·auto·reference-video)는 **기본으로 `--benchmark auto`** 다. 사용자는 profile 이름을 몰라도 된다.
"○○ 주제로 쇼츠 만들어줘", "이 유튜브 참고해서 만들어줘: URL" → 그냥 `make --topic …` / `make --url …` 를 실행한다.

내부 흐름: 조사 → **Content Brief(AI 1회)**: verified_facts / inference 분리, 시청 질문 후보 2~3개(View Potential 5항목×20점), 8개 profile 9기준 점수
→ **Auto Router**(가중합 0~100 + 게이트: 근거 영상이 필요한 kpop_observation_clip·physics_comparison_simulation·ranked_moments 는 권리 확인 영상이나 사용자가 준 인용 영상(`--quote`)이 없으면 제외, 필수 근거 슬롯 부족 시 제외, 기준 45점 미만이면 `illustrated_fact_explainer` fallback)
→ 선택 profile 에 맞는 보충 조사 1회 → **구조 주입 대본**(장면별 beat_role·시간·글자 예산·훅/결론/마지막 질문, 사실·추론·창작 분리) → 기존 장면 설계 + `apply_scene_plan`(장면 역할·카드 성격·강조 길이) → 기존 Edge TTS·자막·카드·렌더.
기존 구성 분석(`make_plan`)은 benchmark 가 켜지면 건너뛰므로 AI 호출 수는 그대로 3회(brief·대본·장면)다.

- 점수는 **현재 자료로 어떤 구조가 경쟁력 있는지 고르는 내부 판단값**이다. 사용자에게 조회수·성공 확률이라고 말하지 않는다.
- 결과: `project_state.json` 의 `benchmark`(mode, selected_profile, candidate_scores, top3, viewer_question, reason_to_watch, claim, view_potential_score, selection_reason, fallback_used, narration_mode, scene_roles, quality) + 전체 기록 `benchmark_decision.json`(사실·추론·후보·원본 분석). `inspect --part benchmark` 로 본다.
- `resume`·`rerender`·`batch-resume` 은 저장된 결정을 그대로 쓰고 다시 고르지 않는다. 완성 대본(`--script`)은 `not_applicable`, 스타일 지정(`--style`)은 auto 일 때 스타일을 따른다.
- 사용자에게 결과를 알릴 때: 고른 구조 이름, 시청 질문, 선택 이유, 상위 3개 점수, fallback 여부와 quality 경고를 쉬운 말로 전한다.
- 유튜브·기사 URL 은 분석한다(`source_analysis`, 유튜브는 타임스탬프 자막으로 `evidence_moments` 근거 구간까지). 원본 문장·장면 순서를 복제하지 않는다.
  YouTube 미디어는 자동으로 내려받지 않는다. 사용자가 준 영상·캡처는 transformative_quote 로 근거 장면에 인용한다(자료 권리 규칙).
- Source Resolver·Clip Analyzer 는 아래 자료 권리 규칙 참고. 아직 없음: 자동 게시, 채널 크롤링, Global Trend Radar, 조회수 예측, 성과 학습.

| 사용자 말 | 실행 |
|---|---|
| "이 주제로 쇼츠 만들어줘", "영상 자료도 알아서 찾아줘" | `make --topic "…"` (benchmark auto · visuals auto 기본) |
| "카드만으로 만들어줘", "외부 자료 쓰지 마" | `make --topic "…" --visuals cards` |
| "이 유튜브 참고해서 쇼츠 만들어줘: URL" | `make --url "URL"` |
| "비교형/사건 순서형으로 만들어줘" 처럼 구조를 명시 | `make --topic "…" --benchmark <profile id>` (예: event_timeline_story) |
| "예전 방식(구조 선택 없이)으로 만들어줘" | `make --topic "…" --benchmark off` |
| "왜 이 구성으로 만들었어?" | `inspect <id> --part benchmark` |

## 카드뉴스 · 인스타툰 · 하이브리드 (2026-10-07)

`make` 에 출력 형식이 생겼다. `--format shorts`(기본) | `card_news` | `insta_toon` | `hybrid` | `all`.
예전 톤 값(`--format information|story|issue`)도 그대로 받는다(새 이름은 `--tone`).
결과는 `output/<id>/<format>/card_01.png …`(1080x1350 PNG), `manifest.json`(페이지별 타입·문구·이미지·캐릭터·출처·대체 여부),
`sources.json`(이 형식에 쓴 자료), `plan.json`, `master.json`, `caption.txt`(인스타 본문·해시태그·출처).

흐름: 입력 수집(쇼츠와 같은 research/article/youtube 모듈) → **Master Content(AI 1회)** → **Format Planner(AI 1회, 규칙으로 보정)**
→ 카드 사진(쇼츠 Source Resolver 그대로: AI 2회, usable 만) → 만화 컷(업로드 `toon_NN_*` → Bible 참고 이미지 → AI(설정 시) → 앱 마스코트)
→ Pillow 렌더러(글자·말풍선은 전부 앱이 합성). 페이지 하나가 실패해도 대체 레이아웃으로 계속한다.
`hybrid` 비율은 Master 의 story_score 로 자동: 정보형 80/20, 일반 50/50, 스토리형 20/80(카드/만화).
`all` = 쇼츠(기존 엔진 그대로) + 같은 대본으로 하이브리드. 쇼츠가 실패해도 카드는 만든다(`partial_failure`, 쇼츠는 `resume`).

| 사용자 말 | 실행 |
|---|---|
| "이 주제로 카드뉴스 만들어줘" | `make --topic "…" --format card_news` |
| "이 기사로 인스타툰 만들어줘: URL" | `make --url "URL" --format insta_toon` |
| "카드뉴스랑 인스타툰 섞어서 만들어줘", "카드뉴스랑 만화를 섞어서" | `make --topic "…" --format hybrid` |
| "이 원고로 하이브리드 만들어줘" | `make --script "원고" --format hybrid` |
| "쇼츠와 하이브리드 카드뉴스 둘 다", "전부 만들어줘" | `make --topic "…" --format all` |
| "이 조사 자료로 카드뉴스" (JSON) | `make --research-file 파일.json --format card_news` |
| 형식이 애매한 문장 | `make --topic "…" --request "사용자 문장 원문"` (형식 자동 인식, `app/factory/intent.py`) |
| "캐릭터 있는 카드뉴스로" | `make … --format card_news --template character_info` |
| "토리 말고 다른 캐릭터로" | `characters list` → `make … --character <id>` |

- 템플릿: `clean_info`(정보형 카드뉴스 기본), `character_info`(카드에 안내 캐릭터), `comic_hybrid`(인스타툰·하이브리드 기본). `app/carousel/templates/*.yaml` 추가만으로 새 템플릿.
- 캐릭터: `characters/<id>/bible.json`(Character Bible, id 는 ASCII). `characters add --file bible.json`. 기본 `tory_01` 토리.
- 캐릭터 그림 기본은 **무료 마스코트**(앱이 Bible 색으로 직접 그림). `config.yaml` `carousel.image_provider` 를 바꾸면 유료 AI 생성 — 사용자 허락 없이 바꾸지 않는다.
  Flow 등에서 만든 그림을 `--asset toon_03_이름.png --note "Flow 생성" --confirm-rights --license ai_generated` 로 넣으면 그 페이지 첫 컷에 쓴다.
- 캐러셀은 `--review`·`--reference-video` 를 받지 않는다. `resume`·`rerender` 대상이 아니다(다시 `make`). `inspect <id> --part carousel` 로 페이지 요약.
- 결과를 알릴 때: 장수, 카드/만화 비율, 사진을 쓴 페이지와 출처, 대체 레이아웃이 된 페이지(`fallback_pages`)를 전한다.

## Benchmark 인벤토리와 오프라인 경로 (2026-10-05)

benchmark 현황의 기준은 `docs/BENCHMARKS.md` 맨 위 현황판이다(source 6개·profile 8개·상태·실제 검증). 아래는 오프라인 `benchmark plan/render` 경로 규칙이다.
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
| "이 영상으로 kpop_observation_clip 방식으로 만들어줘" | 기본: `make --url "URL" --quote 직캠·캡처 --benchmark kpop_observation_clip` (해설 나레이션 + 인용 구간). 관찰/타임코드 JSON을 직접 준 경우에만 오프라인 plan/render |
| "physics_comparison_simulation 방식으로 제작해줘" | 직접 만든 실험 영상/조건/고정 환경을 확인 → physics 양식 → plan/render; 시뮬레이션 영상 생성은 미지원임을 알려준다 |
| "레스기처럼 순위로 묶어줘" | 채널 복제 대신 ranked_moments, N위부터1위 근거 클립과 순위 기준을 기록 |
| "건축 원리 설명/발언 맥락/숫자 정보/사건 시간 순서" | 각각 mechanism_explainer / quote_context_story / illustrated_fact_explainer / event_timeline_story의 근거 JSON → plan/render |
| "계획만 먼저 보여줘" | plan/inspect 결과를 보여주고 멈춘다 |
| "벤치마크 계속/다시 렌더" | 대화에 알려진 benchmark ID로 `benchmark render ID`; V1 resume를 사용하지 않는다 |

Benchmark 입력 양식은 예시이며 실제 분석/사실이 아니다. 사용자의 사실/영상 입력으로 교체한다. URL(reference)은 provenance 문자열이고 엔진은 접속하지 않는다.
오프라인 `benchmark plan/render` 경로의 이야기 profile은 narration 없는 자체 카드 adapter다(위 V1 자동 통합은 나레이션 포함). 번역/Blender/고급 지도 생성/Global Trend Radar는 아직 없다.
source/profile/코드/문서를 함께 갱신하고 기존 V1 전체 테스트와 Benchmark 회귀 테스트를 실행한다. 테스트/실렌더/흥행 확인을 서로 대신 보고하지 않는다.
