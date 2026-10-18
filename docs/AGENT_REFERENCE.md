# 에이전트 참고 문서 (상세)

`AGENTS.md` 에서 옮긴 상세 설명이다 (2026-10-16, 문장 변경 없이 이동). 해당 기능을 고치거나 결과를 설명할 때만 읽는다.

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


## 카드뉴스 · 인스타툰 · 하이브리드 — 내부 흐름 (2026-10-07)

`make` 에 출력 형식이 생겼다. `--format shorts`(기본) | `card_news` | `insta_toon` | `hybrid` | `all`.
예전 톤 값(`--format information|story|issue`)도 그대로 받는다(새 이름은 `--tone`).
결과는 `output/<id>/<format>/card_01.png …`(1080x1350 PNG), `manifest.json`(페이지별 타입·문구·이미지·캐릭터·출처·대체 여부),
`sources.json`(이 형식에 쓴 자료), `plan.json`, `master.json`, `caption.txt`(인스타 본문·해시태그·출처).

흐름: 입력 수집(쇼츠와 같은 research/article/youtube 모듈) → **Master Content(AI 1회)** → **Format Planner(AI 1회, 규칙으로 보정)**
→ 카드 사진(쇼츠 Source Resolver 그대로: AI 2회, usable 만) → 만화 컷(업로드 `toon_NN_*` → Bible 참고 이미지 → AI(설정 시) → 앱 마스코트)
→ Pillow 렌더러(글자·말풍선은 전부 앱이 합성). 페이지 하나가 실패해도 대체 레이아웃으로 계속한다.
`hybrid` 비율은 Master 의 story_score 로 자동: 정보형 80/20, 일반 50/50, 스토리형 20/80(카드/만화).
`all` = 쇼츠(기존 엔진 그대로) + 같은 대본으로 하이브리드. 쇼츠가 실패해도 카드는 만든다(`partial_failure`, 쇼츠는 `resume`).

- 템플릿: `clean_info`(정보형 카드뉴스 기본), `character_info`(카드에 안내 캐릭터), `hamtorich_toon`(인스타툰·하이브리드 기본), `comic_hybrid`(기존 선택형). `app/carousel/templates/*.yaml` 추가만으로 새 템플릿.
- 캐릭터: `characters/<id>/bible.json`(Character Bible, id 는 ASCII). `characters add --file bible.json`. **기본(브랜드) 캐릭터는 햄토리치 `hamtorich_01`** — 최상위 기준 `characters/hamtorich_01/master/design_sheet.png`, 제작용 투명 포즈 8장 `poses/`, 새 포즈 규칙 `characters/hamtorich_01/README.md`. 토리 `tory_01` 은 `--character tory_01` 로 계속 사용.
- 자동 인스타툰: `toon --topic "…" --facts-from-topic <topic_id> [--writer rules|claude]` — 훅→상황→상대역→갈등→정보 발견→해결·반전→결론 8장. 기본 `rules` 무료(AI 0회), `claude` 는 사용자가 고를 때만(구독 CLI). 수치는 verified fact 원문만, 검증 실패 초안은 `status: rejected`(PNG 없음). 품질 기준 샘플은 `samples/`. 사용자 그림은 `assets/inbox/`(자동 등록), 장면 배경은 코드로 그린 11종(`app/carousel/scenes.py`).
- 캐릭터 그림은 Bible 의 등록 포즈(햄토리치)를 컷의 감정·자세에 맞춰 고른다(무료). 등록 그림이 없는 토리는 앱 마스코트로 그린다. 햄토리치는 마스코트로 대체하지 않는다(mascot_fallback=false). `config.yaml` `carousel.image_provider` 를 바꾸면 유료 AI 생성 — 사용자 허락 없이 바꾸지 않는다.
  `approved=false` 포즈는 기본 포즈와 reference_images 경로로도 사용하지 않는다. 받은편지함 원본은 같은 이름이어도 별도 이름으로 보존한다. 출처 상자는 공식 자료 여부를 단정하지 않는 '근거 자료' 배지를 쓴다.
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
