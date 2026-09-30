# AI 콘텐츠팩토리 — Codex / Claude Code 공통 작업 규칙

이 프로젝트는 한국어 9:16 유튜브 쇼츠를 만드는 **범용 AI 콘텐츠팩토리**다.
**이 채팅이 메인 화면**이다. Codex와 Claude Code는 사용자의 자연어 요청을 아래 명령으로 바꿔 실행하고, 결과 JSON을 쉬운 말로 알려준다.
웹 UI(`AI Shorts 실행.cmd` → http://127.0.0.1:8765)는 결과 확인·세부 수정·미리보기용 보조 화면이다.

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
| `make ... --review` | **대본까지만** 만들고 승인 대기로 멈춤 |
| `make ... --style "이름"` / `--preset daily` | 스타일·분야 기본값 지정 (`styles`로 목록 확인) |
| `make ... --asset 파일 --note "근거" --confirm-rights` | 내가 권리를 가진 사진·영상을 장면 화면 후보로 |
| `resume [id]` | 멈춘/실패한 프로젝트를 저장된 대본으로 이어서 MP4까지 (조사·대본 다시 안 함) |
| `status [id]` | 진행 상태 (id 생략 = 가장 최근 프로젝트 + 최근 목록) |
| `inspect [id] --part script\|scenes\|visuals\|files\|all` | 대본·장면 시간·화면 선택 이유·파일 |
| `edit-scene [id] --scene 3 --narration "…" --emphasis "…"` | 렌더 전 장면 문장/강조문구 수정 |
| `set-visual [id] --scene 3 --card number_card` | 렌더 후 장면 화면을 카드로 바꾸고 다시 렌더 |
| `set-visual [id] --scene 3 --file 사진 --note "근거" --confirm-rights` | 장면 화면을 권리 확인된 사진으로 |
| `rerender [id]` | 저장된 재료로 영상만 다시 렌더 (조사·대본·음성 다시 안 함) |
| `styles` / `trends` | 스타일·프리셋 목록 / 화제 키워드 |
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
- 테스트: `.venv\Scripts\python.exe -m unittest tests.test_blueprint tests.test_reference_workflow tests.test_script_split tests.test_sources tests.test_timeline_export tests.test_tts_timeline tests.test_visual_resolver tests.test_factory`
- Git 규칙:
  - force push 하지 않는다.
  - 기존 커밋·원격 브랜치를 수정하거나 삭제하지 않는다.
  - 비밀정보는 커밋하지 않는다.
  - push는 사용자가 요청할 때만 한다.
- 진행 기록은 `IMPLEMENTATION_PLAN.md`(계획)와 `HANDOFF.md`(작업 인계)에 남긴다.
