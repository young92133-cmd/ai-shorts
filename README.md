# AI Shorts Studio

주제 한 줄, 유튜브 URL, 또는 "지금 핫한 이슈"에서 9:16 세로 쇼츠 mp4 를 자동으로 만드는 개인용 도구.

```
입력 → 리서치(뉴스/자막) → Claude 대본 → TTS 나레이션 → AI 이미지(또는 원본 클립) → 자막·BGM 합성 → final.mp4 + 제목/설명/태그
```

## 1. 준비물

| 항목 | 필요 여부 | 비고 |
|---|---|---|
| Python 3.11+ | 필수 | 설치됨 |
| ffmpeg | 필수 | `winget install Gyan.FFmpeg` (설치됨) |
| 대본 AI (아래 중 하나) | 필수 | **Claude 구독 로그인** (API 키 불필요) 또는 **OpenAI 키** |
| `GEMINI_API_KEY` | **이미지(기본값)** | https://aistudio.google.com/apikey — Nano Banana 2 |
| `FAL_KEY` | 이미지(저렴, 장당 ~4원) | https://fal.ai |
| `HF_TOKEN` | 이미지(무료·한도) | https://huggingface.co/settings/tokens → Read 토큰 |
| `NAVER_CLIENT_ID/SECRET` | 선택 | 네이버 뉴스 검색. 없으면 DuckDuckGo 만 사용 |
| `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `TYPECAST_API_KEY` | 선택 | 유료 TTS/이미지로 바꿀 때 |

`.env.example` 을 복사해 `.env` 를 만들고 키를 넣으세요.

### 대본 AI 고르기 (`config.yaml` → `llm.provider`, UI 옵션에서도 선택 가능)

| provider | 준비 | 비용 |
|---|---|---|
| `claude` (기본) | 아래 **Claude 로그인** 1회 | 구독에 포함 (Pro/Max 사용량 한도 공유) |
| `openai` | 화면의 **GPT 연결 · OpenAI API 키 등록**에서 키 저장 (또는 `.env`에 `OPENAI_API_KEY`) | API 사용량에 따라 별도 요금 |
| `anthropic` | `.env` 에 `ANTHROPIC_API_KEY` | API 종량제 |

**Claude 로그인 (한 번만)** — Claude Code CLI 로 브라우저 로그인하면 이 프로그램이 그 로그인을 그대로 씁니다. 데스크톱 앱에 번들된 `claude.exe` 를 자동으로 찾고, 없으면 `irm https://claude.ai/install.ps1 | iex` 로 설치하세요.

```bash
.venv\Scripts\python.exe -m app.pipeline.llm login     # 브라우저가 열림 → 로그인
.venv\Scripts\python.exe -m app.pipeline.llm status    # loggedIn: true 확인
.venv\Scripts\python.exe -m app.pipeline.llm test      # 구조화 응답 스모크 테스트
```

## 2. 실행

**쉬운 실행:** 프로젝트 폴더의 [`AI Shorts 실행.cmd`](AI%20Shorts%20실행.cmd)를 더블클릭하세요.
준비가 끝나면 브라우저가 자동으로 열립니다. 사용하는 동안 열린 명령 창을 유지하고,
종료할 때는 그 창을 닫으세요. 이미 실행 중이면 브라우저만 다시 엽니다.

터미널에서 직접 실행하려면:

```bash
cd shorts-ai
.venv\Scripts\activate
uvicorn app.main:app --port 8765
```

브라우저에서 http://localhost:8765

- **주제로 만들기**: 한 줄 입력 → 끝까지 자동
- **링크**: 유튜브는 자막을 분석해 새 대본으로 재구성 (옵션에서 *원본 클립 재편집* 을 켜면 하이라이트 구간을 잘라 세로로).
  유튜브 링크의 **관련 영상도 찾아서 편집**은 기본으로 켜져 있으며, 검토 화면에서 소스 후보를 고를 수 있습니다.
  **뉴스·커뮤니티 글 링크**를 넣으면 본문과 **이미지까지 가져와** 장면에 씁니다. 여러 개면 줄바꿈으로 구분
- **핫이슈 자동**: Google Trends(KR) 키워드 중 프리셋에 맞는 걸 Claude 가 골라 제작
- **영상 업로드**: 참고 영상 파일을 올리고 선택하면 음성과 여러 장면을 분석해 주제와 검색어를 정합니다.
  관련 자료·유튜브 영상 후보를 찾은 뒤 대본 검토 화면에서 쓸 영상을 고르고 자동 편집합니다.
  영상당 200MB까지 올릴 수 있습니다. 화면 분석은 Gemini 키가 있으면 Gemini를, Gemini 키 없이 GPT를 선택하면 OpenAI를 사용합니다.
  Claude를 선택하고 화면도 분석하려면 화면의 **영상 화면 분석 · Gemini API 키 등록**에서 키를 등록하세요.
  음성 분석은 Claude 선택 시 로컬 Whisper(최초 모델 다운로드), GPT 선택 시 OpenAI API를 사용합니다.
- 옵션의 **대본 먼저 확인** 을 켜두면 대본 단계에서 멈추고, 수정 후 "렌더링 시작"

### 관련 영상과 댓글 넣기

연예·정치 카테고리의 **영상 짜깁기** 또는 **영상 업로드**에서, 대본 검토 화면에 관련 영상 후보가 나타납니다.
원본 링크를 열어 확인하고 사용할 것만 체크하세요. 댓글을 자동으로 가져오려면 화면의
**댓글 자동 수집 · YouTube Data API 키 등록**에서 키를 저장해야 합니다.
공개 댓글 후보 중 최대 2개를 골라 넣을 수 있습니다. 댓글은 실제 화면을 캡처하는 대신
원문 텍스트를 익명 카드로 재구성하며, 출처 링크를 `meta.txt`에 남깁니다.
키가 없거나 해당 영상이 댓글을 공개하지 않았다면 댓글 없이 제작합니다.
외부 영상 다운로드와 자막 수집은 YouTube 측 제한으로 실패할 수 있으며,
그 경우 해당 장면은 이미지나 대체 카드로 처리됩니다.

### 💡 이미지를 공짜로 쓰는 법 (기본 설정)

Google Flow / Gemini 앱에서 만드는 이미지는 **구독료에 포함**이지만, Gemini **API**는 별도 종량제라
이미지 모델 3종 모두 무료 티어가 없습니다. 구독이 API 접근을 주지 않습니다.

그래서 기본값은 `provider: none` — **AI 생성을 하지 않습니다.** 대신 이렇게 씁니다:

1. 옵션의 **대본 먼저 확인**을 켜고 만들기 → 대본이 나오면 멈춤
2. 검토 화면의 **「장면별 이미지 프롬프트 복사」** 클릭
3. [Google Flow](https://labs.google/flow)에 붙여넣어 이미지 생성 (구독 내 무료)
4. 만든 이미지를 장면별 **＋** 버튼으로 업로드
5. **렌더링 시작** → API 비용 0원

> 돈을 조금 써서 자동화하고 싶으면 옵션에서 `fal.ai FLUX · 장당 4원`(8장 32원)을 고르세요.

### 짜깁기 모드 (정치·연예)

연예·정치 프리셋은 `visual_mode: broll` 입니다. 주제에 맞는 유튜브 영상을 자동 검색하거나
링크로 직접 지정하면, 장면마다 어울리는 구간을 잘라 이어 붙이고 **원본 소리는 작게 깔고 나레이션을 위에** 얹습니다.

- 소스당 사용 길이 상한 기본 15초 (`config.yaml` → `video.broll_max_per_source`)
- 소스 영상 최대 4개, 720p로만 다운로드
- 화면 하단에 `영상 출처: 채널명` 자동 표기 + 설명란에 모든 소스 URL
- 소스를 못 찾거나 실패하면 **이미지 모드로 자동 전환**되어 영상은 반드시 완성됩니다

### 장면 비주얼은 어디서 오나

우선순위대로 채워집니다. 앞 단계에서 못 채운 장면만 다음 단계로 넘어갑니다.

| 순서 | 출처 | 설명 |
|---|---|---|
| 0 | **짜깁기 영상** | `broll` 모드에서 소스 영상의 해당 구간 (정치·연예 기본) |
| 1 | **내 파일 첨부** | 드래그해서 올린 사진·영상. AI가 내용을 보고 어울리는 장면에 배치 (영상은 대표 프레임 사용). 파일명이 `scene_03_...` 이면 그 장면에 고정 |
| 2 | **링크에서 수집한 이미지** | 기사 본문·대표 이미지. **화면 하단에 출처가 자동 표기**되고 설명란에도 링크가 들어감 |
| 3 | **AI 생성** | 옵션에서 provider 를 고른 경우에만. 기본값 `none` 은 생성하지 않음 |
| 4 | **대체 카드** | 위가 전부 실패해도 단색 카드로 채워 영상은 반드시 완성됨 |

> 첨부 파일 배치에는 `GEMINI_API_KEY`가 쓰입니다(이미지 내용 파악용, 장당 수 원).
> 키가 없으면 분석을 건너뛰고 **올린 순서대로** 배치합니다.

### 제작 방식 2가지

| 방식 | 언제 | 어떻게 |
|---|---|---|
| **스타일 모드** | 벤치마킹할 채널처럼 만들고 싶을 때 | 스타일 드롭다운에서 저장된 지침 선택 |
| **자동 모드** (기본) | 소재에 맞게 알아서 | 스타일을 비워두면 AI가 소재를 먼저 분석해 구성·훅·장면 수·비주얼 방식을 직접 정함 |

### 스타일 만들기 — 참고 영상에서 자동 추출

**＋ 참고 영상으로 만들기** 를 누르고 벤치마킹할 채널의 영상 주소를 한 줄에 하나씩 (최대 5개) 넣으면,
자막과 구성을 분석해 **훅 공식 / 전개 구조 / 말투 / 문장 스타일 / 호흡 / 마무리** 지침을 자동으로 뽑아냅니다.
결과를 그대로 쓰거나 편집한 뒤 저장하면, 그 스타일대로 대본을 씁니다. `styles/*.yaml` 에 저장됩니다.

```bash
# CLI 로도 가능
python -m app.pipeline.styles analyze "https://youtu.be/AAA" "https://youtu.be/BBB"
python -m app.pipeline.styles list
```

> 영상당 자막을 받아오므로 **1~3분** 걸립니다.

### 이번 영상 지침에 유튜브 링크 넣기

**이번 영상 지침** 칸에 유튜브 주소를 1~5개 붙여넣으면 **참고 영상 분석해 지침 채우기** 버튼이 나타납니다.
버튼을 누르면 자막과 제목·설명에서 공통 후킹, 전개 방식, 감정 흐름, 문장 서술 방식 등을 뽑아
편집 가능한 지침으로 채워줍니다. 주소를 남겨 둔 채 **만들기**를 눌러도 먼저 자동 분석합니다.
링크와 함께 쓴 메모는 지침 끝에 남습니다. 분석 근거도 펼쳐 볼 수 있습니다.

화면의 **대본·참고 영상 분석에 사용할 AI**에서 Claude 또는 GPT를 고르세요. 두 작업에 같은 AI가
적용됩니다. Claude는 구독 로그인을, GPT는 별도 OpenAI API 키를 사용합니다. 키를 처음 등록할 때는
AI 선택 아래의 **GPT 연결**을 여세요. 자막을 가져올 수 없는 영상은 분석을 중단하고 알려줍니다.
이 기능은 자막·메타정보를 분석하며 영상 화면이나 음악은 분석하지 않습니다.
화면에서 등록한 키는 OneDrive 안의 프로젝트가 아닌 Windows 사용자 설정 폴더에 저장됩니다.

### 지침 넣는 곳 (3군데) — 아래로 갈수록 우선

| 위치 | 적용 범위 | 용도 |
|---|---|---|
| **✎ 이 프리셋 지침 편집** (프리셋 옆) | 이 카테고리 모든 영상 | 말투, 대본 규칙, 이미지 스타일, 자막 색·크기 (`presets/*.yaml`) |
| **스타일** (드롭다운) | 이 스타일을 고른 모든 영상 | 벤치마킹 채널의 구성·말투 (`styles/*.yaml`) |
| **이번 영상 지침** (입력창 아래) | 이번 한 편만 | "쉽게 설명해줘", "비유 하나 넣어줘" 같은 1회성 요청 |

충돌하면 **이번 영상 지침 > 스타일 > 프리셋** 순으로 이깁니다.

결과는 `output/<잡ID>/` 에 저장:
`final.mp4`, `thumb.jpg`, `meta.txt`(제목 3안·설명·태그·출처), `script.json`, `scenes/*.jpg`, `narration.mp3`, `subs.ass`

### CLI

```bash
python -m app.pipeline.run --topic "철근 콘크리트가 강한 이유" --preset engineering
python -m app.pipeline.run --url "https://youtu.be/..." --preset daily --clip
python -m app.pipeline.run --auto --preset entertainment
python -m app.pipeline.run --topic "..." --until script     # 대본까지만
python -m app.pipeline.run --topic "..." --instructions "쉽게 설명하고 비유를 넣어줘"
python -m app.pipeline.run --topic "..." --style style-f8b83e20   # 저장된 스타일 적용
python -m app.pipeline.run --url "https://n.news.naver.com/article/..."   # 기사 링크
python -m app.pipeline.run --topic "..." --uploads "C:\내사진폴더"        # 파일 첨부
```

## 3. 설정

- `config.yaml`: 기본 모델, TTS/이미지 provider, 해상도, 길이, BGM 볼륨, 자막 폰트
- `presets/*.yaml`: 카테고리별 말투·대본 규칙·이미지 스타일·목소리·자막 색
  - 새 프리셋을 추가하려면 yaml 하나 복사해서 `id` 를 바꾸면 UI 에 자동으로 뜸
- `assets/bgm/*.mp3`: 넣으면 자동으로 깔림 (YouTube 오디오 라이브러리 등 무료 음원)
- `assets/fonts/`: otf/ttf 를 넣고 `config.yaml` 의 `video.font` 에 폰트 이름 지정. 기본은 맑은 고딕

## 4. 비용 감각 (영상 1편, 약 55초·8장면)

| 구성 | 비용 |
|---|---|
| Claude (구독 로그인) 대본 1회 | **0원** (구독 한도 사용) |
| Edge TTS | **0원** |
| 이미지 · `none` 기본값 (Flow 이미지 첨부) | **0원** |
| 영상 짜깁기 (`broll`) | **0원** (다운로드만) |
| 이미지 · Nano Banana 2 Lite (`gemini-lite`, 기본) | 장당 49원 → 8장 **약 390원** |
| 이미지 · Nano Banana 2 (`gemini`, 공학 프리셋) | 장당 97원 → 8장 **약 780원** |
| 이미지 · Nano Banana Pro (`gemini-pro`) | 장당 194원 → 8장 약 1,550원 |
| 이미지 · fal.ai FLUX (`fal`) | 장당 4원 → 8장 약 32원 |
| GPT-5 mini 대본 1회 (Claude 대신) | 약 $0.01 |

> 웹 UI 옵션에서 provider를 고르면 **예상 비용이 실시간으로 표시**됩니다.
> 이미지 생성이 실패해도 단색 카드로 대체되어 영상은 끝까지 완성됩니다.
| Edge TTS | 무료 |
| Hugging Face 이미지 | 무료 (한도) |
| fal.ai FLUX schnell 8장 | 약 $0.03 |
| OpenAI gpt-image 8장 | $0.1~1 이상 |

## 5. 자주 겪는 문제

- **자막이 없는 유튜브 영상**: `pip install faster-whisper` 하면 로컬 음성 인식으로 대체 (첫 실행 시 모델 다운로드, CPU 는 느림)
- **이미지가 단색 카드로 나옴**: 이미지 API 가 실패한 장면. 로그에서 원인 확인. HF 무료 한도 초과면 잠시 후 재시도하거나 fal 로 전환
- **Pollinations**: 키 없이 되지만 현재 무료 티어는 저화질 + 워터마크. 마지막 수단으로만
- **ffmpeg 를 찾을 수 없음**: 설치 후 터미널(또는 앱)을 재시작해야 PATH 가 반영됨
- **기사에서 이미지를 못 가져옴**: 로그인이 필요하거나 스크립트로 이미지를 넣는 사이트(일부 커뮤니티)는 수집이 안 됩니다. 이런 경우 AI 생성으로 자동 대체됩니다

## ⚠ 저작권

- **기사 이미지·타인 영상에는 저작권이 있습니다.** 출처 자동 표기와 길이 제한은 완화 장치일 뿐 면책이 아닙니다
- 인용 범위를 넘지 않도록 최종 판단은 직접 하세요. 안전하게 가려면 **첨부 파일이나 AI 생성 이미지**만 사용하세요
- 정치·연예 주제는 프리셋에 사실 기반·중립 규칙이 들어 있지만, 업로드 전 내용을 한 번 확인하는 것을 권합니다

## 6. 구조

```
app/main.py            FastAPI + SSE
app/jobs.py            잡 큐 / 대본 검토 대기 / 상태 저장
app/pipeline/run.py    오케스트레이터 (CLI 겸용)
app/pipeline/script.py Claude 프롬프트 (구성 설계 / 대본 / 클립 계획 / 트렌드 선택)
app/pipeline/styles.py 스타일 지침 저장·로드 + 참고 영상 자동 분석
app/pipeline/article.py  기사·글 링크 본문 추출 + 이미지 수집
app/pipeline/assets.py   첨부 파일 관리 + 장면별 비주얼 우선순위 결정
app/pipeline/vision.py   이미지 내용 파악 (Gemini 비전) + 장면 매칭
app/pipeline/broll.py    소스 영상 검색·수집, 장면별 구간 매칭
app/pipeline/research.py, youtube.py, clips.py, subtitles.py, render.py
app/pipeline/tts/      edge | openai | elevenlabs | typecast
app/pipeline/images/   gemini(Nano Banana 2) | fal | huggingface | openai | pollinations
```
