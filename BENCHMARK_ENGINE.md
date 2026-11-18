# 범용 Benchmark Engine 1단계 구현 보고 (2026-10-02)

사용자 요청에 따라 다른 컨셉의 작업과 분리한 `shorts-ai-benchmark-v2`에서 구현했다. V1 완료 커밋 `dce81daad0c69fd765be5f15915d58630ab1679f`를 기준으로 만든 독립 worktree이며, 현재 detached HEAD이다. 커밋·push·amend·rebase는 하지 않았다. 기존 `shorts-ai`의 다른 세션 작업과 산출물은 이 작업에 포함하지 않는다.

## 1. 구현한 architecture

```text
권리 확인 로컬 입력 (1~4개)
  → Material: 관찰 수집 / 사용자가 제공한 관찰
  → WatchIntent: 시청 이유 → viewer_question → hook/claim
  → EvidenceSelection: 이미 확정된 claim을 증명하는 근거 선택 → payoff
  → BenchmarkPlan + profile 규칙·출처·관찰 구간 검증
  → visual_clip adapter
  → 기존 PlannedScript / VideoBlueprint / timeline.json
  → 기존 자막 + b-roll renderer → final.mp4
```

`app/benchmarks/`에 공통 계약·분석·로더·프로필을 둔다. 이미 Python 패키지인 `app` 안에서 상대 import와 CLI 설치 경로를 유지하려는 선택이다. 새로운 프레임워크는 도입하지 않았다. 공통 모델에는 특정 채널·장르 enum이 없다. K-pop의 여섯 observation 규칙과 시간 구성은 JSON에만 존재한다.

첫 분석 응답인 `WatchIntent`에는 클립 선택·타임코드 필드가 없다. 관찰 내용에서 시청 이유와 질문·claim을 먼저 저장하고, 별도 두 번째 호출에서 근거를 선택한다. `benchmark_intent.json`으로 먼저 정한 의도를 보존하며 두 번째 응답은 claim을 변경할 수 없다. 근거가 불충분하거나 confidence가 기준보다 낮으면 중단한다. confidence는 모델/사용자의 자체 평가이며 통계적으로 보정한 확률이 아니다.

공통 근거는 `evidence_type`, 설명, `supports_claim`, 출처, 선택적 `clip`, `observation_ids`를 갖는다. `fact`, `timeline`, `quote`, `reaction`, `comparison`, `current_update`, `multiple_examples` 등도 계약으로 표현할 수 있다. 영상 외 관찰은 타임코드가 필수가 아니다. 이러한 타입의 실제 입력 수집기·렌더 adapter·프로필은 이번 범위에 포함하지 않는다.

## 2. 수정한 파일

| 파일 | 변경 이유 |
|---|---|
| `app/factory/__main__.py` | 영상 입력, 프로필 목록, 계획/관찰 JSON, 원본 음소거, inspect 옵션 |
| `app/factory/core.py` | Benchmark 분기, 기존 상태/조회/수정/resume/rerender 연결 |
| `app/pipeline/llm.py` | 기존 Claude 구독 호출에 로컬 JPEG inline 입력 지원. 유료 fallback 없음 |
| `app/pipeline/models.py` | Blueprint timing에 선택적 `evidence_aligned` 값 추가 |
| `app/pipeline/timeline.py` | 선택적 narration, 근거 종료 시각, Benchmark 렌더 옵션 전달 |
| `app/pipeline/render.py` | narration 없는 b-roll, 종료 시각 제한, 원본 오디오, 전체 근거 프레임 배치 |
| `app/pipeline/subtitles.py` | `static` 자막은 카라오케 없이 짧은 해설로 렌더 |
| `app/pipeline/sources.py` | 확인된 사용 허가를 의미하는 `licensed_upload` 권리 유형 추가 |
| `app/pipeline/capcut.py` | narration 없는 프로젝트도 내보내기 가능 |
| `README.md`, `AGENTS.md`, `CLAUDE.md` | 별도 작업 범위와 자연어 사용 안내 |
| `IMPLEMENTATION_PLAN.md`, `HANDOFF.md` | 구현·검증·환경·분리 작업 기록 |

## 3. 새로 추가한 파일

| 파일 | 역할 |
|---|---|
| `app/benchmarks/__init__.py` | 공통 엔진 공개 진입점 |
| `app/benchmarks/models.py` | 장르에 독립적인 계약과 입력 검증 |
| `app/benchmarks/profiles.py` | 안전한 로컬 JSON 로더 |
| `app/benchmarks/engine.py` | 관찰, 시청 이유 우선 분석, 근거 검증 |
| `app/benchmarks/adapters.py` | 공통 계획을 V1 렌더 계약으로 변환 |
| `app/benchmarks/profiles/kpop_observation_clip.json` | 이번에 실제 제공하는 유일한 profile |
| `app/factory/benchmark.py` | 로컬 입력·권리·상태·검토·재개·렌더 생명주기 |
| `examples/benchmark_plan.json` | 사람이 확인해서 수정할 전체 제작 계획 예시 |
| `examples/benchmark_observations.json` | 직접 관찰한 타임코드를 입력하는 예시 |
| `tests/test_benchmark_engine.py` | 계약·분석 순서·확장성·렌더 연결 검증 |
| `tests/test_benchmark_factory.py` | CLI·권리·상태·실패·재개·결과 보존 검증 |
| `BENCHMARK_ENGINE.md` | 이 보고서와 사용법 |

프로필에는 구조적 규칙만 저장한다. 영상·다른 채널 자산·저작물은 넣지 않는다.

## 4. 새로운 CLI 사용법

PowerShell에서 반드시 **별도 작업 폴더**를 연다.

```powershell
cd 'C:\Users\young\OneDrive\Desktop\클로드코드\shorts-ai-benchmark-v2'
.\.venv\Scripts\python.exe -m app.factory benchmark-profiles

# Claude 구독: 관찰 수집 → 시청 이유 → 근거 → 렌더
.\.venv\Scripts\python.exe -m app.factory make --video 'C:\Videos\my-performance.mp4' --benchmark kpop_observation_clip --license my_channel --note '내가 촬영했고 출연자·음원·편집·상업 사용 권한을 확인한 영상' --confirm-rights

# 대본과 근거를 먼저 검토
.\.venv\Scripts\python.exe -m app.factory make --video 'C:\Videos\my-performance.mp4' --benchmark kpop_observation_clip --review --license licensed_upload --note '영상과 음원의 쇼츠 편집·상업 사용을 허가받음' --confirm-rights
.\.venv\Scripts\python.exe -m app.factory inspect PROJECT_ID --part benchmark
.\.venv\Scripts\python.exe -m app.factory resume PROJECT_ID
.\.venv\Scripts\python.exe -m app.factory rerender PROJECT_ID

# AI 없이: 사람이 실제 영상에 맞게 확인한 계획 JSON
.\.venv\Scripts\python.exe -m app.factory make --video 'C:\Videos\my-performance.mp4' --benchmark kpop_observation_clip --benchmark-plan 'C:\Videos\verified-plan.json' --review --note '내 영상과 음원 사용 권한 확인' --confirm-rights

# 프레임 분석 대신 직접 관찰한 JSON; 이후 시청 이유/근거 선택은 Claude 구독 사용
.\.venv\Scripts\python.exe -m app.factory make --video 'C:\Videos\my-performance.mp4' --benchmark kpop_observation_clip --benchmark-observations 'C:\Videos\observations.json' --review --note '내 영상과 음원 사용 권한 확인' --confirm-rights
```

`--video`를 반복하면 입력 순서대로 `video_1`~`video_4`가 된다. JSON의 `clip.source_id`/관찰 출처는 이 ID를 사용한다. 파일당 200MB 이하의 읽을 수 있는 로컬 영상만 지원한다. URL·원격 UNC 입력은 거부한다. 자동 다운로드 기능은 없다.

`--seconds 30`으로 목표 길이를 지정하고 `--mute-source`로 원본 오디오를 제외할 수 있다. 기본 30초, 권장 20~35초다. profile의 단계 시간 비율을 목표 길이에 맞게 조정한다. 선택한 근거 전체가 근거 단계 안에 들어오지 않으면 조용히 잘라내지 않고 오류를 반환한다. 자막이 꺼져 있어도 상단 제목과 자체 branding은 유지한다. `--instructions`는 제작 선호를 전달하며 사실 근거로 취급하지 않는다.

`examples`의 시간·내용은 **실제 영상 분석 결과가 아닌 예시**다. 해당 구간이 있는 영상에 맞게 직접 확인·수정해야 한다. `--benchmark-plan`은 AI를 호출하지 않으며 supplied_plan으로 기록한다. 자동 모드는 Claude 구독만 사용하고 구독 실패 시 유료 API로 전환하지 않는다. Benchmark에서는 V1 입력·스타일·TTS·유료 허용 옵션을 혼합하지 않는다.

자연어 매핑: “이 영상으로 kpop_observation_clip 벤치마크를 적용해서 쇼츠 만들어줘” → 로컬 파일과 이미 확인된 사용 권리 근거로 위 `make --video ... --benchmark ...`를 실행한다. “대본 먼저”는 `--review`, “좋아 계속해”는 해당 ID의 `resume`이다. 권리 확인은 영상뿐 아니라 유지할 원본 오디오까지 포함해야 한다.

## 5. kpop_observation_clip profile 전체 예시

아래는 실제 제공하는 JSON의 전체 내용이다. `stages`, `length`, `analysis`, `render`를 수정해 기본값을 바꿀 수 있다. 새로운 프로젝트는 바뀐 profile을 읽고, 기존 프로젝트는 저장된 snapshot으로 재개한다.

```json
{
  "version": 1,
  "profile_name": "kpop_observation_clip",
  "content_type": "observation_clip",
  "render_adapter": "visual_clip",
  "minimum_confidence": 0.65,
  "length": {"recommended_min": 20, "recommended_max": 35, "target": 30},
  "stages": [
    {"key": "reason_to_watch", "seconds": 2, "caption": "reason_to_watch", "evidence_start": 0},
    {"key": "first_evidence", "seconds": 6, "caption": "reaction_captions", "evidence_start": 0},
    {"key": "comparison_or_interpretation", "seconds": 14, "caption": "reaction_captions", "evidence_start": 1},
    {"key": "payoff_or_question", "seconds": 8, "caption": "payoff_or_question", "evidence_start": 0}
  ],
  "evidence_types": ["visual"],
  "observation_types": {
    "discovery": {"description": "놓치기 쉬운 장면이나 포인트 발견", "min_evidence": 1},
    "unexpected_change": {"description": "이전 또는 다른 장면과 달라진 점", "min_evidence": 2},
    "comparison": {"description": "같은 곡, 다른 무대, 다른 멤버 등의 비교", "min_evidence": 2},
    "common_pattern": {"description": "여러 장면에서 반복되는 공통점", "min_evidence": 2},
    "rediscovery": {"description": "과거 장면을 현재 관점에서 다시 보기. 과거 시점은 제공된 근거가 있을 때만 언급", "min_evidence": 1},
    "evidence_based_reaction": {"description": "실제 화면으로 확인 가능한 강한 인상", "min_evidence": 1}
  },
  "viewer_question_rules": [
    "시청자가 왜 이 장면을 봐야 하는지 먼저 정의한다.",
    "화면을 보면 답을 확인할 수 있는 구체적인 질문을 만든다.",
    "인물의 속마음, 관계, 실력 서열을 화면만으로 단정하지 않는다."
  ],
  "hook_types": ["놓치기 쉬운 디테일", "확인 가능한 변화", "같은 동작의 표현 차이", "반복되는 공통점"],
  "title_strategy": [
    "기본 크기에서 상단 두 줄에 들어가는 짧은 제목: 가급적 24자 이내.",
    "짧은 질문 또는 관찰할 포인트로 제목의 약속을 만든다.",
    "제목에서 약속한 차이나 포인트를 선택한 evidence가 직접 증명해야 한다.",
    "타 채널 고유 문구를 복사하거나 확인되지 않은 논란을 만들지 않는다."
  ],
  "caption_rules": [
    "시청 이유, payoff, ending question, reaction은 각각 가급적 40자 이내. 16자씩 세 줄 안에 들어오게 쓴다.",
    "짧은 해설 또는 reaction caption, evidence 순서와 1:1 대응",
    "화면에서 확인할 수 있는 동작, 시선, 표정, 위치만 설명",
    "감탄만 반복하지 않고 어디를 보면 되는지 안내"
  ],
  "analysis": {
    "frame_interval_seconds": 2,
    "max_frames": 24,
    "rules": [
      "하이라이트 점수로 장면부터 고르지 않는다. 시청 이유와 claim을 먼저 확정한다.",
      "comparison, unexpected_change, common_pattern은 서로 다른 근거 구간을 두 개 이상 사용한다.",
      "샘플 프레임은 연속 동작의 완전한 증거가 아니다. 샘플에서 확인되지 않은 동작이나 인물 이름을 추측하지 않는다.",
      "근거가 부족하면 임의 구간이나 과장된 제목으로 대체하지 않고 분석 실패를 알린다."
    ]
  },
  "render": {
    "width": 1080, "height": 1920, "fps": 30,
    "narration": false, "preserve_source_audio": true, "source_volume": 1.0,
    "blur_background": true, "frame_layout": "evidence", "branding": "콘텐츠팩토리",
    "font": "Malgun Gothic", "caption_size": 60,
    "accent": "#38BDF8", "outline": "#122033"
  }
}
```

## 6. 기존 V1과 연결되는 방식

공통 엔진의 계획은 V1 `Script`를 상속하지 않는다. adapter에서만 기존 `PlannedScript`, `VideoBlueprint`, `build_timeline`으로 변환한다. 자막 문장은 기존 프로젝트 호환을 위해 `narration` 필드에도 보존하지만 실제 narration 오디오와 TTS 호출은 없다. Blueprint는 `evidence_aligned`로 시간을 기록한다.

`make`, `resume`, `rerender`, `inspect`, `edit-scene`, `export`와 기존 상태·권리 대장을 재사용한다. 기존 V1의 `information/story/issue`, batch, renderer, subtitle, b-roll 경로와 기본값은 유지한다. Benchmark의 `edit-scene --narration`은 화면 해설 편집으로 사용되며 `--emphasis`는 해당 장면 제목 편집이다. 근거를 카드/다른 화면으로 교체하는 Benchmark `set-visual`은 거부한다. 근거 변경은 검증된 계획 JSON으로 새 프로젝트를 만든다. **V1의 set-visual 동작은 유지한다.**

기존 `script.json`, `blueprint.json`, `timeline.json`과 상태 형식을 유지하고 Benchmark에만 추가 파일·메타데이터를 저장한다. `benchmark.json`, `benchmark_profile.json`, `benchmark_sources.json`, 필요 시 `benchmark_material.json`, `benchmark_intent.json`, 프레임 샘플 기록이 추가된다. 원본 복사본은 작업별 `uploads/`에 보존하며 SHA-256으로 변경을 검사한다. 새 입력은 별도 폴더의 `output/`에 저장된다.

렌더는 선택한 구간 밖 프레임을 읽어 뒤에 붙이지 않도록 `src_end`를 전달한다. 모든 근거를 payoff 전에 끝까지 보여 주며 부족한 시간을 반복할 때 reaction에 “다시 보기”를 표시한다. 자체 남색 배경·하늘색 해설·맑은 고딕·콘텐츠팩토리 branding을 사용한다. 전체 근거 프레임을 상단 제목과 하단 해설 영역 사이에 맞춰 배치한다. 제목·해설이 지정한 줄 수를 넘으면 약속/근거가 잘리지 않도록 렌더 전에 오류를 낸다.

재개·재렌더는 AI·TTS를 다시 호출하지 않는다. 저장된 profile/근거, 파일 hash/권리, 타임라인이 근거 범위를 지키는지와 payoff 전 전체 근거가 나오는지 재검사한다. 새로운 MP4의 해상도·길이를 확인한 뒤에만 final.mp4를 교체한다. 렌더 실패 시 기존 final.mp4를 보존한다.

## 7. 추가한 테스트

새 테스트 **43개**: profile loading/없는 이름/안전한 이름, 스키마·기본 fallback, 여섯 observation 규칙, 근거 구간·비교 최소 개수·중복/겹침·출처 경계, confidence, 관찰과의 연결, 영상 외 계약/V1 독립성, 시청 이유를 먼저 확정하는 두 호출, 구독 이미지 입력·유료 fallback 금지, 샘플 수/시각 검사, 단계 시간 변경·근거 전체 재생·자막 잘림 검사, 기존 b-roll 호출과 V1 오디오 기본값, narration 없는 CapCut/pack, 권리·원격 입력·CLI, 검토/편집/resume/inspect/rerender, 파일 변경·타임라인 이탈·두 번째 근거 누락 차단, 렌더 실패·잘못된 출력 해상도에서 기존 결과 보존을 검증한다.

AI, TTS, FFmpeg/FFprobe는 mock으로 대체한다. 테스트는 임시 폴더에만 쓰고 실제 사용자 영상을 만들지 않는다.

## 8. 전체 자동 테스트 결과

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -q
# 기존 132 + Benchmark 43 = 175 tests, OK
.\.venv\Scripts\python.exe -X utf8 -m compileall -q app tests
```

모든 기존 테스트와 새 테스트를 통과했다. CLI `--help`, `make --help`, profile 목록도 읽기 명령으로 확인했다. 테스트/검증 과정에 유료 API 호출과 실제 제작은 없었다.

이 PC의 원래 venv launcher가 사라진 Python 3.12.10 위치를 가리켜, 별도 worktree에 번들 Python 3.12.14로 `.venv`를 만들었다. `.pth`로 기존 venv의 Python 3.12 의존성을 읽어 사용하며 원래 환경은 수정하지 않았다. 이 `.venv`는 git ignore 대상이고 다른 PC로 이동할 때는 Python 3.12로 새 venv와 requirements 설치가 필요하다.

## 9. 실제 동영상으로 아직 검증하지 못한 부분

이번 개발에서는 실제 샘플 제작을 실행하지 않았다. 자동 테스트 통과는 실제 분석/화면 품질 검증을 대체하지 않는다.

- 실제 Claude 구독에서 inline JPEG 입력과 구조화 출력이 끝까지 성공하는지
- 샘플 간격 때문에 빠른 안무·표정·시선 변화가 누락되는 정도와 claim/evidence의 실제 의미적 정확도
- 실제 FFmpeg에서 가로/세로·서로 다른 프레임률·무음/원본 오디오 입력을 조합할 때 해상도·동기화·자막/branding 가독성
- CapCut 앱에서 실제 가져온 뒤 화면/오디오가 기대대로 표시되는지

기본 최대 24개 프레임은 전체 영상을 연속 분석하는 방식이 아니다. 움직임 전체·인물 이름·촬영일·속마음·실력 서열을 확인해 준다고 주장하지 않는다. 관찰 구간 검사와 supports_claim 설명은 의미적 사실 검증을 완전히 보장하지 않는다. 빠른 동작 비교는 직접 확인한 관찰 JSON 또는 계획 JSON과 검토 흐름을 사용할 수 있다. 원본 오디오 보존은 선택된 근거 구간의 오디오를 이어 재생하는 것이며 전체 곡이 연속 재생되는 방식은 아니다.

## 10. curiosity_update_story를 추가할 때 수정할 범위

아직 해당 profile은 구현하거나 제공하지 않았다. 다음 단계의 범위는 다음과 같다.

1. `app/benchmarks/profiles/curiosity_update_story.json` 추가: 궁금증→과거→변화→현재→질문의 답, 허용 근거와 제목/해설 규칙 설정
2. 사실·업데이트·타임라인 입력 수집/출처 검증 계층 추가: 공통 `Material`/`Evidence`로 변환. 실제 fact grounding 규칙은 새 입력 계층에서 검증
3. `app/benchmarks/adapters.py`에 이야기 adapter와 registry 항목 추가: 기존 대본·화면·렌더로 변환, 필요 시 새로운 caption 역할을 해당 adapter에만 구현
4. Factory에 해당 입력을 받는 작은 분기/CLI 옵션 추가와 테스트·문서 추가

공통 WatchIntent → EvidenceSelection, BenchmarkPlan, profile loader, 기존 V1 renderer는 다시 작성할 필요가 없다. 현재 Factory 입력 경로는 local video용으로 범위가 정해져 있으므로 텍스트/사실 입력을 지원하는 진입점은 추가해야 한다. profile JSON만 넣으면 아직 없는 story adapter까지 자동 완성된다고 약속하지 않는다.

## 마지막 git 확인

별도 worktree에서 `git diff --check`, `git diff --stat`, 전체 diff, `git status --short`를 확인했다. 위 목록의 코드·예시·테스트·문서 변경만 있으며 예상 밖 추적 파일 변경은 없다. `.venv`/Python 캐시 등 로컬 환경은 ignore 대상이다. HEAD는 시작 커밋 그대로이며 커밋·push는 하지 않았다. 원래 폴더에서 진행 중인 다른 컨셉의 변경은 이번 diff에 포함되지 않는다.
