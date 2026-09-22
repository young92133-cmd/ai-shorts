# HANDOFF — 개발 인수인계 문서

> 이 문서만 읽고 바로 작업을 이어갈 수 있도록 쓴 **개발자/AI용** 문서입니다.
> 사용자용 사용법은 [`README.md`](README.md)에 있습니다. 중복되는 내용은 그쪽을 참고하세요.
>
> **최종 갱신: 2026-09-22** · 작성 시점의 실제 파일 상태와 대조 완료 (문서 맨 아래 «정합성 확인» 참고)

---

## 1. 이 프로젝트는 무엇인가

**한국어 유튜브 쇼츠(9:16 세로 영상) 자동 생성기.** 개인용, 로컬 실행, 웹 UI.

```
입력 ──┬─ 주제 한 줄
       ├─ 링크 (유튜브 / 뉴스 기사 / 커뮤니티 글, 여러 개 가능)
       └─ 핫이슈 자동 (Google Trends KR)
                    ↓
     리서치 → 구성 설계 → 대본 → TTS 나레이션 → 비주얼 → ffmpeg 렌더
                    ↓
     output/<잡ID>/final.mp4  +  meta.txt (제목 3안·설명·해시태그·출처)
```

**핵심 목표**: 채널 운영에 실제로 쓸 수 있을 것. 그래서 ①벤치마킹 채널 스타일 모방,
②링크 하나로 끝내기, ③카테고리별 편집 방식 분기, ④비용 최소화가 설계의 축이다.

유튜브 업로드는 하지 않는다 (사용자 요청). mp4와 업로드용 텍스트만 만든다.

---

## 2. 빠른 시작

```bash
cd shorts-ai
.venv\Scripts\activate
uvicorn app.main:app --port 8765
```

→ http://localhost:8765

**Claude 로그인(최초 1회, 필수)** — 대본 생성에 Claude Pro 구독을 쓴다. API 키가 아니다.

```
claude-login.cmd  (탐색기에서 더블클릭)
```
브라우저가 열리면 로그인 → Authorize → 표시된 코드를 검은 창에 우클릭 붙여넣기 → Enter.
`"loggedIn": true` 가 나오면 성공. 상태 확인은 `python -m app.pipeline.llm status`.

`.env`는 **없어도 동작한다.** 없으면 이미지 AI 생성과 비전 분석만 비활성화된다.

---

## 3. 완료된 작업 (Phase A~E)

**⚠ 검증 상태 열을 반드시 확인할 것.** "코드만"은 실제로 실행해 본 적이 없다는 뜻이다.

| Phase | 내용 | 검증 상태 |
|---|---|---|
| **초기** | 주제 → 리서치 → 대본 → TTS → 이미지 → mp4 기본 파이프라인, 웹 UI, 잡 큐/SSE | ✅ **실제 실행** — 55초 mp4 2편 생성, 자막 싱크·렌더 확인 |
| **A** 스타일 지침 | 참고 영상 URL → 자막 분석 → 스타일 지침 자동 추출·저장·적용 | ✅ **실제 실행** — 건축 채널 2편 분석, 스타일 적용/미적용 대본 차이 확인 |
| **B** 링크 분석 | 유튜브가 아닌 링크를 기사 모드로 분기, 본문+이미지 수집, 출처 자동 표기 | ⚠️ **로직 점검만** — 가짜 HTML로 파서 검증. 실제 기사 URL 미투입 |
| **C** 파일 첨부 | 업로드(토큰 staging), Gemini 비전으로 내용 파악 후 장면 매칭 | ⚠️ **부분** — 업로드 API는 브라우저에서 실제 확인. 비전 매칭은 키가 없어 미검증 |
| **D** Gemini 이미지 | Nano Banana 2 3종 provider, UI 실시간 비용 표시 | ❌ **코드만** — API 호출 0회 |
| **E** 영상 짜깁기 | 소스 자동검색/링크 지정 → 장면별 구간 매칭 → 원본 소리 덕킹 + 나레이션 | ❌ **코드만** — `render_broll` 실제 렌더 0회 |
| **E** Flow 워크플로 | 이미지 프롬프트 복사 → Flow에서 무료 생성 → 장면별 업로드 | ⚠️ **UI만** — DOM 렌더·복사 텍스트 조립 확인. 전체 흐름 미검증 |

**Phase F (Omni Flash 영상 생성)는 착수하지 않았다.**

---

## 4. 파일 구조와 각 파일의 역할

`■` = 이번 확장에서 **신규 작성**, `▲` = 기존 파일 **수정**

### 파이프라인 (`app/pipeline/`)

| 파일 | 줄수 | 역할 |
|---|---|---|
| `run.py` ▲ | 444 | **오케스트레이터.** 6단계 전부를 조율. CLI 겸용. 가장 큰 파일이자 변경이 집중된 곳 |
| `models.py` ▲ | 122 | 모든 pydantic 모델. LLM 구조화 출력 스키마 겸용 |
| `script.py` ▲ | 129 | Claude 프롬프트 4종: 구성설계(`make_plan`)·대본(`write_script`)·클립계획·트렌드선택 |
| `llm.py` ▲ | 178 | LLM provider 3종 (claude 구독 / openai / anthropic). `claude.exe` 자동 탐색 |
| `styles.py` ■ | 153 | 스타일 지침 CRUD + 참고 영상 자동 분석 |
| `article.py` ■ | 192 | 기사·글 링크 본문 추출 + 이미지 수집 + 출처 문구 |
| `assets.py` ■ | 172 | 첨부 파일 관리 + **장면별 비주얼 우선순위 결정** |
| `vision.py` ■ | 96 | Gemini Flash 비전으로 이미지 내용 파악 → 장면 매칭 |
| `broll.py` ■ | 180 | 소스 영상 검색·수집, 자막 타임라인, 장면별 구간 매칭·정규화 |
| `render.py` ▲ | 261 | ffmpeg 3종: `render_slideshow` / `render_clips` / `render_broll`(신규) |
| `subtitles.py` ▲ | 99 | ASS 자막 생성. `Sub`(카라오케)·`Title`(키워드)·`Credit`(출처, 신규) |
| `media.py` ▲ | 106 | ffmpeg 유틸. `extract_frames`·`has_audio` 신규, ffmpeg 경로 자동 탐색 |
| `youtube.py` ▲ | 138 | yt-dlp 메타·자막(단어 타임스탬프)·다운로드, whisper 대체 |
| `research.py` | 110 | 뉴스 검색(네이버/DDG) + 본문 추출, Google Trends KR |
| `clips.py` | 37 | 클립 모드 구간 정규화·자막 리타이밍 |

### Provider 어댑터

| 폴더 | 파일 | 비고 |
|---|---|---|
| `images/` | `base.py`, `gemini.py` ■, `fal.py`, `huggingface.py`, `openai_img.py`, `pollinations.py` | `__init__.get_images()`가 분기. **`none`이면 `None` 반환** |
| `tts/` | `base.py`, `edge.py`, `openai_tts.py`, `elevenlabs.py`, `typecast.py` | 기본 `edge`(무료, 단어 타임스탬프 제공) |

### 웹

| 파일 | 줄수 | 역할 |
|---|---|---|
| `app/main.py` ▲ | 242 | FastAPI. 라우트 18개 + SSE |
| `app/jobs.py` ▲ | 184 | 잡 큐(순차 1개씩), 대본 검토 대기, 상태 영속화, 업로드 이동 |
| `app/config.py` ▲ | 86 | config/preset/style 로딩, `merge_options` 우선순위 |
| `app/templates/index.html` ▲ | 292 | 단일 페이지 |
| `app/static/app.js` ▲ | 513 | 전체 UI 로직 (빌드 없음) |
| `app/static/style.css` ▲ | 131 | 다크 테마, 모바일 대응 |

### 설정·데이터

```
config.yaml           기본 provider·해상도·길이·볼륨
presets/*.yaml        카테고리 4종 (daily/engineering/entertainment/politics)
styles/*.yaml         저장된 스타일 지침 (현재 1개: style-f8b83e20)
assets/bgm/           mp3 넣으면 자동 사용 (현재 비어 있음)
assets/fonts/         otf/ttf (현재 비어 있음, 맑은 고딕 사용 중)
output/<잡ID>/        결과물 (현재 비어 있음)
claude-login.cmd      Claude CLI 로그인 헬퍼
```

---

## 5. 아키텍처 핵심

### 파이프라인 6단계 (`run.py: run_pipeline`)

```
1 리서치/입력분석  → mode별 분기 (topic / url→유튜브·기사 / auto)
2 구성 설계        → 스타일 없으면 AutoPlan 으로 구성·장면수·visual_mode 자동 결정
3 대본            → Script (장면별 나레이션·이미지프롬프트·화면키워드 + 제목/설명/태그)
     ↕ review 콜백으로 여기서 멈추고 사용자 수정 대기 가능
4 TTS             → 장면별 합성 후 이어붙임, 단어 타임스탬프 확보
5 비주얼          → broll 분기 / 첨부·기사·생성·카드 우선순위 해결
6 자막 + 렌더      → ASS 생성 후 ffmpeg
```

### 지침 3계층 — 아래로 갈수록 우선

```
프리셋(presets/*.yaml)  <  스타일(styles/*.yaml)  <  이번 영상 지침(job options)
   카테고리 기본 규칙        벤치마킹 채널 구성·말투        1회성 요청
```
`script.py`의 `_preset_block` → `_style_block` → `_autoplan_block` → `_instructions_block`
순서로 프롬프트에 쌓이고, 뒤쪽 블록이 "충돌하면 이것을 따르라"고 명시한다.

### 비주얼 우선순위 (`assets.resolve_visuals` → `run._prepare_visuals`)

```
0. broll 구간       (visual_mode=broll 일 때만)
1. 첨부 파일        파일명 scene_NN_* 이면 그 장면에 고정, 아니면 비전으로 매칭
2. 기사 수집 이미지  출처 자동 표기
3. AI 생성          provider가 none이 아닐 때만
4. 단색 카드        위가 전부 실패해도 영상은 반드시 완성
```

### visual_mode 3종

| 값 | 동작 | 기본 적용 |
|---|---|---|
| `images` | 정지 이미지 슬라이드쇼(켄번즈+xfade) + TTS | daily, engineering |
| `broll` | 여러 소스 영상 구간 짜깁기 + TTS 오버레이 | entertainment, politics |
| `clip` | 원본 영상 하이라이트 그대로 | UI의 "원본 클립 재편집" 체크 시 |

### LLM provider 3종 (`llm.py`)

| 값 | 인증 | 비용 |
|---|---|---|
| `claude` (기본) | `claude.exe` 구독 로그인 | **0원** (구독 한도) |
| `openai` | `OPENAI_API_KEY` | 종량제 |
| `anthropic` | `ANTHROPIC_API_KEY` | 종량제 |

`claude` 경로는 `claude-agent-sdk`로 `claude.exe`를 서브프로세스 실행한다.
**주의**: 이 프로그램이 Claude Code 세션 안에서 돌 때 상속되는 `CLAUDE_CODE_*` 환경변수를
`llm.py`에서 비워서 넘긴다. 이걸 지우면 중첩 실행이 꼬인다.

---

## 6. 현재 막혀 있는 것 / 미검증 — **가장 중요**

### 6.1 대부분이 실행된 적 없다

사용자와 **"개발 중에는 샘플 생성·유료 API 호출 금지, 다 만든 뒤 한 번에 테스트"** 로 합의했다.
그래서 Phase B~E는 다음만 통과한 상태다:

- `python -m compileall app` 통과
- import·FastAPI 라우트 등록 확인
- **가짜 데이터로 순수 로직 검증** (HTML 파서, 우선순위 배치, 구간 정규화, 파일명 규칙)
- ffmpeg를 가짜 함수로 바꿔 **필터그래프 인자만** 검사
- 브라우저에서 DOM 렌더·이벤트 확인 (잡 생성 없이)

### 6.2 가장 위험한 미검증 지점

| 위험도 | 항목 | 이유 |
|---|---|---|
| 🔴 높음 | **`render_broll()` 실제 렌더** | ffmpeg 필터그래프가 길고 복잡하다. `tpad`+`trim` 길이 맞춤, 여러 입력 dedupe, `anullsrc` 무음 삽입, `amix` 3입력이 전부 미실행. 문법 오류 하나면 전체가 죽는다 |
| 🔴 높음 | **broll 전체 흐름** | yt-dlp 검색 → 자막 → 매칭 → 720p 다운로드까지 외부 의존이 4단계 |
| 🟡 중간 | **Gemini 이미지·비전** | `.env` 없어 한 번도 호출 못 함. 응답 파싱은 가짜 JSON으로만 확인 |
| 🟡 중간 | **기사 이미지 수집** | 실제 뉴스 사이트는 지연로딩·CDN·referer 검사가 제각각. 가짜 HTML만 통과 |
| 🟢 낮음 | 첨부 비전 매칭 | 키 없으면 "올린 순서대로" 경로로 자동 강등되므로 최악에도 동작 |

### 6.3 환경 상태

- **`.env` 없음.** `GEMINI_API_KEY`, `FAL_KEY`, `OPENAI_API_KEY`, `NAVER_CLIENT_ID/SECRET` 전부 미설정
- Claude 구독 로그인은 **되어 있음** (`loggedIn: true`, Pro)
- Python 3.12.10 / ffmpeg 9.0.1 (winget 설치, `media.py`가 경로를 자동으로 찾음)
- `output/` 비어 있음, `styles/`에 1개

---

## 7. 알려진 버그 · 주의사항

### 해결됨 (재발 방지 필요)

| 버그 | 원인 | 조치 |
|---|---|---|
| 스타일 조회 실패 | `slugify`가 `NFKD`로 한글 자모 분해 | id를 **ASCII 전용**(`style-<md5 8자>`)으로. 한글은 `name` 필드에만 |
| 스타일 중복 표시 | 한글 id 구본 파일이 남아 둘 다 로드됨 | 파일 삭제 + `load_styles()`가 비ASCII id를 건너뛰고 경고 |
| `scene_03_flow.png` 인식 실패 | 정규식 `\b` 사용 — 숫자와 `_`가 둘 다 단어문자라 경계 없음 | `(?!\d)`로 교체. **Flow 워크플로 전체가 죽는 버그였음** |
| 참고 영상 자막 덮어쓰기 | 여러 영상을 같은 폴더에 받아 `source.ko.json3` 충돌 | 영상별 `ref{n}/`·`src{n}/` 하위 폴더 |
| 유튜브 자막 HTTP 429 | 연속 요청 | `sleep_interval_subtitles`+재시도 3회+백오프, 소스는 순차 수집 |
| ffmpeg 못 찾음 | 새 프로세스에 PATH 미반영 | `media.require_ffmpeg()`이 winget 설치 경로를 직접 탐색 |

### 미해결 / 제약

- **UI에서 `visual_mode`를 직접 고를 수 없다.** 프리셋 값 또는 "원본 클립 재편집" 체크박스로만 결정된다.
  `run_pipeline(visual_mode=)` 인자와 CLI `--visual`은 있으므로, UI 드롭다운만 추가하면 된다
- **검토 화면에 비주얼 미리보기가 없다.** 장면별 업로드(`＋`)는 되지만 무엇이 배치될지 보이지 않는다
- **`typecast.py`의 API 스펙 미확인.** 문서 기준으로 작성했고 호출해 본 적 없다
- **Pollinations 무료 티어는 저화질+워터마크.** 모델을 바꿔도 같은 이미지가 나온다(실측). 최후 수단
- **잡은 순차 1개씩** 처리된다. 동시 실행 불가
- 서버 재시작 시 진행 중이던 잡은 `error`로 표시된다 (`jobs.py:_load_from_disk`)

---

## 8. 다음에 할 일 (우선순위 순서)

### 1️⃣ 키 없이 되는 경로부터 실검증 — **여기부터 시작**

비용이 들지 않고 가장 많은 코드를 지나간다.

```bash
# 대본까지만 (Claude 구독만 사용, 0원)
python -m app.pipeline.run --topic "엘리베이터 안전장치" --preset engineering --until script

# 전체 (이미지는 provider=none 이므로 단색 카드로 렌더됨)
python -m app.pipeline.run --topic "엘리베이터 안전장치" --preset engineering
```
확인할 것: 6단계 전부 통과 / `output/<잡>/final.mp4` 생성 / `ffprobe`로 1080x1920·길이 /
프레임 추출로 자막 싱크.

그다음 웹 UI에서 **Flow 워크플로 전체**: 대본 검토 → 프롬프트 복사 → Flow에서 이미지 생성 →
장면별 `＋` 업로드 → 렌더. `scene_NN_*` 파일명 고정 배치가 실제로 되는지가 핵심.

### 2️⃣ `render_broll` 실제 렌더 1회 — **가장 위험한 미검증**

전체 broll 흐름을 돌리기 전에, **필터그래프만 따로** 검증하는 게 안전하다.
로컬 mp4 2개를 만들어 `clips` 배열을 손으로 구성하고 `render_broll()`을 직접 호출할 것.
(영상·이미지 혼합, 오디오 없는 소스 포함)

실패하면 `tpad`/`trim` 길이 맞춤과 `amix` 부분을 먼저 의심할 것.

### 3️⃣ 기사 링크 모드 실검증

네이버뉴스·연합뉴스 URL을 실제로 투입. 본문 추출·이미지 수집 개수 확인,
프레임 추출로 하단 `출처: ...` 크레딧이 보이는지 확인.

### 4️⃣ Gemini 경로 (사용자가 키를 넣은 뒤에만)

```bash
python -m app.pipeline.images.gemini "test prompt" lite   # 1장 ≈ 50원
```
성공하면 비전 매칭(`vision.describe_image`)도 확인.

### 5️⃣ Phase F — Omni Flash 영상 생성

`gemini-omni-1.1-flash`, 3~10초 클립, **초당 약 145원**. 비용이 커서 장면 단위 opt-in 필수.
`SceneVisual(kind="generated_video")`를 추가하고 `render_slideshow`가 영상 세그먼트를 받게 확장.

### 6️⃣ UI 개선

- `visual_mode` 드롭다운
- 검토 화면 장면별 비주얼 미리보기 + 교체
- 잡 취소 버튼

---

## 9. 사용자가 요청한 조건 — 반드시 지킬 것

1. **개발 중에는 샘플 영상·대본을 만들지 않는다.** 유료 API 호출과 Claude 구독을 쓰는 실행 금지.
   코드와 UI를 다 만든 뒤 사용자 신호를 받고 테스트한다.
   *허용*: import·문법·라우트 확인, 가짜 데이터 로직 테스트, 브라우저 DOM 확인(잡 생성 없이)
2. **이미지 비용 0원이 기본.** `images.provider: none` + Flow에서 만든 이미지 첨부.
   유료 provider는 UI에서 명시적으로 골라야만 쓰인다
3. **영상 짜깁기는 원본 소리를 12%로 깔고 나레이션을 위에** 얹는다 (완전 음소거 아님)
4. **대본은 Claude 구독 로그인 사용.** API 키를 요구하지 않는다
5. **유튜브 자동 업로드는 하지 않는다.** mp4 + 메타 텍스트까지만
6. 지침은 3계층으로 분리해 각각 저장·재사용할 수 있어야 한다
7. 웹 UI로 혼자 쓰는 도구. 복잡한 빌드 체인 없이

---

## 10. 건드리면 안 되는 것

| 대상 | 이유 |
|---|---|
| **스타일 id의 ASCII 규칙** (`styles.slugify`) | 한글 파일명은 Windows/OneDrive NFC/NFD 불일치로 조회 실패·중복을 일으킨다. 실제로 겪은 버그 |
| **`_prepare_visuals`의 fallback 체인** | "무슨 일이 있어도 영상은 완성된다"가 설계 원칙. 각 단계 실패 시 다음으로 강등되는 구조를 깨지 말 것 |
| **저작권 장치** | 출처 자동 표기(ASS `Credit`), 소스당 길이 상한, UI 경고 문구. 법적 리스크 완화 장치이므로 임의로 제거 금지 |
| **`youtube.py`의 자막 재시도·백오프** | 없애면 429로 바로 실패한다 |
| **영상별 하위 폴더 분리** (`ref{n}/`, `src{n}/`) | 같은 폴더에 받으면 자막 파일명이 충돌한다 |
| **`llm.py`의 `CLAUDE_CODE_*` 환경변수 제거** | Claude Code 안에서 실행될 때 중첩 세션이 꼬인다 |
| **정치·연예 프리셋의 사실기반·중립 규칙** | 명예훼손·허위정보 리스크 |
| `.venv/`, `output/`, `.env` | 각각 의존성, 결과물, 비밀값 |

---

## 11. 실행 · 테스트 방법

### 웹

```bash
uvicorn app.main:app --port 8765
```

### CLI (단계별 실행 가능 — 디버깅에 유용)

```bash
python -m app.pipeline.run --topic "..." --preset engineering --until script
python -m app.pipeline.run --url "https://n.news.naver.com/article/..."
python -m app.pipeline.run --auto --preset entertainment
python -m app.pipeline.run --topic "..." --style style-f8b83e20
python -m app.pipeline.run --topic "..." --uploads "C:\내사진폴더"
python -m app.pipeline.run --topic "..." --visual broll
```

`--until` 값: `research` | `script` | `tts` | `images` | `render` | `done`

### 보조 명령

```bash
python -m app.pipeline.llm status                      # Claude 로그인 상태
python -m app.pipeline.llm login                       # 로그인
python -m app.pipeline.llm test                        # 구조화 출력 스모크 테스트
python -m app.pipeline.styles list                     # 저장된 스타일
python -m app.pipeline.styles analyze <URL> <URL>      # 참고 영상 → 스타일 추출
python -m app.pipeline.images.gemini "prompt" lite     # 이미지 1장 (≈50원 과금)
```

### 무과금 점검 (개발 중 권장)

```bash
python -m compileall -q app          # 문법
python -c "import sys; sys.path.insert(0,'.'); import app.main"   # import·라우트
```

ffmpeg를 실제로 돌리지 않고 필터그래프만 보려면 `render.run_ffmpeg`를 가짜 async 함수로
교체한 뒤 호출해 `-filter_complex` 인자를 확인하는 방식을 쓴다 (Phase E에서 이 방식으로 검증했다).

### API 엔드포인트 (18개 / 고유 경로 13개 + 웹 UI `GET /`)

```
GET     /                                    웹 UI

GET     /api/presets
PUT     /api/presets/{preset_id}

GET     /api/styles
POST    /api/styles
PUT     /api/styles/{style_id}
DELETE  /api/styles/{style_id}
POST    /api/styles/analyze                  참고 영상 분석 (1~3분 소요)

POST    /api/uploads                         잡 생성 전 임시 보관 (token 기준)
GET     /api/uploads/{token}
DELETE  /api/uploads/{token}                 ?name= 주면 파일 1개만 삭제

GET     /api/jobs
POST    /api/jobs
GET     /api/jobs/{job_id}
DELETE  /api/jobs/{job_id}
POST    /api/jobs/{job_id}/approve           대본 확정 → 렌더 진행
POST    /api/jobs/{job_id}/scene-visual      장면별 파일 지정 (scene_NN_* 로 저장)
GET     /api/jobs/{job_id}/events            SSE 진행상황

GET     /files/{job_id}/{name}               결과물 (final.mp4, meta.txt 등)
```

### 편당 비용

| 구성 | 비용 |
|---|---|
| Claude 구독 대본 + Edge TTS + `provider: none` + broll | **0원** |
| fal.ai FLUX 이미지 8장 | 약 32원 |
| Nano Banana 2 Lite 8장 | 약 390원 |
| Nano Banana 2 8장 | 약 780원 |
| Omni Flash 영상 5초 (Phase F) | 약 725원 |

> Google Flow/Gemini 앱 이미지는 구독에 포함되지만, **Gemini API 이미지 모델은 무료 티어가 없다**
> (공식 pricing·rate-limits 문서에서 확인). 구독이 API 접근을 주지 않는다.

---

## 12. 정합성 확인

이 문서 작성 시점(2026-09-22)에 실제 파일 상태와 대조한 결과:

| 항목 | 문서 | 실제 | |
|---|---|---|---|
| 소스 파일 수 | 47개 (HANDOFF 제외) | 47개 | ✅ |
| `app/` 코드량 | 36파일 5,200줄 (.py 4,182줄) | 동일 | ✅ |
| API 엔드포인트 | 18개 (+ `GET /`) | 18개 | ✅ |
| 라우트 경로·파라미터명 | `{job_id}`/`{preset_id}`/`{style_id}`/`{token}` | 동일 | ✅ |
| `images.provider` | `none` | `none` (`get_images()`→`None`) | ✅ |
| `llm.provider` / model | `claude` / `claude-opus-5` | 동일 | ✅ |
| 프리셋 visual_mode | daily·engineering=images, entertainment·politics=broll | 동일 | ✅ |
| broll 설정 | 볼륨 0.12 / 소스 4개 / 소스당 15초 | 동일 | ✅ |
| 스타일 | 1개 (`style-f8b83e20`) | 1개 | ✅ |
| `output/` | 비어 있음 | 비어 있음 | ✅ |
| `.env` | 없음 | 없음 | ✅ |
| `compileall` | 통과 | 통과 | ✅ |

**문서 작성 중 고친 것**

*코드/데이터*
1. `styles/`에 한글 id 구본이 남아 UI 드롭다운에 같은 스타일이 두 번 뜨던 문제 →
   파일 삭제 + `load_styles()`가 비ASCII id를 건너뛰며 경고하도록 수정 (`styles.py`)
2. `output/`의 개발용 테스트 잡 2개 삭제

*문서 자체 (대조 스크립트로 잡아낸 오류)*
3. 소스 파일 수를 34개로 잘못 적었던 것 → 47개로 정정
4. API 라우트 경로를 `{id}`로 축약해 적었던 것 → 실제 파라미터명(`{job_id}` 등)으로 정정.
   "라우트 18개"의 의미도 *엔드포인트(메서드+경로) 18개*로 명확히 함

> 대조는 스크립트로 자동 수행했다. 같은 방식으로 다시 검증하려면 파일 경로 실재 여부,
> 라우트 목록(`app.main.app.routes`), `config.yaml` 기본값, 프리셋 `visual_mode`,
> 스타일 ASCII 여부, 문서가 언급한 함수의 실제 정의 유무를 대조하면 된다.
