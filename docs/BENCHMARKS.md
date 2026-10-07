# Benchmark 현황판 (단일 기준 문서)

**최종 갱신: 2026-10-08.** 새 benchmark 를 분석·반영할 때 이 표를 같이 갱신한다(CLAUDE.md/AGENTS.md 규칙).
상태는 문서·과거 대화가 아니라 **현재 코드·테스트·output 기록**으로 판정했다. "분석됨"과 "구현됨"을 구분한다.

상태 열 의미
- analyzed: 실제 영상/목록을 보고 구조를 분석한 기록이 있다
- source_registered: `benchmarks/sources/<id>.json` 에 등록됐다
- profile_created: 일반화된 production profile(`benchmarks/profiles/*.yaml` 또는 `benchmarks/kpop_observation_clip.yaml`)이 있다
- pipeline_connected: V1 `make` 자동 경로(benchmark auto router → 대본·장면 → TTS·렌더)가 이 구조로 실제 영상을 만들 수 있다
- tested: 자동 테스트(mock)가 있다
- real_video_verified: 실제 Claude 구독 + Edge TTS + ffmpeg 로 MP4 를 만들고 `verify_factory_v1.py --verify` 를 통과했다

## 1. Benchmark source (6개 등록 + 미등록 분석·언급 5건)

채널 이름은 source 로만 쓰고 production profile 이름으로 쓰지 않는다. 한 source 가 여러 profile 로, 여러 source 가 한 profile 로 갈 수 있다.

| source id | 이름 | 분석일 | 분류 | 핵심 성공 구조 | derived profile | analyzed | registered | profile | pipeline | tests | real video |
|---|---|---|---|---|---|---|---|---|---|---|---|
| doltori | 돌토리 @doltori | 2026-10-02 | K팝 관찰 | 볼 이유 → 장면 근거 → 짧은 해설 → 선택 질문 | kpop_observation_clip | ✅ | ✅ | ✅ | △ 근거 영상(권리 확인 또는 `--quote`) 있을 때만 | ✅ | ❌ |
| zzal_ing | 짤잉 @zzal_ing | 2026-10-02 | 근황/이유/후속 | 궁금증 → 과거 → 변화 → 현재 → 제목의 답 | curiosity_update_story | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (A·F·G) |
| bks_simulation | BKS Simulation | 2026-10-03 | 단일 변수 물리 비교 | 질문/장치 → 변수 하나 → 반복 → 결과 비교 | physics_comparison_simulation | ✅ | ✅ | ✅ | △ 근거 영상 있을 때만 | ✅ | ❌ |
| lesgi | 레스기 | 2026-10-03 | 순위 사례 | 쉬운 주제 → 5위부터 1위 → 마지막 보상 | ranked_moments | ✅ | ✅ | ✅ | △ 근거 영상 있을 때만 | ✅ | ❌ |
| architecture_mania | 건축매니아 (콘크리트/DDP 2편) | 2026-09-21 | 원리/문제 해결 | 통념 → 반전 → 질문 → 원리 → 대안 한계 → 해결 → 답 | mechanism_explainer (+ 기존 스타일 `style-f8b83e20`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (B·D·E) |
| factory_reference | reference.mp4 — 제작 시스템 + 12종 스타일 | 2026-09-29 | 시스템/복수 예시 | 채팅 → 구조 선택 → 근거 → 제작 계획 → 화면/자막 → 검토 | curiosity_update_story, ranked_moments, mechanism_explainer, quote_context_story, illustrated_fact_explainer, event_timeline_story | ✅ | ✅ | ✅ | ✅ (단 ranked 는 △) | ✅ | 부분 (curiosity·mechanism·event_timeline) |

`factory_reference` 안의 세부 스타일(findings, 13건): 건축사전st(catalog_only → mechanism), 더다큐롱폼st(partial → event_timeline),
랭킹st(partial → ranked), 무비st·비하인드스토리st·연예인쇼핑st·정치채널st(direct → quote_context), 스포츠st(direct → event_timeline),
이게맞나st(catalog_only → curiosity), 이라스토야st·커뮤니티형st(direct → illustrated_fact), 요즘PDst(catalog_only, profile 없음), 롱투숏/모션그래픽(제작 기능, profile 아님).

미등록 분석 (source 로 등록하지 않은 이유)

| 분석 | 상태 | 처리 |
|---|---|---|
| 요즘PD (factory_reference finding) | catalog_only — 완성 영상의 실제 구조를 확인하지 못함 | profile 만들지 않음. 실영상 분석 후 기존 profile variation 인지 판단 |
| 롱투숏/모션그래픽 (factory_reference finding) | 제작 기능 관찰 | profile 이 아니라 기능 후보 (구현 없음) |
| `../shorts-ai-benchmark-v2` (별도 폴더, 2026-10-02) | 돌토리 K팝 구조의 별도 1단계 구현 | 같은 source(doltori). 이 브랜치에 병합하지 않음 |
| 경제대부·경제뉴스·해외 콘텐츠 등 | 기능 예시로만 언급, 분석 URL 없음 | source 로 꾸며서 추가하지 않음 |
| 2026-10-07 "오사카에서 생긴 일" 링크 (G) | benchmark 분석이 아니라 제작 실사용 | source 아님 (아래 실제 검증 G) |

## 2. Production profile (8개, 코드 기준)

V1 자동 경로 정보는 `benchmarks/v1/integration.yaml`, 오프라인 profile 계약은 `benchmarks/profiles/*.yaml`·`benchmarks/kpop_observation_clip.yaml`.
모든 profile 이 auto router 평가 대상이다(8개 전부 점수화). 목표 길이는 `make --seconds` 가 정하고, 아래 범위를 벗어나면 quality 경고만 남긴다.

| profile | 목적 | reason_to_watch / viewer_question | hook | evidence (필수 슬롯) | narration | scene structure (beat_role) | 권장 길이 | 화면 전략 (source_strategy) | V1 연결 | real video |
|---|---|---|---|---|---|---|---|---|---|---|
| curiosity_update_story | 익숙한 대상의 변화·후속 소식 | 익숙한 대상의 변화 / "왜·무엇이 바뀌었나" | 결과·현재 모습 먼저 | past_state, change_point, current_state | Edge TTS | hook → background → change×2 → current_update → payoff → ending_question | 20~60초 | 근거형: licensed→PD→인용→생성→카드, 영상 우선 | ✅ | ✅ A·F·G |
| event_timeline_story | 사건을 시간 순서로 | 결과·극적 순간 / "어떻게 여기까지" | 결과 먼저 | event_start, turning_point, outcome | Edge TTS | hook → background → turning_point×2 → outcome → payoff → ending_question | 30~90초 | 근거형, 사진 우선 | ✅ | ✅ C |
| mechanism_explainer | 통념을 뒤집고 원리 설명 | 통념과 사실의 어긋남 / "사실은 왜" | 통념 → 반전 질문 | common_belief, mechanism | Edge TTS | hook → question_context → mechanism×2 → solution → payoff → ending_question | 30~90초 | 정보형: licensed→PD→생성→인용→카드, 도해 우선 | ✅ | ✅ B·D·E |
| illustrated_fact_explainer | 생활 질문·숫자를 짧게 (안전 fallback) | 생활 궁금증 / "이건 왜/얼마나" | 생활 질문·의외의 숫자 | core_fact | Edge TTS | hook → context×2 → explanation×2 → payoff → ending_question | 20~60초 | 정보형, 사진 우선 | ✅ (fallback 겸용) | ❌ |
| quote_context_story | 화제 발언을 맥락과 함께 | 발언의 진짜 뜻 / "무슨 뜻이었나" | 발언 핵심 인용 | quote, speaker_context | Edge TTS | hook → context×2 → statement×2 → payoff → ending_question | 20~60초 | 근거형, 훅도 카드 | ✅ | ❌ (G에서 2위 70점) |
| kpop_observation_clip | 무대·영상에서 확인 가능한 포인트 관찰 | 놓치기 쉬운 포인트·변화 / "어떤 차이가 보이나" | 볼 이유 한 문장 | observed_moment, evidence_clip | optional (V1 은 해설 나레이션) | reason_to_watch → first_evidence → comparison_or_interpretation×2 → payoff_or_question | 20~35초 | 근거형, 영상 우선, 인용 허용 | △ 근거 영상 필요 | ❌ |
| physics_comparison_simulation | 변수 하나만 바꾼 실험 비교 | 결과 예상 / "어느 조건이 어떻게 다를까" | 실험 질문 | variable, conditions, result | optional | hook → trials×3 → payoff → ending_question | 20~45초 | 근거형, 영상 우선 | △ 근거 영상 필요 | ❌ |
| ranked_moments | 정의한 기준으로 사례 순위 | 기준과 사례 수 / "1위는?" | 순위 기준·사례 수 | ranking_criterion, ranked_items | optional | hook → ranked_examples×3 → payoff → ending_question | 15~60초 | 근거형, 영상 우선 | △ 근거 영상 필요 | ❌ |

"△ 근거 영상 필요": router 게이트가 권리 확인 영상 또는 사용자가 준 인용 영상(`--quote`, transformative_quote)이 없으면 이 구조를 후보에서 뺀다.
오프라인 `app.factory benchmark plan/render` 경로(사람이 근거 JSON 작성, 나레이션 없음)는 8개 모두 mock 테스트로 연결돼 있으나 실제 MP4 검증은 없다.

## 3. 실제 검증 기록 (output 폴더의 project_state.json 으로 대조함)

| 실행 | 입력 | 선택 profile (점수) | 길이 | 화면 | 프로젝트 |
|---|---|---|---|---|---|
| A | 주제 "최근 화제가 된 AI 기술 하나" 30초 | curiosity_update_story 84 | 25.2초 | 카드 7 | 20261005_164635_c740 |
| B | YouTube URL (웹 망원경 분광학) | mechanism_explainer 90 | 32.9초 | 카드 (숫자·비교 카드 포함) | 20261005_165012_0833 |
| C | 주제 "1912년 타이타닉호 침몰 과정" | event_timeline_story 88 | 32.6초 | 카드 | 20261005_165421_c7c8 |
| D | YouTube URL + Source Resolver | mechanism_explainer 88 | 32.9초 | Commons 사진 4장면 (PD 3·CC BY 1) + 카드 | 20261005_171137_be9d |
| E | 주제만 + Source Resolver | mechanism_explainer 92 | 27.3초 | Commons 사진 2장면 + 카드 | 20261005_171742_b5cb |
| F | 주제 "아르테미스 2호" + Source Resolver | curiosity_update_story 87 | 26.2초 | NASA PD 영상 3장면 + 사진 1 (첫 렌더 SAR 버그 → 수정 후 resume) | 20261005_172334_074f |
| G | YouTube URL (여행 예능, K팝 관찰 요청) | curiosity_update_story 85 (kpop 62, 근거 영상 없어 제외) | 25.1초 | Commons 사진 1 + 카드 | 20261007_223747_c9e4 |
| H | 직접 대본 + `--quote` 로컬 영상 (인용 렌더 경로 확인) | not_applicable | 17.8초 | 인용 3장면 (부분 재생 + 정지, 비중 34%) | 20261007_235056_e55c |

## 4. 알려진 한계 (benchmark 관련)

- kpop_observation_clip·physics_comparison_simulation·ranked_moments 는 V1 자동 경로에서 실제 MP4 로 검증되지 않았다. 근거 영상 없이 링크만 주면 router 가 다음 구조로 넘어간다.
- illustrated_fact_explainer·quote_context_story 도 실제 MP4 검증이 없다(router 가 아직 1위로 고른 적 없음).
- Content Brief 는 자막·설명·기사 텍스트만 본다. 화면 속 표정·동작은 판단하지 못한다(Vision 분석 없음).
- 점수는 구조 선택용 내부 값이며 조회수 예측이 아니다.

---

# 이력

## 2026-10-05 Benchmark Inventory (당시 기록)

## 변경 전 Audit (코드 수정 전에 확정)

기준: shorts-ai, feature/agent-content-factory, HEAD dce81da. 별도 shorts-ai-benchmark-v2는 조사만 하고 병합하지 않는다.
자료: HANDOFF/CLAUDE/README/IMPLEMENTATION_PLAN/REFERENCE_VIDEO_ANALYSIS, 전체 app/tests/config/styles/benchmarks,
Git 전체 ref의 관련 이력, output의 분석 메모, 이 PC의 Claude 프로젝트 JSONL 전체(하위 세션 포함),
Codex 프로젝트의 벤치마킹 대화 6개(중복/중단 포함)와 원 개발 대화, 보관 채팅 목록(0개).
현재 접근 가능한 기록의 완전성이지 다른 PC에만 있는 대화까지 조사했다는 뜻은 아니다.

| source / 세부 패턴 | 장르 | 분석 존재 | profile 구현 | pipeline | test | 중복 | 이번 작업 |
|---|---|---|---|---|---|---|---|
| 돌토리 @doltori | K팝 관찰 | yes, 2026-10-02 | kpop_observation_clip YAML | plan/render | 38 | Claude/Codex 반복, reaction 이름 초안, 별도 V2 JSON | 기존 유지, source 연결 |
| 짤잉 @zzal_ing | 변화/이유/후속 | yes, 2026-10-02 | no | no | no | 중단된 이슈 채팅, reference 근황형 | curiosity_update_story 통합 |
| 레스기 | 순위별 짧은 사례 | yes, 2026-10-03 | no | no | no | reference 랭킹 | ranked_moments로 통합 |
| BKS Simulation | 단일 변수 실험 비교 | yes, 2026-10-03 | no | no | no | 없음 | physics_comparison_simulation; 자체 제작 실험 영상 편집 |
| 건축매니아 (콘크리트/DDP 2편) | 원리/문제 해결 | yes, 2026-09-21 | 기존 style YAML만 | V1 style yes, Benchmark no | V1 일반 style 검사 | 반복 분석 3회 이상, reference 건축 | mechanism_explainer로 구조화 |
| reference.mp4 — 전체 제작 시스템 | 시스템/여러 완성 예시 | yes, 2026-09-29 | no | V1 일부 기능 구현 | V1 132 | 아래 세부 패턴 | 하나의 reference source로 관리 |
| reference — 랭킹st | 클립 순위 | yes, 목록/구조 | no | no | no | 레스기 | ranked_moments |
| reference — 이게맞나st | 근황 이야기 | 목록만 | no | no | no | 짤잉 | 기존 curiosity variation, 추가 실영상 분석 필요 |
| reference — 건축사전st | 기술 원리 | 목록만 | no | no | no | 건축매니아 | mechanism variation, 최상급 주장 추측 금지 |
| reference — 정치채널st | 날짜/출처 있는 발언 | 화면 확인 | no | no | no | 비하인드 발언 | quote_context_story variation |
| reference — 비하인드스토리/무비st | 발언/장면 맥락 | 화면 확인 | no | no | no | 서로 같은 근거-맥락 구조 | quote_context_story variations |
| reference — 연예인쇼핑st | 제품 소개/평가 | 화면/원문 확인 기록 | no | no | no | 발언 맥락 | quote_context_story product variation |
| reference — 커뮤니티형/이라스토야st | 숫자/정보/일러스트 | 완성 화면 확인 | no | no | no | 사실 설명 | illustrated_fact_explainer; 자체 카드만 |
| reference — 스포츠st | 사건 흐름 | 완성 화면 확인 | no | no | no | 다큐 사건 | event_timeline_story variation |
| reference — 더다큐롱폼st | 사건/지도/시간 | 화면 일부, 전체 서사 미확인 | no | no | no | 사건 타임라인 | event_timeline_story 쇼츠 변형; 원 16:9/롱폼 미지원 |
| reference — 요즘PDst | 해외 행동/대화 현지화 | 목록만, 완성 화면 없음 | no | no | no | 이야기/인용 | source 기록; 번역/현지화 자동화 미구현 |
| reference — 롱투숏/모션그래픽 | 도구 기능 | 화면 확인 | 해당 없음 | V1 일부 | V1 | 콘텐츠 profile 아님 | source 전략만 보존; 이번 생성 기능 추가 안 함 |

벤치마킹 source는 채널/참고영상 단위 6개다. 세부 영상·스타일은 source 내 findings이며 채널로 잘못 세지 않는다.
수치/색상/문장/로고를 제작 데이터로 복제하지 않는다. 공개 수치는 과거 분석 시점의 값이며 이번 작업에서 최신 재조회하지 않는다.
기존 profile/관찰/계획/state JSON은 그대로 읽을 수 있게 유지한다. 새 입력은 오프라인 주석 근거만 사용한다.

## 변경 후 Production Inventory

| profile | source | 내용/variation | 계획/선택 | 실제 코드 연결 | 테스트 | 다음 작업 |
|---|---|---|---|---|---|---|
| kpop_observation_clip | 돌토리 | 발견/변화/비교/공통점/재발견/근거 반응 | 기존 YAML + 관찰 JSON | legacy_clip → timeline/B-roll/ASS | 기존38 + snapshot/common 검사 | 실제 권리 영상 품질 확인 |
| curiosity_update_story | 짤잉 + reference 근황 목록 | change/why/follow_up | typed evidence/3역할/출처 | evidence_cards → 자체 카드/timeline/B-roll/ASS | 신규 통합 suite | 사실 grounding/음성 adapter |
| physics_comparison_simulation | BKS Simulation | softness/size/shape/slope/height/material/obstacle | 변수1/고정조건/별도 조건값/최소2결과 | evidence_sequence → 사용자 실험 클립/timeline/B-roll/ASS | 신규 통합 suite | Blender 생성은 별도 개발 |
| ranked_moments | 레스기 + reference 랭킹 | countdown; N위부터1위, 최대10사례 | 연속 역순 순위/근거 전체/길이 | evidence_sequence → 사용자 클립+순위 자막/결과 카드 | 신규 통합 suite | 순위표 UI/실렌더 품질 |
| mechanism_explainer | 건축매니아 + reference 건축 목록 | principle/problem_solution | 질문 맥락/원리/해결3역할 | evidence_cards → 자체 원리 카드 | 신규 통합 suite | 3D 단면/논점 축소 품질 |
| quote_context_story | reference 정치/비하인드/무비/제품 | official_statement/behind_scene/scene_context/product_reaction | 맥락/발언 요약2역할/출처 | evidence_cards → 자체 발언 요약 카드 | 신규 통합 suite | 날짜/원문 맥락 사실 확인/권리 원음 adapter |
| illustrated_fact_explainer | reference 커뮤니티/이라스토야 | numbers/everyday_why | 기준/설명2역할/출처 | evidence_cards → 자체 사실/숫자 카드 | 신규 통합 suite | 숫자 단위/비교 검증/자체 일러스트 |
| event_timeline_story | reference 스포츠/다큐 | sports_event/documentary_event | 배경/전환점/결과3역할/출처 | evidence_cards → 9:16 사건 카드 | 신규 통합 suite | 사건 날짜 검증/지도, 원16:9/롱폼 미지원 |

여기서 연결은 실제 factory 계획/inspect/render와 공통 renderer 호출까지 코드와 mock 테스트로 검증한 상태다.
실제 MP4/음질/가독성/흥행 검증을 뜻하지 않는다. 카드 profile은 원 채널의 narration/실사 영상과 다른 무음 변형이다.

## 전체 source와 분석 깊이

- `architecture_mania` — 2026-09-21. 두 URL/메타데이터 분석 후 자막까지 입력된 기록. 기존 style은 보존; Benchmark 원리 구조 추가.
- `bks_simulation` — 2026-10-03. 대표 영상4편/최신·인기 목록 관찰. 시뮬레이션 생성과 조건 통제 진위를 엔진이 확인하는 것은 아니다.
- `doltori` — 2026-10-02. Claude/Codex 중복 분석을 단일 source로 통합. reaction 초안 이름은 observation profile의 관점에 흡수.
- `factory_reference` — 2026-09-29. reference.mp4 프레임 분석. 12종 스타일의 관찰 깊이와 도구 기능은 JSON의 findings에 전부 기록.
- `lesgi` — 2026-10-03. 대표 인기3편 재생/길이와 순위 구성을 관찰. reference 랭킹과 하나의 profile을 공유.
- `zzal_ing` — 2026-10-02. 최신45개/인기 목록 및 대표3편 분석. 중단된 이슈 대화는 별도 분석으로 세지 않음.

각 source의 원 URL/대표 영상/분석 기록/채택 구조/복제 제외 요소는 `benchmarks/sources/<id>.json`에 있다.
실제 분석 URL이 없고 기능 예시로만 언급된 경제대부/경제뉴스/해외 콘텐츠 등은 분석 source로 꾸며서 추가하지 않았다.

## 중복 통합과 미반영

- K팝 YAML/별도 V2 JSON/초기 kpop_reaction_clip는 같은 돌토리 구조다. 현재 브랜치에서는 기존 YAML을 확장하고 별도 V2 파일은 보존한다.
- 짤잉/이게맞나 목록 → curiosity_update_story; 레스기/reference 랭킹 → ranked_moments.
- 건축매니아/reference 건축 목록 → mechanism_explainer. 원본257~300초 해설을30~90초 개념 축소로 변형한다.
- 정치/비하인드/작품 맥락/제품 소개 → quote_context_story variations; 커뮤니티 숫자/일러스트 정보 → illustrated_fact_explainer.
- 스포츠 사건/다큐의 시간·결과 → event_timeline_story variations. 원16:9 다큐/전체 서사/지도 제작을 완성했다고 보고하지 않는다.
- 요즘PD는 catalog_only: 완성 영상의 실제 행동·대화·번역 구조를 확인하지 못해 새 production profile을 만들지 않았다. source 기록과 추가 분석 과제는 남긴다.
- 롱투숏/모션그래픽은 제작 기능이며 profile로 중복 생성하지 않는다. 별도 생성 기능은 이번에 추가하지 않았다.

## 계약/향후 확장

공통 output: profile_name, content_type, reason_to_watch, viewer_question, hook, claim, evidence_type, evidence,
payoff, ending_question, confidence, reasoning_summary. `benchmark inspect`의 benchmark 객체에 나온다.
원 plan selection/snapshot도 함께 보존해 기존 JSON/state와 호환된다.

범용 evidence type: visual, clip, fact, timeline, comparison, reaction, quote, multiple_examples, experiment_result,
before_after, current_update. 각 profile의 evidence_types/역할/길이/variation 규칙으로 실제 허용 범위를 제한한다.
사용자 annotation만 검증하고 주장 진위/공개 반응/실험 조건 통제의 의미를 자동 검증하지 않는다.

profile.strategy는 title/narration/visual/pacing/scene_structure/repeatability/follow_up을 별도로 기록해 앞으로 전략 조합이 가능하게 한다.
이번에 mix UI/서로 다른 profile의 자동 조합을 제공하지 않는다. source schema에는 선택적 source_country/source_language/target_market/
trend_date/trend_signal/localization_notes가 있다. Radar/Localization/성과 feedback 수집은 아직 없다.

## V1 자동 통합 (2026-10-05 오후)

`make` 가 기본으로 이 8개 profile 을 자동 평가·선택한다(`--benchmark auto|off|<id>`). 통합 정보는 `benchmarks/v1/integration.yaml`
(beats·research_needs·narration_mode·hook/payoff 전략·9기준 가중치·fallback=illustrated_fact_explainer), 로직은 `app/pipeline/bench_auto.py`.
아래 오프라인 `benchmark plan/render` 경로는 사람이 근거 JSON 을 직접 넣는 별도 경로로 그대로 유지한다.

| profile | V1 자동 경로 | 나레이션 | 비고 |
|---|---|---|---|
| curiosity_update_story | 사용 (실제 검증 A) | 있음 | 과거·변화 시점·현재 슬롯 필요 |
| event_timeline_story | 사용 (실제 검증 C) | 있음 | 시작·전환점·결과 슬롯 필요 |
| mechanism_explainer | 사용 (실제 검증 B, YouTube URL) | 있음 | 통념·원리 슬롯 필요 |
| illustrated_fact_explainer | 사용, fallback | 있음 | 핵심 사실 1개면 가능 |
| quote_context_story | 사용 (실제 영상 미검증) | 있음 | 발언·맥락 슬롯 필요 |
| kpop_observation_clip / physics_comparison_simulation / ranked_moments | 권리 확인 영상이 없으면 자동 제외 | optional | 영상 근거 구조. Clip Analyzer 이후 확장 |

점수는 현재 자료로 어떤 구조가 경쟁력 있는지 고르는 내부 값이며 조회수 예측이 아니다.

화면 자료(2026-10-05 저녁): profile 마다 `visual_priority`·`card_roles`·`visual_hint` 가 있고 Source Resolver 가 이를 따른다
(curiosity/physics/ranked/kpop = 영상 우선, mechanism/illustrated/event/quote = 사진·도해 우선, 마지막 질문 장면은 카드).
실제 검증: mechanism(D·E) 사진 위주, curiosity(F) NASA 영상 3장면. kpop/physics/ranked 는 여전히 권리 확인 영상이 있어야 자동 선택된다.

## 사용법

```powershell
# 정상 Python3.12 환경, shorts-ai에서 실행
.\.venv\Scripts\python.exe -m app.factory benchmark sources
.\.venv\Scripts\python.exe -m app.factory benchmark profiles
.\.venv\Scripts\python.exe -m app.factory benchmark plan --profile curiosity_update_story --input verified-update.json --confirm-rights --note "직접 새로 작성한 설명과 근거"
.\.venv\Scripts\python.exe -m app.factory benchmark inspect <ID>
.\.venv\Scripts\python.exe -m app.factory benchmark render <ID>
```

각 profile의 입력 양식은 `benchmarks/examples/<profile>.input.json`; 기존 K팝은 `kpop_comparison.input.json`.
예시는 실제 분석이 아니다. 영상 profile은 자신의 로컬 영상 경로/타임코드/조건으로, 카드 profile은 검증한 사실/출처/새 요약으로 교체한다.
본문을 자동 생성/검색하거나 URL을 다운로드하지 않는다. `--observation-type`은 선택한 profile variation 이름이고 미지원 이름은 요청 오류.

자연어: "이 주제로 curiosity_update_story 적용해줘", "이 영상으로 kpop_observation_clip 방식으로 만들어줘",
"직접 만든 실험을 physics_comparison_simulation으로 비교해줘". CLAUDE.md/AGENTS.md가 입력 JSON과 plan/render로 연결한다.
계획 확인 요청이면 plan/inspect에서 멈추고, 완성 요청이면 render까지 실행한다. V1 make/resume 명령과 구분한다.

## 검증/개발 우선순위

기존170개=V1 132+기존 Benchmark38. 이번 신규32개=registry/스키마/required fields/잘못된 근거/각 variation/
CLI/전체 profile 계획→렌더/자체 카드/실험·순위/실패 보존/구 renderer graph. 테스트별 세부는 tests/test_benchmark_inventory.py.
전체 최종 **202개 통과(61.749초), 실패0/skip0**. HANDOFF 최신 절과 `output/benchmark_full_tests.log`에 기록한다. output은 Git 제외.

1. performance feedback loop: 사용자가 제공하는 영상별24시간/7일 성과를 source/profile/variation과 연결. 비교 기간을 같게 한다.
2. Global Trend Radar: 후보/공개 근거/관찰 시점/시장 신호를 수집한 뒤 사람 검토 및 source 등록. 이번에는 수집하지 않는다.
3. Localization Engine: 위 근거와 시청 시장에 맞춰 질문/말투/배경/언어를 변형하고 사실 변화 여부 확인.

그 전에 실제 권리 영상과 사실 입력으로 소수 profile의 가독성/음질/전체 근거 표시 품질을 검증하고,
사실 grounding 및 필요 시 음성 adapter를 추가하는 것이 우선이다.
