# AI 콘텐츠팩토리 — Codex / Claude Code 공통 작업 규칙

이 파일이 **두 AI 의 공통 규칙 원본**이다. CLAUDE.md 는 이 파일을 가져오고(`@AGENTS.md`) Claude 전용 내용만 둔다. 규칙은 여기만 고친다.
이 프로젝트는 한국어 9:16 유튜브 쇼츠와 인스타그램 캐러셀(카드뉴스·인스타툰)을 만드는 **범용 AI 콘텐츠팩토리**다.
**이 채팅이 메인 화면**이다. 사용자의 자연어 요청을 아래 명령으로 바꿔 실행하고, 결과 JSON을 쉬운 말로 알려준다.
웹 UI(`AI Shorts 실행.cmd` → http://127.0.0.1:8765)는 결과 확인·세부 수정·미리보기용 보조 화면이다.
카드뉴스·인스타툰 스튜디오(`카드뉴스 스튜디오 실행.cmd` → http://127.0.0.1:8765/studio)는 혼자 쓰는 PC 화면: 주제→만들기→카드별 문구 수정·장면 바꾸기→ZIP 저장. 엔진 `app/studio/project.py`(Factory make·carousel 재사용), 화면·경로 `app/studio/{api.py,studio.html}`.
새 대형 기능(Global Trend Radar·Localization·Vision Clip Analyzer·성과 학습·자동 게시)은 사용자의 별도 요청 전에는 시작하지 않는다.

```
Claude Code / Codex (채팅) ─→ app/factory (명령층) ─→ app/pipeline (제작 엔진) ←─ Web UI (보조)
                                            └─→ app/carousel (카드뉴스·인스타툰) · app/topics (주제 전략)
```

## 작업 시작 · 종료 (두 AI 공통, 자동 인수인계)

1. **시작**: `git status --short` → `git log --oneline -5` → `HANDOFF.md` 맨 위 '현재 상태'만 읽는다. 전체 저장소를 다시 훑지 않는다.
2. 다른 세션의 미커밋 변경은 덮어쓰거나 되돌리지 않는다. 같은 파일을 고쳐야 하면 먼저 `git diff <파일>` 로 확인한다.
3. **종료·AI 전환 전**: `HANDOFF.md` 맨 위 '현재 상태'를 갱신한다 — 현재 작업 / 완료 / 남은 작업 / 수정 파일 / 테스트 결과 / 다음 작업 / 주의.
   '현재 상태'는 80줄 이내로 유지하고, 끝난 기록은 `docs/history/` 로 옮긴다(지우지 않는다).
4. 위험한 파일 삭제, 대규모 구조 변경, 사용자 데이터(output·reference·samples) 정리, commit/push 는 사용자 승인 후에만.

## 개발 원칙 (기능 추가·수정마다)

기존 코드 확인 → 최대한 재사용 → 중복 방지 → 불필요한 코드 정리 → 테스트 → HANDOFF.md 갱신.
- 새 함수를 쓰기 전에 `rg "def 이름|비슷한 단어" app` 로 같은 기능이 있는지 찾는다. 공통 도구: 글꼴 `app/pipeline/fonts.py`,
  글자 맞춤 `app/pipeline/cards.py`(wrap_to_width·fit_text), LLM `app/pipeline/llm.ask_structured`, 권리 대장 `app/pipeline/sources.SourceRegistry`.
- 안 쓰는 코드는 참조(`rg -w 이름 app scripts tests app/static app/templates`)를 확인한 뒤 지운다. 줄 수보다 실행 안정성과 유지보수성이 먼저다.

## 토큰 절약

- 필요한 파일만 `rg` 로 찾아 해당 부분만 읽는다. 큰 문서(HANDOFF 기록, docs/history, docs/AGENT_REFERENCE.md)는 필요할 때만 연다.
- 출력은 결과 요약 위주로 짧게. 긴 로그·파일 전체 출력·같은 설명 반복을 하지 않는다.
- 이미 끝난 작업·테스트를 같은 코드 상태에서 반복하지 않는다. 코드를 바꿨으면 관련 테스트는 반드시 다시 돈다(커밋 전에는 전체 테스트).

## 명령 (프로젝트 폴더에서, 가상환경 파이썬으로)

`.venv\Scripts\python.exe -m app.factory <명령>` 을 실행한다. 결과는 stdout JSON 한 덩어리이고, 진행 로그는 stderr로 나온다.
현재 Codex 환경에서는 `./scripts/factory.ps1 <명령>`을 쓴다. 깨진 기존 `.venv`는 보존하고,
저장소 밖 `../.codex-envs/ai-shorts-py312`의 Python 3.12가 기존 패키지를 재사용한다.
래퍼는 정상 `.venv` → 복구 환경 → 제공된 Python 순으로 선택하고 `.pth`를 처리하며, 로컬 FFmpeg 경로는 실행 중에만 추가한다.
복구 환경은 기존 `.venv/Lib/site-packages`에 의존하므로 이를 삭제하지 않는다. CLI import 성공은 Claude 로그인·실제 제작 검증과 구분한다.
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
| `characters [list\|show ID\|add --file\|import\|generate\|approve]` | 캐릭터 목록·등록·그림 가져오기·생성 견적·포즈 승인. generate는 `--confirm-cost` 없으면 API 미호출 |
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
| `toon --topic "…" --facts-from-topic <topic_id> [--writer rules\|claude]` | 자동 인스타툰 8장 (훅→상황→상대역→갈등→정보 발견→해결·반전→결론). 기본 rules 무료, claude 는 선택 |
| `topics collect\|rank\|recommend\|calendar\|approve\|plan\|create …` | 주제 수집·검증·추천·캘린더 (상세 `docs/TOPIC_STRATEGY.md`) |
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
- 전체 테스트: `.venv\Scripts\python.exe -m unittest discover -s tests -q` (Codex 환경은 `scripts/factory.ps1` 과 같은 Python). 2026-10-16 기준 390개. ffmpeg 가 없는 환경에서는 실제 FFmpeg 테스트 3개가 skip 된다. 최신 결과는 `HANDOFF.md` 맨 위.
- 인용 모드 테스트는 `quote.clip_analyzer.analyze` 도 가짜로 막는다(`tests/test_quote_mode.py` 참고).
- Git 규칙:
  - force push 하지 않는다.
  - 기존 커밋·원격 브랜치를 수정하거나 삭제하지 않는다.
  - 비밀정보는 커밋하지 않는다.
  - push는 사용자가 요청할 때만 한다("저장해줘" 포함, 위 작업 요청 규칙).
- 진행 기록: `HANDOFF.md`(현재 상태, 위 인수인계 규칙) · 진행 중 계획 `docs/OPTIMIZATION_PLAN_2026-10-14.md` · 지난 기록·옛 계획 `docs/history/`.

## 주제 전략 (Topic Strategy V1)

상세 CLI·검증 조건·원문/승인 보존은 `docs/TOPIC_STRATEGY.md`. 발행 API는 없고 `topics published`는 사람이 게시한 이력 기록이다.
번호 선택은 결과의 `selection_id`를 유지한다. `topics rank --ai` 외에는 전략 평가에 LLM을 호출하지 않는다.
개발 검증은 `tests/test_topics.py`; 실제 뉴스/Claude/API/PNG 샘플은 사용자 요청 없이 반복하지 않는다.

## Benchmark × V1 자동 통합 (기본값)

`make`(topic·url·auto·reference-video)는 **기본으로 `--benchmark auto`** 다. 사용자는 profile 이름을 몰라도 된다. 내부 흐름·결과 필드는 `docs/AGENT_REFERENCE.md`.
점수는 **현재 자료로 어떤 구조가 경쟁력 있는지 고르는 내부 판단값**이다. 사용자에게 조회수·성공 확률이라고 말하지 않는다.
`resume`·`rerender`·`batch-resume` 은 저장된 결정을 그대로 쓴다. 결과를 알릴 때: 고른 구조 이름, 시청 질문, 선택 이유, 상위 3개 점수, fallback 여부와 quality 경고.

| 사용자 말 | 실행 |
|---|---|
| "이 주제로 쇼츠 만들어줘", "영상 자료도 알아서 찾아줘" | `make --topic "…"` (benchmark auto · visuals auto 기본) |
| "카드만으로 만들어줘", "외부 자료 쓰지 마" | `make --topic "…" --visuals cards` |
| "이 유튜브 참고해서 쇼츠 만들어줘: URL" | `make --url "URL"` |
| "비교형/사건 순서형으로 만들어줘" 처럼 구조를 명시 | `make --topic "…" --benchmark <profile id>` (예: event_timeline_story) |
| "예전 방식(구조 선택 없이)으로 만들어줘" | `make --topic "…" --benchmark off` |
| "왜 이 구성으로 만들었어?" | `inspect <id> --part benchmark` |

벤치마킹 분석·오프라인 `benchmark plan/render` 경로 규칙은 `docs/AGENT_REFERENCE.md` 와 `docs/BENCHMARKS.md`(현황판 기준).

## 카드뉴스 · 인스타툰 · 하이브리드

`make --format shorts`(기본) | `card_news` | `insta_toon` | `hybrid` | `all`. 결과 `output/<id>/<format>/card_NN.png`(1080x1350) + `manifest.json`·`sources.json`·`caption.txt`.
내부 흐름·템플릿·캐릭터 세부는 `docs/AGENT_REFERENCE.md`. 품질 기준 샘플은 `samples/`.

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

- 기본(브랜드) 캐릭터는 햄토리치 `hamtorich_01`(최상위 기준 `characters/hamtorich_01/master/design_sheet.png`, 규칙 `characters/hamtorich_01/README.md`). 토리 `tory_01` 은 선택.
- 무료가 기본: 등록 포즈 + 코드로 그린 장면 11종 + 효과. 사용자 그림은 `assets/inbox/`(자동 등록). `carousel.image_provider`·`characters generate --confirm-cost` 같은 유료 생성은 사용자 허락 없이 쓰지 않는다.
- 자동 인스타툰 `toon`: 수치는 verified fact 원문만, 검증 실패 초안은 `status: rejected`(PNG 없음). `--writer claude` 는 사용자가 고를 때만(구독 CLI).
- 캐러셀은 `--review`·`--reference-video` 를 받지 않고 `resume`·`rerender` 대상이 아니다(다시 `make`). 결과를 알릴 때: 장수, 카드/만화 비율, 사진 출처, `fallback_pages`.
