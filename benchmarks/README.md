# Benchmark Engine — Stage 1

> **2026-10-08 기준:** 이 문서는 사람이 근거 JSON 을 직접 쓰는 **오프라인 경로**(`benchmark plan/inspect/render`) 안내다.
> 일반 제작은 `make` 가 같은 8개 profile 을 자동 평가·선택한다(`--benchmark auto`, `benchmarks/v1/integration.yaml`, 나레이션 포함).
> source·profile·연결·실제 검증 상태는 [docs/BENCHMARKS.md](../docs/BENCHMARKS.md) 맨 위 현황판이 기준이다.

## 최신 통합 상태 (2026-10-05)

기존 Stage1 경로에6개 source/8개 production profile을 통합했다. 전체 표와 제한은 [BENCHMARKS.md](../docs/BENCHMARKS.md).
`benchmark sources`는 source/profile 양방향 관계를 검사한다. 기존 K팝 YAML은 이 폴더에 남기고 새 profile은 profiles/,
채널/영상 분석은 sources/에 분리했다. 예전 YAML/관찰/계획/state의 load를 유지한다.

모든 profile은 `benchmark plan --profile NAME --input verified.json`에서 선택하고 inspect/render까지 연결된다.
현재 영상 profile: kpop_observation_clip(기존 clip), physics_comparison_simulation(자체 실험 영상), ranked_moments(순위 사례 영상).
현재 자체 카드 profile: curiosity_update_story, mechanism_explainer, quote_context_story, illustrated_fact_explainer, event_timeline_story.
카드 profile은 자동 narration/조사/원음/지도/번역이 없는 무음 변형이다. 실제 MP4와 의미적 사실 검증은 아직 하지 않았다.

새 JSON 예시는 examples/<profile>.input.json. 카드 source는 path 대신 reference(검증 메모/출처), 근거는 evidence_type/role/source_id/
content/supports_claim/caption/confidence를 갖는다. 영상 근거에는 clip과 조건값/순위를 추가한다.
시뮬레이션은 experiment.variable/controls와 서로 다른 condition_value, 순위는 N부터1까지 연속 rank가 필수다.
profile snapshot/전체 근거/권리/hash를 매 render 검증한다. 기존 V1의 project_state 및 최근 작업 선택과 섞이지 않는다.

아래 Stage1 안내 중 길이20~35초/6관점/클립 입력 제한은 기존 K팝에 해당한다. 새 profile의 길이/variation은 profiles 명령으로 확인한다.
Benchmark JSON은 source references에 접속하지 않는다. annotation 진위는 사용자가 확인한다. 유료 호출/외부 영상 다운로드는 없다.

영상의 디자인을 복제하지 않고 **소재 → 시청 이유 → claim을 증명하는 장면 → 짧은 해설 → 자체 렌더**를 적용한다.
V1의 `information/story/issue`, `make/resume` 경로와 별도로 `app.factory benchmark`에서 사용한다.

## 1단계의 분석 범위

이 명령은 **사용자가 작성한 영상 관찰 메모를 구조적으로 분석하는 오프라인 엔진**이다.
영상 파일만으로 인물·동작·표정을 자동 인식하거나 claim의 진위를 자동 판정하지 않는다.
입력의 claim/evidence 쌍을 검증하고, 근거의 편집상 확신으로 후보를 선택한다.
`confidence`는 선언된 claim/근거 확신도의 최솟값이며 조회수 예측이나 AI 검증 결과가 아니다.
결과에는 `selection_method=annotated_claim_evidence_v1`, `semantic_verification=user_annotations_only`를 남긴다.

## 프로필

[`kpop_observation_clip.yaml`](kpop_observation_clip.yaml)은 구조만 저장한다:

- 철학 5단계, 관점별 설명·최소 근거 수·질문 예시
- `discovery`, `unexpected_change`, `comparison`, `common_pattern`, `rediscovery`, `evidence_based_reaction`
- 기본 30초, 지원 20~35초, 최소 확신도 0.65
- `0–2 reason_to_watch`, `2–8 first_evidence`, `8–22 comparison_or_interpretation`, `22–30 payoff_or_question`

20~35초로 변경하면 네 구간의 비율을 유지한다. 디자인 정보는 프로필 밖의 자체 렌더 코드에 있다.
새 채널 분석은 같은 계약의 YAML을 이 디렉터리에 추가하고 파일명과 `id`를 일치시키면 된다.
`app/pipeline/benchmark_models.py`의 `BenchmarkProfile`은 로고·폰트·색상·영상 경로 등 알 수 없는 필드를 거부한다.
다른 채널 영상 다운로드·검색·수집은 이 명령에 없다.

## 입력 준비

[`examples/kpop_comparison.input.json`](examples/kpop_comparison.input.json)을 복사해 편집한다.
예시의 관찰 문구는 가상 메모이므로 **실제 영상을 확인한 내용으로 교체**해야 한다.
[`examples/kpop_comparison.plan.json`](examples/kpop_comparison.plan.json)은 같은 입력과 가정한 원본 길이
90초로 생성한 계획 예시다. 실제 미디어 분석·렌더 결과가 아니다. claim, 근거, 반응 자막, 질문,
확신/추론 요약, 프로필 스냅샷이 보존되는 구조를 확인할 수 있다.
`sources[].path`는 입력 JSON의 위치를 기준으로 한 상대 경로 또는 로컬 절대 경로다.
HTTP URL·네트워크 경로는 받지 않으며 실제 영상 길이는 FFprobe로 확인한다.
타임코드는 초 단위다. `00:31–00:37`은 `start: 31, end: 37`이다.

각 `observations[]` 후보에는 다음을 모두 넣는다:

- `id`, `observation_type`, `reason_to_watch`, 짧은 `hook`, `claim`
- `evidence_clips[]`: `source_id`, `start`, `end`, `perspective`, `observation`, `supports_claim`, `confidence`
- `reaction_captions[]`(각 40자 이내), `ending_question`(40자 이내)
- `confidence`(0~1), `reasoning_summary`

비교·변화·공통점은 서로 다른 `perspective`의 근거가 최소 2개 필요하다.
중복·겹침·원본 밖 구간·2초 미만 근거·빈 주장/지지 이유·낮은 확신도는 거부한다.
각 후보는 근거 최대 4개다. 전체 근거를 두 evidence 구간에서 모두 보여줄 수 없는 후보도 거부한다.
긴 근거를 임의로 잘라 주장을 뒷받침하는 부분이 빠지는 것을 막기 위한 제한이다.
통과한 후보 중 가장 높은 최소 확신도를 선택하고, 동률은 입력 순서를 따른다.
거부·미선택 사유는 `rejected_candidates`에 보존한다.

## 명령

프로젝트 루트에서, 정상 Python 3.12 가상환경을 기준으로:

```powershell
.\.venv\Scripts\python.exe -m app.factory benchmark profiles
.\.venv\Scripts\python.exe -m app.factory benchmark plan --input .\benchmarks\examples\kpop_comparison.input.json --profile kpop_observation_clip --seconds 30 --confirm-rights --note "내가 직접 촬영했고 영상과 오디오를 사용할 권리가 있음"
.\.venv\Scripts\python.exe -m app.factory benchmark inspect benchmark_작업번호
.\.venv\Scripts\python.exe -m app.factory benchmark render benchmark_작업번호
```

예시 파일 옆의 `my_practice.mp4`를 준비하거나 JSON 경로를 실제 파일로 바꾸어야 `plan`이 성공한다.
`--observation-type comparison`으로 특정 관점만 선택할 수 있다.
타인의 영상에 대한 허가를 보유했다면 `--license licensed_upload`와 구체적인 `--note`를 지정한다.
기본 `my_channel`, 또는 `ai_generated`도 지원한다. 확인은 영상과 원본 오디오의 상업적 사용·변형·제3자 권리를 포함한다.
`--mute-source`는 원본 오디오를 제거한다. 모든 경로에서 TTS/LLM/이미지 API 호출은 없다.

### 이 PC의 이동된 가상환경에서 실행하기

현재 `.venv`는 이전 PC의 사라진 Python 3.12.10 경로를 가리킨다. 이번 검증은 기존 패키지와
Codex 번들 Python 3.12.14를 사용했으며 가상환경/패키지를 변경하지 않았다.
이 PC에서는 프로젝트 루트에서 아래 준비 후 `$benchmarkPython`으로 실행할 수 있다:

```powershell
$benchmarkPython = 'C:\Users\young\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = Join-Path (Get-Location) '.venv\Lib\site-packages'
$env:PYTHONIOENCODING = 'utf-8'
$env:PATH = (Join-Path (Split-Path (Get-Location) -Parent) 'ffmpeg-9.0.2-essentials_build\bin') + ';' + $env:PATH
& $benchmarkPython -B -m app.factory benchmark profiles
```

번들 경로는 이 PC의 환경에 한정된다. 다른 PC에서는 정상 Python 3.12와 프로젝트 가상환경을 준비한다.

## 저장과 렌더

`output/benchmarks/<project_id>/`에 별도로 저장하므로 V1의 최근 프로젝트·resume·batch 선택에 섞이지 않는다.

- `benchmark_plan.json`: 프로필 스냅샷, 선택된 claim/evidence 전체, 반응 자막, 질문, 확신/추론 요약, 거부 사유
- `benchmark_state.json`: 상태, 입력 길이·오디오 정보·SHA256, 공급자 `none`, TTS `none`
- `uploads/`: 선택된 권리 확인 영상의 로컬 복사
- `sources.json`: 기존 사용 권한 대장
- `timeline.json`, `subs.ass`, `brand_overlay.png`, `final.mp4`: 렌더 재료와 결과

기존 B-roll·ASS·카드 텍스트 레이아웃 도구를 사용한다. 1080×1920, 30fps, 상단 훅,
짧은 정적 자막, 자체 남색/주황색 브랜딩이다. 원본 화면을 잘라내지 않고 영역 안에 맞춘다.
근거 밖의 화면을 사용하거나 속도를 바꾸지 않는다. 남는 시간은 명시적인 다시 보기/질문으로 채우며
재생 구간과 `replay` 표시를 타임라인에 보존한다. 편집된 구간의 원본 소리는 유지할 수 있지만
연속된 노래 전체를 유지하는 기능은 아니다.

매 렌더에서 권리, 파일 SHA256, 타임코드와 근거 전체의 길이를 다시 검사한다.
1080×1920 및 목표 길이 ±0.2초 검증 후 임시 MP4를 최종 파일로 교체한다.
실패하면 계획과 기존 완성본을 보존하며 같은 `benchmark render <id>`로 재시도한다.
V1 `resume/rerender/export` 대신 benchmark 전용 명령을 사용한다. 웹 UI·CapCut 연결은 이번 단계에 없다.

## 검증

`python -B -m unittest discover -s tests -q`로 V1과 benchmark 테스트를 함께 실행한다.
새 테스트는 프로필 확장, 6개 관점, claim/evidence 검증·순위·전체 근거 보존,
구간/자막/오디오 그래프, 권리 재검사, 재렌더 실패 보존, CLI/V1 격리를 확인한다.
FFmpeg/FFprobe와 AI는 mock이다. 실제 K팝 입력과 실제 MP4, 음악 연결·시청성·흥행은 아직 검증하지 않았다.
2026-10-02: 새 benchmark 38개 + 기존 V1 132개 = 전체 170개 통과(25.221초).
로그는 Git 제외 `output/benchmark_v2_stage1_unittest.log`에 보존했다.
