# HANDOFF — 개발 인수인계 문서

## 2026-10-08 22:33 재개 — 저장 범위 분리 및 최종 검증

- Claude 세션 22:28:51 종료, 22:28:55 마지막 로그 이후 약 1분간 소스/자산 해시·HEAD·로그가 안정된 것을 확인했다.
  fetch 후 로컬/원격 작업 브랜치는 여전히 `365a810`, ahead/behind 0/0이다.
- 현재 미커밋은 수정16 + 신규12. Codex 마무리9파일과 다른 세션 햄토리치 작업19항목을 별도 기능 단위로 보존한다.
  Codex 저장 후보: AGENTS.md, CLAUDE.md, HANDOFF.md, README.md, docs/OPS_VALIDATION_2026-10-08.md,
  docs/TOPIC_STRATEGY.md, scripts/demo_topic_strategy.py, scripts/factory.ps1, tests/test_topics.py.
  별도 작업: app/carousel/{characters,pipeline,render,visuals}.py, app/topics/config.py, config.yaml, tests/test_carousel.py,
  characters/hamtorich_01/ 12파일. 이 작업을 임의 수정/되돌림/커밋하지 않는다.
- 새 백업: `../backups/ai-shorts-codex-20261008-223514/` 2,565파일, 1,367,634,686바이트.
  새 캐릭터 자료12개 및 현재 변경28항목을 포함하고 복사 전후/원본/복사본 해시와 Git bundle을 검증했다.
  이전 백업·중단 기록·Codex 변경 사본도 보존한다. 기존 환경을 다시 설치/삭제하지 않았다.
- 실제 테스트 정의 수: 현재 폴더368개(햄토리치 회귀3개 포함), `365a810 + Codex 9파일` 저장 후보365개.
  아래 365개 통과는 캐릭터 추가 전 완료된 검증이다. 최신 결과는 새 백업의 `working-tree/test-results.json`과
  `commit-candidate/test-results.json`, 각 `unittest.log`에서 확인한다. 두 범위를 고정 사본으로 각각 전체 실행한다.
  후보 사본은 Git에서 기본 소스를 읽고 Codex9파일만 적용한다. 원본 파일·Git index·working tree는 전환하지 않는다.
  결과가 실패/차단/원본 변경을 보고하면 저장 승인을 요청하지 않고 원인을 구분한다.
- 현재 로컬 기본 캐릭터는 햄토리치이며 토리는 계속 등록되어 있다. 이 변경은 별도 미커밋 작업이므로
  Codex9파일만 저장한 후보의 기본 캐릭터는 기존 토리다. 캐릭터 기능까지 GitHub에 저장한 것으로 보고하지 않는다.
- commit/push는 여전히 사용자 승인 전 대기. 환경·output·캐시·인증 정보·다운로드 자료는 저장 후보에서 제외한다.

## 2026-10-08 — Codex 안전 마무리 / commit·push 승인 대기

- 정확한 프로젝트: `C:\Users\young\OneDrive\Desktop\클로드코드\shorts-ai`.
  저장소 `https://github.com/young92133-cmd/ai-shorts`, 브랜치 `feature/agent-content-factory`.
  재개 시 로컬 HEAD와 fetch 후 origin 브랜치 모두 `365a810e3108086db09102826622e40b6398a3a9`, ahead/behind 0/0, 미커밋 0이었다.
  이전 28개 작업 파일은 다른 세션이 `7a7e0a9`(엔진)·`365a810`(문서)로 이미 저장했다. 이를 다시 구현하거나 되돌리지 않았다.
- 충돌 확인: 관련 Claude 세션 마지막 기록 21:54:24의 종료 이후 파일 해시·HEAD·세션 기록이 안정된 것을 확인하고 진행했다.
  실행 중인 프로세스를 종료하지 않았다. 별도 `shorts-ai-benchmark-v2` worktree는 그대로 보존한다.
- 백업: 저장소 밖 `../backups/ai-shorts-codex-20261008-220646/`.
  소스·운영 output·참고 자료·기존 로그·환경 설정 2,552파일, 1,356,097,100바이트를 복사해 원본/복사본 SHA256 일치를 확인했다.
  `repository.bundle` 전체 이력 검증 완료. 기존 기능 28파일 + Topic 운영 407파일을 임시 폴더에 복원해 435파일 해시 검증 완료.
  캐시·설치 패키지는 삭제하지 않고 원위치 보존, 버전 목록은 백업의 `dependency-versions.json`에 기록한다.
- 환경: 이 Codex에서 기존 `.venv` 실행은 여전히 불가(삭제된 Python312 경로). 원본은 변경하지 않았다.
  외부 `../.codex-envs/ai-shorts-py312/` Python 3.12.14를 만들고 `.pth`의 `site.addsitedir`로 기존 패키지를 재사용했다.
  직접 요구사항 17개 만족·`pip check` 정상, Claude SDK 0.2.157·Edge TTS 7.2.8·faster-whisper 1.2.1·PyAV 18.1.0 import 정상.
  FFmpeg/FFprobe 9.0.2 정상. `scripts/factory.ps1`는 복구 환경 및 `.pth` 처리와 실행 중 FFmpeg PATH 추가를 지원한다.
  도움말 성공 0·잘못된 명령 2·PATH/현재 폴더 복원 확인. Claude CLI 설치 위치만 확인했고 로그인/구독 호출은 검증하지 않았다.
  복구 환경은 기존 패키지 경로에 의존한다. 독립 재설치 환경이나 웹 UI 실행 복구까지 검증한 것으로 보지 않는다.
- 최소 수정: 데모 JSON의 가상 자료 안내를 결과의 일반 notice가 덮어쓰지 않도록 마지막에 기록한다.
  격리된 가상 자료 데모를 두 번 실행해 안내문·8장 계획·기존 결과 보존을 확인하는 회귀 1개 추가.
  엔진·운영 데이터·LLM 기본 공급자/모델·다운로드/인용 정책은 변경하지 않았다.
- 최신 전체 테스트: **365개 통과, 실패0, 오류0, skip0, 미실행0**.
  최신 소스를 저장소 밖 사본으로 고정하고 `.env`/사용자 settings 로딩·실제 HTTP/DNS·Claude 등 비FFmpeg subprocess·원본 쓰기를 차단했다.
  Windows asyncio의 로컬 socket과 임시 FFmpeg 테스트만 허용. 실제 FFmpeg 회귀 3개 포함, 외부 호출 시도0·테스트 중 원본 파일 변경0.
  최초 실행의 FFmpeg 3오류는 격리 실행기의 Windows executable=None 처리 오류였으며 실행기를 고쳐 전체 재실행했다.
  최종 결과/소스 사본/실행 로그는 백업 폴더의 `test-results.json`, `unittest.log`, `isolated_tests.py`에 보존한다.
- 실제 결과 재확인: 기존 `output/20261008_214102_85f2` 상태 render_complete, ai_calls=[];
  hybrid/card_01~08.png 모두 정상 PNG·1080×1350, manifest와 페이지별 근거 기록 존재.
  이번 작업에서는 실제 뉴스 재수집·Claude/OpenAI/Edge 서비스 호출·새 실제 콘텐츠 제작을 하지 않았다.
  실 뉴스 진위 재검증과 Topic→쇼츠/K-pop 실제 인용 제작 검증은 별도 승인 후 진행한다.
- 남은 한계: 공식 원문 자동 연결·사건일 추출·상시 주제 분류·JS 본문 수집·규칙 스토리 제목/숫자 맥락 개선.
  YouTube source_info 타임스탬프 덮어쓰기(run.py), Quote Guard의 근거 역할/질문 누락 경고 처리(quote.py),
  무자막 YouTube 오디오 다운로드와 문서 정책 불일치는 여전히 남아 있다. 이번에는 해당 정책/제작 코드를 수정하지 않았다.
- 다음: 최종 diff·민감정보/생성물 제외 확인 → 사용자 commit/push 승인 → 새 일반 commit·현재 브랜치 push.
  output·캐시·환경·외부 자료·인증 정보는 Git에 추가하지 않는다. reset/clean/stash/amend/rebase/force push 금지.

아래 섹션의 테스트 수·환경·미커밋 표시는 당시 기록이다. 현재 Git·환경·검증 기준은 위 섹션이다.

## 2026-10-08 (밤) — Topic Strategy V1 실운영 검증·안정화 (이후 7a7e0a9·365a810 저장)

상세: `docs/OPS_VALIDATION_2026-10-08.md`. 실제 뉴스 수집 32건(고유 25, 중복 병합 8), 검증 통과 1건(9월 소비자물가 — 국가데이터처 공식 원문 5문장),
그 주제로 8장 하이브리드 실제 제작 `output/20261008_214102_85f2/hybrid/`(AI 0회). 실데이터에서 발견한 수집·중복·점수·스토리·캘린더 결함을
`app/topics/{discovery,dedup,scoring,story,calendar}.py` 에서 수정하고 회귀 테스트 6개 추가. 이전 세션 기록은 전체 364개 통과·skip 0이다.
현재 Codex 환경 점검 및 최신 재검증은 위 섹션을 기준으로 한다.

## 2026-10-08 — Topic Strategy Engine V1 (구현 당시 기록, 이후 Git 저장)

기존 쇼츠·캐러셀 코드 위에 전략 계층을 추가했다. 아래의 기존 브랜치/커밋 기록은 **이번 변경 전 상태**다.

- 신규: `app/topics/`(schema/store/discovery/verification/scoring/dedup/semantic/story/business/calendar/engine/config),
  `app/factory/topics.py`, `tests/test_topics.py`, `scripts/demo_topic_strategy.py`, `docs/TOPIC_STRATEGY*.md`.
- 수정: CLI에 `topics` 추가, 기존 intent 확장, `core.make_planned_carousel` 추가,
  캐러셀 `run_carousel`에 optional `prepared_master/prepared_plan` 주입(기존 경로 기본값 유지), `config.yaml` 전략 설정.
- 뉴스/공식/통계: 기존 Naver/DDG 검색과 article 추출 사용, 확인된 공개 RSS 사용자 설정, robots·네트워크/리다이렉트 검사.
  후보의 발행일·수집일·사건일 구분. 출처는 기존 SourceRegistry에 연구용으로 등록하며 사진 사용 권한으로 승격하지 않음.
- 검증: 주요 주장에 원문 인용 일치·공식 1차 출처 또는 독립 신뢰 보도·기준일/단위·적용 대상·원통계를 요구.
  충돌/오래된 사건/근거 없는 제목 수치/과장/권한 문제는 자동 승인 불가. 캐시 재평가로 기한 연장하지 않음.
  뉴스 발행일 재수집 실패 또는 원문 변경은 보류·재승인. 복잡한 의미/법률 판단은 사람 보완 필요.
- 점수: 관심30/스토리25/실용25/사업20, 0~100, 기본80우선/65검토. 내부 추정값. `rank --ai`만 기존 LLM 호출(개발 중 미실행).
  의미 중복 AI는 사람 검토용 제안이며 자동 병합하지 않음. 동일 사건/주장 병합과 30/90일 발행 중복은 규칙으로 처리.
- 제작: 사용자 승인 fingerprint가 있는 주제만 8페이지 story → 기존 CarouselPlan/Renderer.
  기본 자체 그래픽·마스코트, 이미지 API/자료 검색 없음. 쇼츠 파생은 검증 원고를 기존 `make`로 넘김.
  원래 score/근거/plan은 audit 및 결과 `topic_strategy.json`에 보존. `--dry-run`은 전달 JSON만 내고 generated 아님.
- 승인 운영: `collect → rank → inspect/edit/verify → approve → plan/create → review → published`.
  `published`는 외부 게시가 아니라 사람의 발행 이력 기록. exclude/hold/release/schedule/명시적 followup 지원.
  번호는 사용자에게 보여준 selection_id에 묶음; 자연어 번호 제작 요청은 선택 승인으로 처리하되 사실 게이트 유지.
- 캘린더: 주3편/1~4주, 최근20슬롯9:7:4, 적격 부족 시 비움, 예약 주제 중복 방지, 분야 부족 우선·B2B 주간 후보.
- 단계별 확인: 수집7개 → 검증/평가16개 → 기존 Factory/Carousel 포함73개·86개 → B2B/캘린더+회귀64개 모두 통과.
- 최종 전체 회귀: **358개 중 355개 통과, 실패0, 기존 ffmpeg 테스트3개 skip**. 전략 신규50개 모두 통과.
  마지막 검증 로그: `final-topic-tests-complete.log`(Git 제외). 기존 기준308개도 동일 환경에서 실패0/skip3이었다.
- 비용/샘플: Claude·외부 뉴스 API·유료 이미지 호출0회, 비용0원. 실제 PNG 샘플 미실행.
  최종 `output/topic_strategy_v1_demo/`에는 가상 `.example` 근거로 생성한 10후보/상위3/1주3슬롯/4주12슬롯/8장 계획/전달JSON이 있다.
  실 뉴스가 아님을 모든 데모 문서에 명시하고 운영 저장소와 격리했다.
- 환경: 기존 `.venv/Scripts/python.exe`는 이전 PC 경로를 가리켜 실행 불가.
  제공된 Python 3.12 + 기존 `.venv/Lib/site-packages`를 PYTHONPATH에 넣어 검사했다. ffmpeg CLI 부재로 기존 실 ffmpeg 테스트3개는 skip.
  `scripts/factory.ps1`는 정상 가상환경 우선/현재 제공된 Python 대체 실행을 지원하며 `topics --help` 실제 실행 확인.
  실패 후 재제작에서는 현재 제작 결과만 발행 검사에 사용하고 이전 실패 기록은 보존한다. 기존 계획은 plan_history로 보존한다.
- 사용자 요청대로 commit/push하지 않았다. 초기 미커밋 파일 없었고 기존 output는 삭제하지 않았다.

## ★ 현재 상태 요약 (2026-10-08, 다른 PC 는 여기부터 읽는다)

- **브랜치:** `feature/agent-content-factory` (origin 과 동기화). 받기: `git clone --branch feature/agent-content-factory https://github.com/young92133-cmd/ai-shorts.git` 또는 `git pull`.
- **주요 커밋(수정 금지):** `daa97e7` Benchmark × V1 auto router · `d52393e` Source Resolver · Clip Analyzer · `00cd7a6` 자막 정렬 수정.
  2026-10-08 정리: `56e3d98` 캐러셀(카드뉴스·인스타툰) → `fcdfedb` transformative_quote 인용 모드·state evidence → 문서 정리 커밋(이 문서가 들어 있는 커밋).
- **테스트:** 전체 **308개 통과, 실패 0, skip 0** (`.venv\Scripts\python.exe -B -m unittest discover -s tests -q`).
- **Benchmark × V1:** 완료. `make` 기본 `--benchmark auto` → 조사 → Content Brief(사실/추론 분리, 시청 질문 후보, View Potential, 8개 profile 9기준 점수, YouTube 는 근거 구간 타임스탬프)
  → router(게이트·fallback) → 구조 주입 대본 → 장면 역할 → Edge TTS·자막·렌더. 결정은 `project_state.json` `benchmark`(selected_profile, candidate_scores, top3, reason_to_watch, viewer_question, claim, evidence, view_potential, selection_reason, quality)와 `benchmark_decision.json`.
- **8개 profile 전부 router 평가 대상.** 실제 MP4 검증: curiosity_update_story·mechanism_explainer·event_timeline_story. 근거 영상이 필요한 kpop/physics/ranked 는 권리 확인 영상이나 `--quote` 영상이 있을 때만 후보(실제 MP4 미검증). 현황은 `docs/BENCHMARKS.md` 맨 위.
- **Source Resolver (`--visuals auto` 기본):** Openverse · Wikimedia Commons(사진·영상) · NASA · Pexels/Pixabay(키 있을 때만) · 사용자 업로드 · AI 이미지(꺼짐 기본) · 자체 카드 fallback. YouTube 는 분석만.
  상태: licensed / public_domain / transformative_quote / reference_only / unknown. `sources.json` 에 source_type·url/path·usage·rights_status·rights_basis·purpose·attribution·scene_ids·clip_ranges·media_status. 검색 기록 `source_plan.json`.
- **transformative_quote (인용·비평·해설 모드):** 재사용 라이선스가 없어도 분석·비교·해설 목적이면 인용 후보. `make --url URL --quote 영상·캡처`. 근거 역할 장면에만, 최소 구간 재생 + 정지 화면 + 해설, 원본 소리 없음, `인용: 채널 · 제목`.
  렌더 전 `quote.guard`(해설·출처·비중·중복·질문 연결, 고정 초 규칙 없음, 상대 비율만) → `quote_plan.json`. 캡처 2장은 전/후 비교 레이아웃.
- **Clip Analyzer:** ffmpeg 샷 경계 · 무음 경계 · 자막(.srt/전사) 키워드 · benchmark 근거 시각 우선 · 이미 쓴 구간 회피 → 후보 구간·추천 시작/끝. 결과는 `source_plan.json`/`quote_plan.json`/`sources.json clip_ranges`.
- **자막 정렬 (`00cd7a6`):** Edge TTS 단어 경계 시간은 그대로, 자막 글자는 나레이션 원문(`tts/base.align_words`).
- **실제 검증 A~H:** A curiosity 84 25.2초 · B(YouTube) mechanism 90 32.9초 · C event_timeline 88 32.6초 · D(YouTube+공개 사진 4) mechanism 88 32.9초 · E(주제+사진 2) mechanism 92 27.3초 · F(NASA 영상 3+사진 1, resume) curiosity 87 26.2초 · G(여행 예능 링크, kpop 근거 영상 없어 제외) curiosity 85 25.1초 · H(직접 대본+`--quote`, 인용 3장면 부분 재생·정지) 17.8초. 상세 `docs/BENCHMARKS.md` §3.
- **이 과정에서 고친 문제:** B-roll concat SAR 불일치(`render._ninefix` `setsar=1`) · 도표/사진이 상단 제목과 겹침(`cards.fit_image` 22% 아래 배치) · 비유 장면에 엉뚱한 사진(검색어 비유 장면은 card, 시대 불일치 자료 감점, min_visual_fit 7) · 자막 글자 누락(align_words) · 같은 주소 재등록 시 권리 상태 덮어쓰기 · 인용 캡처 파일 잠김.
- **알려진 한계:**
  - Clip Analyzer 는 화면 의미를 보지 못한다. 자막·대사 없는 영상은 샷 안정성으로만 고르므로 원하는 장면(예: 발사) 대신 인물 클로즈업을 고를 수 있다(F 3번 장면). Vision 분석 없음.
  - Content Brief 도 텍스트(자막·설명·기사)만 본다. 표정·동작 같은 화면 근거는 판단하지 않는다.
  - YouTube 미디어는 약관상 자동 다운로드하지 않는다. 화면 인용은 사용자가 준 로컬 영상·캡처로만. **단, 기존 V1 코드는 YouTube 자막이 없으면 음성 인식용 오디오를 내려받는다**(`run.py` url 분기) — 유지 여부 미결정.
  - 인용 화면의 강조 박스·화살표·영상 2개 분할 화면은 미구현(캡처 전/후 비교만). 인용은 법적 판단을 대신하지 않으므로 게시 전 사용자 확인.
  - resume 은 화면 자료 검색을 다시 하므로 공개 자료 선택이 달라질 수 있다(rerender 는 timeline 그대로). 최신 기술 주제는 무료 공개 자료가 적어 카드 비율이 높다.
  - 마지막 질문 장면이 ✓ '정리' 카드로 나온다. 캐러셀 한계는 아래 2026-10-07 절.
- **다음 개발 후보(미구현, 사용자 요청 시):** Global Trend Radar · US/KR/JP Localization Engine · Vision 기반 Clip Analyzer · YouTube Studio 성과 피드백 · Pexels/Pixabay 실사 확대(무료 키) · 자동 업로드/게시.

## 2026-10-07 (밤) — transformative_quote 인용·재가공 모드

- 신규 `app/pipeline/quote.py`(인용 배치·전/후 비교 합성·렌더 전 guard), `tests/test_quote_mode.py`(16개).
- 수정: `sources.py`(상태 5종·QUOTE_LICENSE·purpose/attribution/media_status), `source_resolver.py`(상태·profile source_strategy·근거 장면 인용 후보·YouTube 권리/미디어 분리),
  `clip_analyzer.py`(prefer/avoid 구간), `bench_auto.py`(evidence_moments·근거 영상 게이트·인용 해설 지시·state 에 evidence/view_potential), `run.py`(타임스탬프 자막→brief, 인용 배치·guard, play),
  `timeline.py`/`render.py`(play → 부분 재생 후 정지), `visuals.py`(quote_source), `integration.yaml`(source_strategy·evidence_roles·quote_purpose), factory `--quote`·`--quote-source`·`--quote-reference`.
- 기존 테스트 6개는 예전 정책(BY-SA·YouTube=reference_only, 상태 "usable")을 확인하던 것이라 새 상태로 갱신.

## 2026-10-07 — 카드뉴스 · 인스타툰 · 하이브리드 캐러셀 (`app/carousel/`)

`make --format card_news|insta_toon|hybrid|all` 를 추가했다. 쇼츠 경로(`--format` 없음 / `shorts`)는 코드 흐름이 그대로다(`run.py` 무변경).

- **구조:** `gather_inputs`(쇼츠와 같은 research/article/youtube 모듈, `--research-file` JSON 추가) → `master.build_master`(AI 1회, 실패 시 자료 문장으로 규칙 생성)
  → `planner.plan_pages`(mix_ratio·skeleton 규칙 + AI 문구 1회 + `normalize` 로 첫 장 cover·끝 장 cta·6~10장·형식별 허용 타입·캐릭터 id·말풍선 위치 강제)
  → `visuals.find_card_images`(쇼츠 `source_resolver.resolve` 를 페이지=장면으로 그대로 호출, image 전용) + 렌더 직전 `guard_image`(소스 대장 usable 재확인)
  → `CharacterArtist`(업로드 `toon_NN_*` → Bible 참고 이미지 → AI(설정 시, `characters/<id>/generated/` 캐시) → `mascot.draw_mascot`)
  → `render.render_page`(Pillow, 타입별 RENDERERS, 실패 시 `render_safe`).
- **템플릿:** `app/carousel/templates/{clean_info,character_info,comic_hybrid}.yaml` — 비율 좌표·팔레트·글자 크기·페이지별 영역 덮어쓰기.
- **캐릭터:** `characters/tory_01/bible.json`(토리). `characters list|show|add`. AI 생성 캐시는 .gitignore.
- **factory:** `core._make_carousel`, `_finish_carousel`, `_copy_assets` 추출(쇼츠 동작 동일). `--format` 은 parser Action 으로 톤 값이면 `content_format` 으로 보낸다(기존 테스트 그대로 통과). `--tone`·`--request`(자연어, `intent.detect_output_format`)·`--template`·`--character`·`--pages`. 캐러셀 프로젝트는 resume/pack/capcut 거부, `inspect --part carousel`.
- **all:** 쇼츠를 먼저 만들고 `inputs_from_shorts`(script.json 나레이션 + 조사 목록)로 하이브리드. 조사는 1번. 쇼츠 실패 시에도 캐러셀은 만들고 `partial_failure`.
- **테스트:** `tests/test_carousel.py` 39개 추가 → 전체 **292개 통과**(기존 253 그대로).
- **실제 샘플 (Claude 구독, 유료 없음):** `output/20261007_225503_1732/hybrid/` "전세와 월세, 금리 시대에 뭐가 더 유리할까" — Master·Plan 모두 AI, story_score 0.35 → 카드 50/만화 50, 8장, 대체 0장.
  사진은 0장: 검색어 AI 가 표지·정보 카드를 prefer=card 로 판단해 검색을 건너뜀(쇼츠 Resolver 규칙 그대로) → 그래픽 카드로 대체됨.
  첫 렌더에서 발견해 고친 것: 말풍선과 캡션 겹침, 캡션 2줄 잘림, CTA 라벨 겹침, 이모지가 네모로 찍힘(📌), 비교 카드 글머리표만 남는 줄. 고친 뒤 같은 plan.json 으로 다시 렌더(추가 AI 호출 없음).
- **알려진 한계:** 마스코트는 정면 상반신 1종(옆모습·전신 없음). 클로즈업 컷에서 말풍선이 얼굴 일부를 가릴 수 있다. 캐러셀 재렌더 명령(plan.json 수정 후 다시 그리기)은 아직 없다. 웹 UI 에는 캐러셀 화면이 없다(CLI 전용).

## 2026-10-05 (저녁) — Source Resolver · Clip Analyzer · Rights Guard 변경

`make` 가 기본으로(`--visuals auto`) 장면마다 공개 영상·사진을 찾아 권리를 판정하고, 사용 근거가 확인된 자료만 화면에 쓴다.
`--visuals cards` 는 기존처럼 자체 카드만. 웹 UI(`run_pipeline(source_search=False)` 기본값)는 바뀌지 않았다.

- **흐름:** TTS로 장면 길이 확정 → 업로드·내 영상이 없는 장면에 대해 `source_resolver.resolve`
  → 검색어 계획(AI 1회: 장면별 영어 검색어·prefer video/image/card·must_show·자막 키워드, 비유 장면은 card)
  → discover(Openverse 이미지 CC0/PDM/BY 필터, Wikimedia Commons 이미지·영상, NASA 이미지·영상, Pexels/Pixabay 는 키 있을 때)
  → 권리 판정(`classify_license`) → usable 후보만 적합도 평가(AI 1회: visual_fit·evidence_fit)
  → 내부 점수 0~100(visual 30·evidence 15·quality 15·freshness 5·rights 20·editability 15) + profile `visual_priority` 가산
  → 장면별 선택(점수 ≥60, visual_fit ≥7, 같은 자료 중복 금지, profile `card_roles` 장면은 카드 유지)
  → usable 일 때만 ingest(80MB 제한, 미디어 타입·디코딩 확인) → 영상이면 Clip Analyzer → Scene Planner(`source_video`/`source_image`) → 기존 렌더.
- **권리:** usable 자동 = CC0 · 퍼블릭 도메인 · CC BY(화면 하단·설명란 출처) · NASA 제작 자료(제3자 저작권 표기 있으면 제외) · Pexels/Pixabay.
  reference_only 자동 = YouTube(표기와 무관) · CC BY-SA · NC · ND · 사용 제한 표기, unknown = 표기 없음. 레지스트리는 호출 쪽 주장보다 계산 결과를 우선한다.
- **YouTube 한계(보고):** YouTube 약관은 YouTube 가 제공하는 다운로드 외의 저장을 허용하지 않으므로 YouTube 영상은 CC BY 표기가 있어도 자동 ingest 하지 않는다(분석·참고만). 사용자 소유 영상은 원본 파일을 `--asset … --confirm-rights` 로 주면 기존 경로로 쓴다.
- **Clip Analyzer** (`clip_analyzer.py`): ffmpeg scene score 샷 경계, silencedetect 말 경계, NASA `.srt` 자막(있으면) → 장면 길이 창 후보 → stability·boundary·position·relevance 점수 → 겹치지 않는 상위 3개와 추천 구간. 자막 없는 영상은 화면 내용(의미)까지는 판단하지 못한다.
- **기록:** `sources.json` 항목에 source_type·usage(visual/reference_only/research)·rights_status·rights_basis·scene_ids·clip_ranges. 가공본(장면 이미지)을 쓰면 원본에도 장면 번호가 남는다. `source_plan.json` 에 장면별 검색어·후보·점수·제외 사유(reference_only/unknown 근거)·선택·오류.
- **파일:** 신규 `app/pipeline/source_resolver.py`, `app/pipeline/clip_analyzer.py`, `tests/test_source_resolver.py`(19개).
  수정: `models.SourceItem`(새 필드, 기본값으로 과거 sources.json 호환), `sources.py`(PROVEN_LICENSES·CC BY 출처 필수·`mark_used`), `visuals.py`(resolved 우선순위·licensed_source), `run.py`(5-A 단계·타임라인 영상 구간·meta 출처), `youtube.py`(license 필드), `cards.fit_image`(도표가 상단 키워드와 겹치지 않게 22% 아래 배치), `render.py`(**setsar=1** — 가로 영상 축소 반올림 SAR 로 concat 실패하던 기존 B-roll 버그), `config.yaml` `sources:`, `integration.yaml`(profile별 visual_priority·card_roles·visual_hint), factory `--visuals`.
- **자동 테스트:** **247개 통과**(Benchmark×V1 228 + Source Resolver 19). 실제 ffmpeg 회귀 테스트 2개(샷 검출, 홀수 크기 영상+이미지 concat) 포함 — SAR 테스트는 수정 전 코드에서 실패함을 확인했다.
- **실제 제작 (Claude 구독 + Edge TTS + 공개 API, 유료 없음, 모두 `verify_factory_v1.py --verify` 통과·장면 시트 확인):**
  - D YouTube URL `ZUZqIWVgw2k` → `20261005_171137_be9d` mechanism_explainer 88점, 32.9초. YouTube 원본은 `reference_only`(재사용 라이선스 표기 없음)로 기록, 다운로드 없음. Commons 이미지 4장면(퍼블릭 도메인 3, CC BY 4.0 1 — 출처 표시), 맞는 자료가 없는 장면(최고 54점)은 카드. 도표·상단 키워드 겹침을 발견해 `fit_image` 수정 후 rerender 로 확인.
  - E Topic "최근 화제가 된 기술 하나" → `20261005_171742_b5cb` mechanism_explainer 92점(HBM/HBF 메모리), 27.3초. Commons 이미지 2장면(SSD CC BY 4.0, 퍼블릭 도메인 1). 5번 장면에 대본의 비유('책상 옆 서가')를 따라 1900년대 도서관 판화가 골라진 것을 확인 → 검색어(비유 장면은 card)·적합도(비유·시대 불일치 4 이하) 지침과 min_visual_fit 7 로 강화.
  - F(추가) Topic "NASA 아르테미스 2호 유인 달 비행 준비 근황" → `20261005_172334_074f` curiosity_update_story 87점, 26.2초. 첫 렌더가 SAR 불일치로 **실패**(실제 영상 경로 첫 사용) → `render.py` 수정 + 회귀 테스트 → `resume` 으로 완성. NASA 퍼블릭 도메인 **영상 3장면**(Clip Analyzer 구간 00:13.8-00:18.2, 00:27.0-00:30.3, 00:03.2-00:06.7) + 이미지 1장면, 원본 소리 없이 나레이션만. benchmark 결정은 resume 후에도 유지.
- **알려진 한계:** 자막 없는 영상의 구간은 샷 안정성으로만 고른다(F 3번 장면은 발사 영상 중 우주비행사 클로즈업 구간이 선택됨, 원본 자막 그래픽 포함). 최신 기술 주제는 무료 공개 자료가 적어 카드 비율이 높다 — `PEXELS_API_KEY`(무료) 를 넣으면 스톡 영상이 추가된다. Commons 4K 원본만 있는 영상은 80MB 제한으로 건너뛴다. Edge TTS 단어 경계 때문에 자막 글자가 빠지는 기존 V1 버그를 발견해 별도 작업으로 분리했다(이 커밋에 포함하지 않음).
- **AI 호출:** make 1편당 brief·대본·장면 + 검색어·적합도 = 5회(모두 Claude 구독).

## 2026-10-05 (오후) — Benchmark × V1 자동 통합

`make --topic/--url/--auto/--reference-video` 가 기본으로 8개 benchmark profile 중 하나를 자동으로 골라 그 구조로 대본·장면을 만든다(`--benchmark auto`, 기본값).
사용자는 profile 이름을 몰라도 된다. 웹 UI(`jobs.py`)는 `run_pipeline(benchmark="off")` 기본값이라 동작이 바뀌지 않았다.

- **흐름:** 조사 → `bench_auto.analyze_brief`(AI 1회: verified_facts / inferences 분리, 시청 질문 후보 2~3개와 View Potential 5항목×20점, 8개 profile 9기준×10점, 구조별 보충 검색어)
  → `route`(가중합 0~100, 결정적 게이트: 권리 확인 영상이 필요한 kpop/physics/ranked 는 그런 영상이 없으면 제외, 필수 근거 슬롯 부족·근거 확보도 4 미만 제외, 최고점 45 미만·AI 실패면 `illustrated_fact_explainer` fallback)
  → `pick_candidate`(View Potential 최고 후보) → 선택 구조 보충 조사 1회(LLM 없음)
  → `compose_prompt_block`(beat 역할·시간·글자 예산·훅/페이싱/결론/마지막 질문, 사실·추론·창작 분리, 원본 복제 금지) → 기존 `write_script` 에 주입
  → 기존 `annotate_script` → `apply_scene_plan`(beat_role 로 장면 역할·content_kind·강조 길이) → 기존 TTS·카드·자막·렌더.
  benchmark 가 켜지면 기존 `make_plan` 을 건너뛰어 AI 호출은 3회 그대로다.
- **파일:** 신규 `app/pipeline/bench_auto.py`, `benchmarks/v1/integration.yaml`(profile별 beats·research_needs·narration_mode·훅/결론 전략·가중치·fallback; 기존 profile YAML은 수정하지 않음 — `benchmarks/*.yaml` 은 profile 로더가 읽으므로 하위 폴더에 둠), `tests/test_benchmark_auto.py`(26개).
  수정: `models.Scene.beat_role`(기본 ""), `script.write_script(benchmark_block, benchmark_scenes)`, `script_split.annotate_script`(beat_role 유지), `run.run_pipeline(benchmark=...)` + `_choose_benchmark`, `factory/core.py`(`make(benchmark="auto")`, `state["benchmark"]`, `inspect --part benchmark`, 과거 프로젝트는 `{"mode":"off"}`), `__main__.py`/`batch.py`(`--benchmark`), 기존 `tests/test_factory.py` 공통 setUp 에 brief AI mock 추가.
- **저장:** `project_state.json` 의 `benchmark`(요약) + `benchmark_decision.json`(사실·추론·후보 점수·원본 분석·보충 조사·quality). resume/rerender/batch-resume 은 다시 고르지 않는다. 직접 대본은 `not_applicable`, `--style` 지정 시 auto 는 스타일 우선.
- **자동 테스트:** 기존 202개 + 신규 26개 = **228개 통과**(83초).
- **실제 제작 3편 (Claude 구독 + Edge TTS, 유료 API 없음, 모두 `verify_factory_v1.py --verify` 통과·장면 시트 확인):**
  - A Topic "최근 화제가 된 AI 기술 하나" 30초 → `20261005_164635_c740` **curiosity_update_story 84점**(2위 event_timeline 76, 3위 mechanism 72). 25.2초 / 7장면 / 자막 18줄. 질문 "AI가 마우스를 직접 잡고 그림을 칠해 준다는데…". 대본이 훅(결과)→과거→변화→현재→결론(추론은 '~로 보여요')→질문 순서. 목표 30초보다 짧음(글자 예산 190자 기준).
  - B YouTube URL `ZUZqIWVgw2k`(웹 망원경 분광학) 35초 → `20261005_165012_0833` **mechanism_explainer 90점**(2위 illustrated 85). 32.9초 / 7장면 / 자막 20줄. source_analysis(원본 훅·구조·볼 이유) 기록, 원본 다운로드 없음. 숫자 카드·비교 카드 사용. 장면 순서가 원본 설명 순서와 비슷함(문장은 새로 씀).
  - C Topic "1912년 타이타닉호 침몰 과정" 35초 → `20261005_165421_c7c8` **event_timeline_story 88점**(2위 illustrated 81). 32.6초 / 7장면 / 자막 21줄. 날짜·시각이 verified_facts 와 일치. 결론 장면이 훅의 질문(왜 그 시계가)에 부분적으로만 답함.
  - 세 편 모두 서로 다른 profile 이 자동 선택됐고 quality 경고 없음, fallback 없음.
- **사고 기록:** 구현 중 전체 테스트를 처음 돌렸을 때 기존 factory 테스트가 brief AI 를 mock 하지 않아 **실제 Claude 구독 호출이 약 9회** 발생했다(테스트용 가짜 자료, 유료 API 아님). 테스트를 중단하고 공통 setUp 에 mock 을 추가했다. 규칙을 CLAUDE.md/AGENTS.md 개발 규칙에 남겼다.
- **알려진 한계:** 마지막 질문 장면이 ✓ '정리' 요약 카드로 나온다(질문 전용 카드 없음). 짧은 영상에서 목표 길이보다 10~20% 짧게 나올 수 있다. Clip Analyzer·자동 영상 소스 탐색은 이 절 이후 작업.

## 2026-10-05 — 전체 Benchmark Audit 및 오프라인 엔진 통합

사용자가 shorts-ai 현재 브랜치의 오프라인 엔진을 기준으로 통합하도록 선택했다. 별도 shorts-ai-benchmark-v2는 조사만 했으며 파일/작업/커밋을 병합하지 않았다.

- **자료/구조:** 현재 PC의 Claude 프로젝트 전체 JSONL, Codex 벤치마킹 대화 및 원 개발 대화, 문서/설정/코드/테스트/Git 이력/output 분석 메모를 조사했다. `docs/BENCHMARKS.md`에 코드 변경 전 Audit와 변경 후 인벤토리를 구분한다. 다른 PC에만 있는 기록의 존재까지 확인한 것은 아니다.
- **source 6개:** 돌토리, 짤잉, 레스기, BKS Simulation, 건축매니아(2편), reference.mp4 제작 시스템(12종 스타일+도구 기능). 반복/중단 분석을 별도 source로 중복 집계하지 않는다. `benchmarks/sources/*.json`에 분석 날짜/관찰 깊이/구조/채택 요소/복제 제외/연결 profile을 기록한다.
- **production profile 8개:** kpop_observation_clip, curiosity_update_story, physics_comparison_simulation, ranked_moments, mechanism_explainer, quote_context_story, illustrated_fact_explainer, event_timeline_story. K팝 기존 YAML/관찰/계획/state 로딩을 유지하고 새 profile은 `benchmarks/profiles/*.yaml`에 둔다. 채널명은 production 이름으로 쓰지 않는다.
- **연결:** `app.factory benchmark sources/profiles/plan/inspect/render`. K팝 기존 클립 adapter 유지, 랭킹/물리 비교는 전체 근거 영상 순서 재생, 나머지는 사용자가 새로 쓴 사실/발언 요약/시간 흐름의 자체 카드로 기존 timeline/B-roll/ASS 렌더까지 전달한다. TTS/LLM/다운로드 호출 없음. `inspect`의 benchmark에는 장르 공통 12필드가 나온다. profile snapshot과 근거/권리/hash를 매 렌더 검증한다.
- **검증:** 변경 전 기존 170개(V1 132 + 기존 Benchmark38) 통과. 이번 신규32개 포함 **전체202개 모두 통과(61.749초), 실패0/skip0**. 로그: `output/benchmark_full_tests.log`. FFmpeg/FFprobe/AI/TTS는 mock; 실제 MP4/가독성/음질/흥행은 미검증. 새로운 카드와 영상이 함께 기존 FFmpeg graph로 전달되는 회귀도 검사한다.
- **제한:** Benchmark는 V1 make/resume/export/batch 및 웹 UI에 합치지 않은 독립 상태 경로다. 새 story는 무음 카드 변형이고 관찰한 원본 narration을 재현하지 않는다. Blender 실험 자동 생성, 사실 진위/조건 통제의 의미 검증, 외부 원본 수집, 일러스트/3D/지도/원음 인터뷰, 롱폼16:9/번역 자동화 미구현. 요즘PD는 목록만 관찰돼 production profile을 새로 만들지 않았다. Global Trend Radar/Localization/성과 feedback은 향후 단계다.
- **Git:** 이번 요청은 테스트 성공 후 현재 브랜치의 새 commit과 일반 origin push를 허용한다. 기존 history 수정/amend/rebase/force push 없음. output/미디어/환경/인증 파일 제외. 이전 기록은 아래에 보존한다.

---

## 2026-10-02 — V2 Benchmark Engine 1단계 (오프라인 관찰 입력)

사용자의 새 요청으로 V2 첫 기능을 구현했다. V1의 `make/information/story/issue`는 유지한다.
이번 구현의 공개 경로는 `app.factory benchmark profiles/plan/inspect/render`이고, 구조적 프로필은
`benchmarks/kpop_observation_clip.yaml`, 사용법과 현재 PC 실행 준비는 `benchmarks/README.md`에 있다.

- **범위:** 사용자 관찰 메모 JSON의 시청 이유/claim과 evidence clips를 쌍으로 검증·선택한다. 6개 관점을 지원하고 비교·변화·공통점에는 독립된 관점의 근거 2개를 요구한다. 시간 범위·중복·확신도·전체 근거가 들어갈 길이를 검사한다. 원본 영상을 자동 이해하거나 주장 진위를 판정하는 AI 분석은 이번 경로에 없다. `semantic_verification=user_annotations_only`, confidence는 선언된 근거 확신도의 최솟값이다.
- **파일:** `app/pipeline/benchmark.py`, `benchmark_models.py`, `app/factory/benchmark.py`, `benchmarks/` 프로필/가이드/입력·계획 예시, `tests/test_benchmark.py`를 추가했다. 기존 Factory CLI, `render.py`, `timeline.py`, `subtitles.py`, `sources.py`에 필요한 옵션만 추가했다. `licensed_upload`는 명시적으로 허가받은 로컬 입력이며 기존 권리 확인 조건을 모두 충족해야 한다.
- **저장/렌더:** `output/benchmarks/<id>/`의 별도 상태·프로필 스냅샷·claim/evidence·거부 사유·SHA256·권리 대장. 기존 B-roll/ASS/카드 텍스트 레이아웃을 재사용한다. 1080×1920, 기본 30초/20~35초, TTS 없음, 원본 소리 선택, 자체 남색/주황색 브랜딩. 근거 화면 전체를 영역 안에 맞추고 근거 밖을 가져오지 않는다. 선택한 근거 전체를 first_evidence/interpretation에서 보여주고 여유 구간은 다시 보기로 기록한다. 매 렌더에서 권리·파일·범위를 재검사하고 임시 MP4의 해상도/길이를 검증한 뒤 최종 파일로 교체한다. 실패하면 계획과 기존 완성본을 보존한다.
- **검증:** 개발 전 기존 132개 통과(24.398초), 새 benchmark 테스트 38개 통과, 변경 후 전체 **170개 통과(25.221초)**. `benchmark profiles` stdout JSON/종료코드와 구조적 계획 예시 생성도 실제 실행했다. FFmpeg/FFprobe/AI는 테스트에서 mock 처리했고 실제 MP4·실제 K팝 근거·음악 연결·가독성·흥행 효과는 미검증이다. 로그: `output/benchmark_v2_stage1_unittest.log`.
- **실행 환경:** 이동된 `.venv`의 이전 Python312 경로가 없어서 Codex 번들 Python 3.12.14와 `.venv/Lib/site-packages`를 PYTHONPATH로 사용했다. `.venv`, 패키지, 기존 원본/출력 파일은 수정하지 않았다. 현재 PC 준비 명령은 가이드에 있다.
- **경계:** 유료 API/Claude 구독 실호출/영상 자동 다운로드/실제 샘플 제작/GitHub push/기존 커밋 변경 없음. 이번 경로는 웹 UI·CapCut·V1 resume/export에 연결하지 않았다. 작업 도중 별도로 나타난 `app/benchmarks/`와 `app/pipeline/llm.py` 변경은 이 오프라인 구현에 포함시키거나 되돌리지 않고 보존했다. 이번 공개 명령은 그 별도 모듈을 import하지 않는다.

이 절은 아래 PC 이동 체크포인트 이후의 새 기능 기록이다. V2 전체 완료나 실제 제작 검증 완료를 뜻하지 않는다.

## 2026-10-01 — 다른 PC 이동용 체크포인트 (현재 인계 기준)

**이번 저장은 이동용 WIP 체크포인트이며 V1 release나 최종 완료 승인을 의미하지 않는다. 다음 개발·기능 추가는 사용자의 새 요청을 기다린다.** 이 절의 이동·백업 지침이 아래 이전 작업 기록보다 우선한다.

- **실제 출발 상태:** `feature/agent-content-factory`, 로컬 `b5772eb`(`feat: complete V1 content factory workflows and validation`), 원격 추적 기준 `c6cd645`보다 1커밋 앞섬. 미커밋 변경·미추적 파일·충돌 없음. 사용자가 예상한 미커밋 V1 변경은 이미 이 기존 로컬 커밋에 들어 있었다. 기존 커밋은 amend하거나 되돌리지 않는다.
- **체크포인트:** `wip: checkpoint content factory v1 for pc transfer`라는 새 커밋에 이 인계 안내와 `.gitignore` 보강을 저장한다. 사용자의 이번 명시적 요청으로 현재 브랜치의 기존 미전송 커밋까지 GitHub에 일반 push한다. force push·release·tag는 만들지 않는다. 실제 push 성공과 로컬/원격 해시 일치는 실행 후 최종 답변으로 확인한다.
- **재검증:** 전체 `unittest discover -s tests -q` **132개 통과**(24.322초). 요청의 기준 131개보다 1개 많다. 로그는 Git 제외 `output/pc_transfer_unit_tests.log`. 이번에는 실제 영상 제작·AI 호출·V1 기능 수정은 하지 않았다. 아래 실제 제작/완료 기록은 이전 작업에서 남긴 기록이며 이번 체크포인트의 새 완료 판정은 아니다.
- **보존 범위:** `app/`, `tests/`, `scripts/`, `CLAUDE.md`, `AGENTS.md`, `README.md`, `IMPLEMENTATION_PLAN.md`, `HANDOFF.md`, `requirements.txt`, `.env.example`, `config.yaml`, `presets/`, `styles/`, 실행 CMD와 기존 개발 문서를 포함한다. 추적 대상 86개 파일에 대한 키·토큰·개인 키 및 비밀값 할당 패턴 검사에서 발견 파일 없음. 추적 대상에 인증 파일·output·가상환경·10MB 초과 파일 없음.
- **assets 분류:** 실제 파일은 `assets/fonts/README.md`, `assets/bgm/README.md` 2개뿐이며 모두 추적 중이다. 미추적 고정 테스트 자산(A)이나 일회성 생성 결과물(B)은 없었다. 필요한 안내 문서를 보존하고 assets 전체를 ignore하지 않는다.
- **로컬에만 보존:** `.env`와 개인 인증 정보, Claude/OpenAI 로그인 정보, `.venv/`, Python·도구 캐시, 임시 파일, `output/` 전체(테스트 MP4·렌더 중간파일·대본/작업 상태·실사용 보고서), 원본 참고 영상. 삭제하거나 초기화하지 않는다. GitHub에서 clone하면 이전 영상과 진행 중인 제작 작업 목록은 복원되지 않는다. 해당 산출물까지 옮기려면 별도로 복사해야 한다.

### 새 Windows PC에서 받기

Git, Python **3.12**(현재 검증 환경 3.12.10), FFmpeg/FFprobe, Claude Code CLI 또는 CLI가 번들된 Claude 앱을 준비한다. 기본 Windows 한글 폰트는 맑은 고딕이며 다른 OS에서는 `config.yaml`의 폰트를 설치된 폰트로 맞춘다.

```powershell
git clone --branch feature/agent-content-factory --single-branch https://github.com/young92133-cmd/ai-shorts.git
cd ai-shorts
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.pipeline.llm login
.\.venv\Scripts\python.exe -m app.pipeline.llm status
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
```

새 PC에서는 Claude 구독 브라우저 인증을 다시 한다. 기본 Claude 구독+Edge TTS 경로에는 API 키가 필요하지 않다. 선택 기능의 키가 필요할 때만 `.env.example`을 `.env`로 복사하여 새 PC에서 직접 설정하며 Git에 넣지 않는다. 로컬 Whisper 참고 영상 분석은 첫 실행 때 모델을 내려받고 CPU로 실행하므로 CUDA는 필수가 아니다. 의존성은 `requirements.txt`의 PyAV `<19` 조건을 유지한다. 받은 뒤 이 인계 문서와 현재 상태를 먼저 확인하고 사용자가 요청한 다음 작업만 시작한다.

## 2026-10-01 — V1 기능·실사용 검증 완료 (이전 작업 기록)

**V1 완료 조건을 검증했다. V2 영상 품질 개발은 별도 요청 전에는 시작하지 않는다.** 아래 9월 기록의 작업 순서를 이 절이 대체한다.

- **Git 출발점·체크포인트:** `feature/agent-content-factory` / `c6cd645`. 작업 시작 전 clean, 추적 파일 키·토큰 패턴 없음, `.env`·영상·output 추적 없음 확인 후 요청대로 일반 `git push origin feature/agent-content-factory` 실행 → `Everything up-to-date`. force/amend/다른 브랜치 변경 없음. V1 완료 변경은 이 문서가 포함된 **로컬 체크포인트 커밋**으로 기록한다. 새 변경의 push는 하지 않는다. Git 작성자 설정이 비어 있어 `c6cd645`의 작성자 정보를 이번 커밋에만 사용한다.
- **환경:** Python 3.12.10, ffmpeg·ffprobe 9.0.2 실제 실행 정상. PATH에 없더라도 기존 `require_ffmpeg()`가 WinGet 설치를 찾는다. `faster-whisper` 1.2.1, PyAV 18.1.0, small 전사 모델 준비 완료. PyAV 19의 제거된 인자로 실제 오류가 나서 `av<19`를 requirements에 반영했다. CUDA 라이브러리가 없어 자동 GPU 선택도 실패했으므로 CPU int8을 기본으로 바꾸고 원본 언어를 자동 감지한다. 실제 한국어 전사 34단어 확인.
- **인증:** 사용자의 CLI 인증 요청으로 로그인 절차를 실행했고 `Login successful`, `loggedIn:true`, `authMethod:claude.ai`, `apiProvider:firstParty`를 확인했다. 앱 번들 CLI는 현재 `%APPDATA%/Claude/claude-code/2.1.284/claude.exe`. `python -m app.pipeline.llm login`도 `--claudeai`로 구독 인증을 선택한다. **키·인증 코드를 출력하거나 유료 API로 우회하지 않는다.**
- **현재 구현:** Factory의 `claude/openai/auto` 선택, 유료 OpenAI 허용+키 가드, 구독 호출에 Anthropic API 키/토큰 제거, 전환 가능한 오류 제한, 프로젝트 `ai_calls/ai_provider_used/ai_providers_used` 기록. auto는 성공한 전환 공급자를 한 제작 동안 유지한다. 응답·스키마·거부 때문에 공급자를 전환하지 않는다.
- **입력·명령:** `make --reference-video`(200MB, 원본은 참고용만), `--format information|story|issue`, `--allow-openai`, `batch --topic ... --count N` 또는 `--select ... --candidates ID`, `batch-status`, `batch-resume`. 후보 목록은 `output/_factory/trends_*.json`, 순차 결과는 `batch_*.json`이다. 한 편 실패해도 다른 성공 영상은 보존한다. 엔진은 재작성하지 않았다.
- **무료 기본값:** Factory는 이미지 API를 끄고 기본 TTS는 Edge다. 환경 키만으로 Gemini/OpenAI 비전·전사를 호출하지 않는다. OpenAI TTS도 명시적 OpenAI 허용을 요구한다. 기존 엔진의 카드·기본 줌/전환·자막을 재사용한다.
- **상태 보존:** make/resume 결과 검증 오류도 failed로 저장한다. `resume` id 생략 시 최신의 이어 만들 수 있는 작업을 고른다. 참고 영상은 resume 때 재분석하지 않고 실제 화면에서도 제외한다. 이전 `ai_provider_used:null`은 성공한 AI 호출이 없었던 결과이며, 새 상태는 `none`으로 명시한다.
- **자동 테스트:** 기존 95개 + 신규 37개 = **132개 통과**. 로그 `output/v1_unit_tests.log`. 처음 발견한 기존 참고 영상 테스트 실패는 Factory 비용 가드를 유지하면서 기존 env 목 경계를 복원해 해결했다. 기존 테스트를 삭제하거나 약화하지 않았다. `pip check`도 충돌 없음.
- **실제 제작:** `output/20261001_213706_969f/final.mp4` — 창작 사연 직접 대본, **17.9초 / 1080×1920 / 4장면 / 자막 12줄**. 실제 무료 Edge TTS+FFmpeg 사용. `scripts/verify_factory_v1.py --verify 20261001_213706_969f`에서 전체 디코딩·자막·타임라인·완료 상태·권리 가드 통과. 확인용 `v1_scene_sheet.jpg` 및 `v1_check_frames/` 생성. Claude 분할은 인증 실패해서 기존 문장 경계 대체를 사용했으므로 **AI 성공 영상으로 세지 않는다.**
- **실제 검토→resume:** `output/20261001_215700_5bf6/final.mp4` — 하늘·노을 설명 직접 대본, **36.4초 / 1080×1920 / 7장면 / 자막 25줄**. 검토 대기 때 MP4 없음 확인, status/inspect 저장, resume 전후 `script.json` SHA-256 동일. 실제 TTS·렌더·전체 디코딩·공급자 기록(`none`)·권리 가드 통과. 장면 시트 직접 확인. 자동 대본 생성 검증으로 세지 않는다.
- **기타 실제 확인:** 사연 영상의 `rerender` 성공. Google 화제 조회 `trends --limit 5`와 번호·후보 id 저장 성공. 초기 YouTube 참고 URL 1개는 접근 실패했으나, 공개 자막 수집이 가능한 `https://www.youtube.com/watch?v=ZUZqIWVgw2k`로 실제 URL 제작을 통과했다. 외부 원본 영상은 최종 화면에 쓰지 않았다.
- **실패 보존:** `output/20261001_213049_779e/`는 새 정보형 주제의 대본 생성 전 인증 실패, `failed_at:research_complete`, `next_action:make`. 실패 폴더를 지우지 않는다.
- **최소 5편 실제 AI 검증:** A 정보형 `20261001_223329_2c25`(39.81초), B 창작 사연 `20261001_223524_9bb0`(38.76초), C USB-C `20261001_223702_97cf`(35.83초), D YouTube `20261001_224158_2399`(36.87초), E 화제 군함 `20261001_223845_0dfc`(37.57초) 모두 통과. 모두 1080×1920, TTS·자막·전체 디코딩·타임라인·완료 상태·실제 공급자 `claude`·권리 가드 정상. A 새 주제 review→resume에서 대본 SHA-256 동일. 장면 시트 직접 확인. 보고서 `output/v1_report_20261001_223329_1b88.json`, `output/v1_report_20261001_224158_d1a2.json`.
- **추가 입력 실제 검증:** F 자동 소재 `20261001_224506_e485`(38.59초), G NASA GPS 웹 URL `20261001_224717_c9d6`(37.43초), H 직접 만든 USB-C 영상의 참고 업로드 `20261001_224906_545a`(36.58초)도 동일 검증 통과. H는 CPU 로컬 전사와 Claude 요약을 사용했고 참고 원본은 화면에서 제외했다. 보고서 `output/v1_report_20261001_224506_5011.json`. 총 **Claude 실제 제작 10편 + 직접 대본 2편**을 만들었다.
- **실제 두 편 순차 검증:** 후보 목록 `trends_20261001_223845_106f`의 2번 군함·4번 김예지를 `batch --review`로 생성. `batch_20261001_225231_3abf`에서 대기 2편·완료 0편·MP4 없음 확인 → `batch-resume` 순차 완료 2편·실패 0편. 두 대본 SHA-256 동일, 각 MP4 전체 검사 통과. 결과 `20261001_225231_9178`(39.13초), `20261001_225420_11ff`(40.73초). 기록 `output/v1_batch_validation.json`, 각 폴더의 `v1_verification.json`. 순차 실패 보존은 외부 호출 없는 회귀 테스트로 검증했다.
- **검증 범위·제한:** 위 영상 모두 1080×1920·무료 Edge TTS·내부 카드·기본 자막/전환, 실제 공급자는 Claude 구독이다. 장면 시트와 전환 프레임을 확인했다. OpenAI 실호출은 유료 사용 미승인으로 하지 않았고 공급자 선택·허용 가드·전환 조건은 목 테스트다. 날짜·뉴스 주장·숫자의 자동 팩트체크는 V1에 없으므로 게시 전 출처 확인이 필요하다. 여러 URL 통합·자동 게시·고급 스타일은 미구현이다.
- **다음 작업:** 사용자가 요청한 V1 유지보수 또는 실제 제작만 진행한다. V2와 새 변경 push는 별도 요청 전에는 시작하지 않는다.

### 재현 명령

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe scripts/verify_factory_v1.py --cases A B C D E --youtube-url "실제 참고 영상 URL"
.\.venv\Scripts\python.exe scripts/verify_factory_v1.py --verify 작업번호
.\.venv\Scripts\python.exe -m app.factory batch --select 2 4 --candidates 후보ID --review
.\.venv\Scripts\python.exe -m app.factory batch-resume 묶음ID
```

실제 제작은 이번 사용자 요청에서 허용됐다. 유료 API·자동 게시·새 변경 push는 미승인이다.
이하 내용은 9월 인계 이력이다.

> 이 문서만 읽고 바로 작업을 이어갈 수 있도록 쓴 **개발자/AI용** 문서입니다.
> 사용자용 사용법은 [`README.md`](README.md)에 있습니다. 중복되는 내용은 그쪽을 참고하세요.
>
> **최종 갱신: 2026-10-01 — GitHub 체크포인트 준비 및 AI 공급자 구조 분석.** 아래 2026-10-01 절이 현재 상태다. 그 아래 A0·2D·2C·2B·2A·1단계 기록은 당시 이력으로 읽는다.

## 2026-10-01 — 현재 상태와 다음 작업 (최신)

### 프로젝트·완료 기능·Git

- 한국어 9:16 쇼츠를 주제/유튜브·기사 URL/완성 대본/화제 키워드에서 조사·대본·장면 설계·TTS·권리 확인 화면·자막·FFmpeg MP4까지 만드는 개인용 콘텐츠팩토리다. Claude Code와 Codex 채팅이 기본 조종 화면, 웹 UI는 결과 확인·수정용 보조 화면이다. `app/factory`는 JSON 명령층, `app/pipeline`은 공통 제작 엔진이며 웹 UI도 이 엔진을 사용한다.
- 소스 대장, 2A~2D, Factory `make`/`resume`/`status`/`inspect`/`rerender`/`styles`/`trends`/`export`/`edit-scene`/`set-visual`이 구현됐다. 저장 대본 재개는 재조사·재작성을 하지 않는다. Factory 완료 시 `job.json`을 만들어 웹 목록에 연결한다. 실제 A·C·D·E와 저장 대본 검토→재개→42.61초 1080×1920 MP4는 아래 A0 기록대로 확인했다.
- 브랜치 `feature/agent-content-factory`, 원격 `origin` = `https://github.com/young92133-cmd/ai-shorts.git`. 직전 커밋 `c6cd645`는 이미 같은 이름의 GitHub 브랜치에 push돼 있었고, 점검 시작 때 추적 파일 변경·삭제·staged 파일은 없었다. 이번 체크포인트는 **HANDOFF.md와 아래 신규 소재 7개 파일**만 포함한다. 커밋·push 후 실제 커밋 ID와 작업 폴더 상태를 다시 확인한다. 이전 브랜치·커밋을 수정하거나 force push하지 않는다.
- 이번에 새로 확인한 `assets/cat-box-45s/`: `narration.txt`(5문장 한국어 대본), `storyboard.md`(5장면 시간표·출처 URL·ImageGen 제작 주장), `scene_01_delivery.png`(택배 상자), `scene_02_peek.png`(상자에서 고개 내민 고양이), `scene_03_shelter.png`(은신처), `scene_04_sleep.png`(휴식), `scene_05_outro.png`(02의 동일 이미지 재사용). PNG는 각각 941×1672이며 총 5개 파일 중 마지막은 02와 바이트 단위로 같다. **소재 초안**이고 현재 Factory의 소스 대장이나 특정 프로젝트에 연결하거나 MP4로 렌더한 증거는 없다. 생성 경위는 `storyboard.md`의 기록에 근거하며, 대본의 연구 주장과 사용 권리·출처는 게시 전에 별도 확인해야 한다.
- 이 체크포인트에서 기존 프로그램 코드는 수정하지 않았다. `HANDOFF.md`는 현재 Git·소재·공급자 분석을 추가했고, 기존 설계·검증 이력은 아래에 보존했다.

### AI 공급자 분석과 우선순위 변경 (설계만, 미구현)

- `config.yaml` 기본 `llm.provider: claude`, `model: claude-opus-5`. `app/pipeline/llm.py:ask_structured`가 Claude Code 로그인(`claude`), OpenAI API(`openai`), Anthropic API(`anthropic`)를 공통 Pydantic 구조화 결과로 호출한다. Factory `make --llm openai --model ...`와 웹 수동 선택은 있으나 **`auto`와 오류별 공급자 전환은 없다**. OpenAI API 실호출은 아직 검증하지 않았다. Codex 채팅으로 조종해도 내부 대본 AI가 Codex/ChatGPT 구독으로 자동 변경되지 않는다.
- 자료 검색 자체는 네이버 뉴스(키가 있으면)·DuckDuckGo·본문 추출이고, 자동 화제 선택 `pick_trend`, 구성 `make_plan`, 대본 `write_script`, 장면 설계 `annotate_script`/`split_finished_script`, 업로드 영상 요약은 위 공통 LLM을 쓴다. 구성·장면 단계는 일부 규칙 대체 경로가 있지만 **대본 생성 실패는 전체 제작을 중단**한다. 업로드 영상의 화면 분석·음성 전사와 이미지/TTS 공급자는 별도 API 경로이므로 자동 전환 설계 때 비용 정책을 각각 확인한다.
- **현재 막힘:** 앞선 `make --topic ... --review` 새 대본 실기기 검증은 Claude 사용량 한도로 대본 작성 전에 실패했다. `provider=auto`가 없어서 다른 공급자로 이어가지 못한다. **비용 위험:** `app/config.py`가 `.env` 및 로컬 `settings.env`를 환경에 읽고, Claude Agent SDK 호출은 `ANTHROPIC_API_KEY`를 명시적으로 제거하지 않는다. 키가 설정되면 Claude Code가 구독 대신 API 인증을 우선할 수 있다. 실제 키 존재 여부는 이 문서 작성 중 읽거나 출력하지 않았으므로 확정하지 않는다. 이미지·대본의 사실검증 기능도 아직 완성되지 않았다.
- **다음 순서:** ① `claude` 구독 경로에 API 키가 상속되지 않도록 인증·과금 경계를 고정하고 사용자 설정 없이는 유료 API가 호출되지 않게 한다. ② 기존 `ask_structured` 중심으로 `auto|claude|openai` 선택·공급자별 모델·명시적 우선순위·오류 분류를 추가한다. `auto`는 인증/한도/명확한 일시 장애에만 한 번 전환하고 내용 불만족·형식 오류로 유료 재호출하지 않는다. ③ Factory·웹 설정, 사용 공급자/전환 이유 기록, 무료·유료 안내를 맞춘다. ④ 모의 호출 및 기존 전체 테스트, 명시적 승인 아래 필요한 실호출 검증을 마친다. ⑤ 새 주제 `--review` → `resume` 실기기 재검증. 그 뒤 2E→2G와 주장별 출처·팩트체크를 진행한다. 이 우선순위는 이전 A0 절의 ‘2E가 다음’ 기록보다 우선한다.

### 실행·테스트·보호 규칙

- 프로젝트 루트에서 `.venv\Scripts\python.exe -m app.factory make --topic "고양이가 상자를 좋아하는 이유" --seconds 45 --review` → `status <project_id>`/`inspect <project_id> --part script` → 승인 후 `resume <project_id>`. 직접 쓴 대본은 `make --script-file <파일> --review`. 완성 영상은 `output/<project_id>/final.mp4`; 전체 옵션은 `python -m app.factory --help`. Windows 웹 실행은 `AI Shorts 실행.cmd` → `http://127.0.0.1:8765/`.
- 테스트: `.venv\Scripts\python.exe -m unittest discover -s tests -q`. **2026-10-01 전체 95개 통과.** 이번 실행은 기존 모의 테스트이며 새 소재의 MP4 렌더나 OpenAI API 실호출 검증은 아니다.
- 외부 준비: Python 가상환경과 `requirements.txt`, FFmpeg/FFprobe, 기본 Claude Code 로그인, Edge TTS, 자료 검색 인터넷. 선택: `OPENAI_API_KEY`(유료 GPT), `ANTHROPIC_API_KEY`(유료 Claude API), `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`, `YOUTUBE_API_KEY`, 이미지·유료 TTS 키. 기본 `images.provider: none`은 내부 카드와 권리 확인된 파일을 쓴다. `.env` 또는 `%LOCALAPPDATA%/AIShorts/settings.env`의 **값은 출력·커밋하지 않는다**. Claude/ChatGPT/Codex 구독과 별도 API 과금을 혼동하지 말 것.
- 절대 보존: `output/`의 기존 결과, 이번 `assets/cat-box-45s/` 원본, 소스 대장·렌더 권리 가드, 2C 타임라인·2D 화면 선택기, 원격 히스토리. 사용자 승인 없이 유료 API·게시·다수 제작을 시작하거나 권리 미확인 외부 영상/기사/댓글을 화면에 사용하지 않는다. 프로그램 코드·기존 정상 기능을 대규모로 재작성하지 않는다.

## 2026-09-30 — A0 에이전트 콘텐츠팩토리 (당시 기록)

### 목적·Git·작업 원칙

- 개인용 한국어 9:16 쇼츠 제작기다. 주제/URL/완성 대본/핫이슈 → 조사·대본·장면 → TTS → 권리 확인 화면 → 자막 → FFmpeg MP4가 기존 `app/pipeline`에 있다. 이번 A0의 목표는 **Claude Code/Codex 채팅 자체를 메인 인터페이스**로 삼고, 웹 UI를 결과 확인·세부 수정용 보조 화면으로 쓰는 것이다.
- A0 작성 당시 이 브랜치는 원격에 없고 미커밋 변경이 있었다. 기반 커밋은 `ec86915`(2D 완료·`origin/feature/auto-video-mvp`에 push됨). 기존 `app/pipeline/run.py` 변경 및 `CLAUDE.md`, `app/factory/` 4개 파일, `tests/test_factory.py`를 보존하고 `AGENTS.md`·문서를 더해 `c6cd645`로 커밋했다. **이후 `feature/agent-content-factory` 브랜치를 GitHub에 push했다.** `pull`/`reset`/`checkout`으로 작업을 덮어쓰지 않았다.
- 설계 방향: 엔진 중복 구현이나 대규모 리팩토링을 하지 않는다. `app/factory`는 JSON 명령층, `app/pipeline`은 기존 제작 엔진, 웹 UI는 같은 엔진의 보조 화면이다. 자연어 → CLI 매핑·권리 정책·비용 규칙은 `CLAUDE.md`와 Codex용 `AGENTS.md`에 동일하게 적었다.

### 구현 파일과 사용법

| 파일 | 실제 역할 |
|---|---|
| 수정 `app/pipeline/run.py` | `script_in`을 받는 `resume` 경로. 저장 대본에서 이어서 제작하고 조사·기획·대본을 다시 하지 않는다. |
| 신규 `app/factory/__init__.py`, `__main__.py` | 패키지와 CLI 진입점. `make`, `resume`, `status`, `inspect`, `rerender`, `styles`, `trends`, `export`, `edit-scene`, `set-visual`. stdout 단일 JSON·stderr 진행 로그·종료 코드 0/1/2. |
| 신규 `app/factory/core.py`, `state.py` | 기존 파이프라인 호출, 명령별 검증, `next_action`, `project_state.json` 단계·실패 원인 기록, 최종 `job.json`으로 웹 UI 목록 연결. |
| 신규 `CLAUDE.md`, `AGENTS.md` | Claude Code/Codex에서 채팅을 기본 화면으로 쓰는 방법, 권리·비용·Git 규칙. `compare_card`/`summary_card` 명칭은 `app/pipeline/cards.py`의 실제 카드 종류와 일치한다. |
| 신규 `tests/test_factory.py` | factory 명령·상태·검토/재개·권리·재렌더·JSON 응답 자동 테스트 18개. |
| 수정 `IMPLEMENTATION_PLAN.md`, `HANDOFF.md` | 실제 구현/실기기 검증, Claude 한도에 막힌 B 경로, 다음 작업 순서. |

- 실행: 프로젝트 루트에서 `.venv\Scripts\python.exe -m app.factory make --topic "고양이가 상자를 좋아하는 이유" --seconds 45`. 대본 검토 후 멈춤: `make --topic "..." --review`; 이어 만들기: `resume <project_id>`; 조회: `status <project_id>`, `inspect <project_id> --part script`; 다시 렌더: `rerender <project_id>`. 전체 명령 옵션은 `.venv\Scripts\python.exe -m app.factory --help`와 `AGENTS.md`에 있다. 결과는 Git 제외 `output/<project_id>/`에 저장된다.
- 기본 환경: `config.yaml`은 Claude Code 구독 로그인(`claude.exe`), 무료 Edge TTS, 이미지 API 비활성(`provider: none`, 내부 카드), FFmpeg/FFprobe를 사용한다. `.env`·API 키·토큰·비밀번호를 출력하거나 Git에 넣지 말 것. 실제 업로드 파일은 권리 근거와 확인 플래그가 필요하다. 타인 유튜브/기사/댓글 원문은 내용 참고 전용이고 `sources.json` 및 렌더 가드를 우회하지 않는다. 유료 API·자동 게시·여러 편 연속 제작은 사용자 요청 없이 시작하지 않는다.

### 검증 결과 A~E와 남은 문제

- **자동 테스트:** 기존 77개 + 신규 18개 = **95개 통과** (`.venv\Scripts\python.exe -m unittest discover -s tests -q`). 2D 기능도 현재 코드에서 통과했다.
- **A 주제부터 MP4:** `make --topic "고양이가 상자를 좋아하는 이유" --seconds 45` 실제 실행. 조사 6건 → Claude 대본 7장면 → 무료 Edge TTS → 내부 카드·자막 → `output/20260930_230432_ae95/final.mp4` **42.61초, 1080×1920** 완성. `project_state.json=render_complete`, `job.json=done`. 장면별 AI 화면 분석은 실패해 기존 내용 규칙 대체가 쓰였다. 조사 기사 6건은 `sources.json`에 사용 불가/참고 전용으로 남지만 실제 렌더 재료는 권리 가드를 통과했다. 영상 내용의 사실·숫자는 별도 검증되지 않았으므로 게시 전 확인이 필요하다.
- **B 새 주제 대본까지만:** `make --topic ... --seconds 30 --review` 실제 호출은 Claude 구독 세션 한도(`2:30am Asia/Seoul` 초기화 안내) 때문에 대본 작성 전 실패했다. `output/20260930_230726_85df/project_state.json`에 `failed_at: research_complete`, `next_action: make`가 기록됐다. 유료 API로 우회하지 않았다. **대신** A의 실제 대본을 Git 제외 `output/factory_resume_input.txt`에 보관하고 `make --script-file ... --review`로 새 검토 프로젝트 `20260930_230910_910e`를 만들었다. 이때 Claude 한도로 장면 분할은 문장 경계 대체 경로를 썼다. 7장면 대본만 저장되고 음성/MP4는 없는 상태에서 멈췄다. 새 주제 → 새 대본 검토 경로의 실기기 검증은 아직 남아 있다.
- **C 상태 / D 대본 조회:** 검토 프로젝트의 `status`는 `waiting_for_script_approval`과 `next_action: resume`을 반환했고, `inspect --part script`는 7장면 대본을 보여줬다.
- **B 이어서 완성:** `resume 20260930_230910_910e`는 저장 대본을 그대로 써서 다시 조사·작성하지 않고 **42.61초, 1080×1920 MP4**와 웹용 `job.json`을 만들었다. 실제 영상의 소스 권리 가드를 통과했다.
- **E 다시 렌더:** 같은 프로젝트의 `rerender`가 `rerendered: true`와 완성 MP4를 반환했다. 전후 `script.json` SHA-256 앞 16자 `b4eb15553d93ba2a`, `narration.mp3`는 `f7587288f320412e`로 같았다. 재렌더 후 `final.mp4`도 동일 내용으로 생성됐다.
- **당시 남은 첫 작업:** Claude 구독 한도 초기화 후 새 주제의 `make --review` → `status`/`inspect` → `resume` 전체를 재검증한다. 실패한 프로젝트를 지우지 말고 새 `make`로 시도한다. 당시 계획은 2E 장면별 자막·모션·전환, 2F 오디오/렌더 안정화, 2G 한 번에 제작 흐름, 주장별 팩트체크·스타일팩 순서였다. **현재 우선순위는 위 2026-10-01 절의 AI 공급자·비용 안전 작업이다.** 브라우저의 새 factory 결과 실제 클릭 확인과 GPT 실호출은 아직 하지 않았다.
- **절대 건드리지 말 것/주의:** 기존 완료 MP4·`output/` 산출물, `feature/auto-video-mvp` 원격 히스토리, 소스 대장 권리 검사, 2C 실측 타임라인과 2D 카드 선택기. 실제 출력 경로는 로컬 전용이며 Git에 추가하지 않는다. 커밋 전 민감정보 검사와 전체 95개 테스트를 다시 확인한다.

## 2026-09-30 — 2D 장면별 화면 자동 선택 완료

- **브랜치·백업:** `feature/auto-video-mvp`에 2D 커밋을 만들고 GitHub에 push했다. 이후 작업은 `feature/agent-content-factory`에서 한다.
- **흐름:** 자동 대본(주제·URL)이든 직접 대본이든 다음 순서로 간다.
  1. 장면 설계: 역할·내용 성격·짧은 강조문구·숫자·비교 대상
  2. 검토 화면 미리보기 (`scenes/preview_NN.jpg`)
  3. TTS 실측(2C)
  4. 화면 결정·생성: `visuals.plan_visuals`/`materialize`
  5. 결정 기록: `blueprint.json`의 `visual_decision` + `visuals.json`
  6. 권리 가드 → 렌더
- **화면 우선순위:** 권리 확인 업로드 > 내 영상 구간 > AI 이미지(켜져 있을 때) > (스톡 자리) > 내용 성격별 카드 > 안전 카드. 권리 불명 자료는 후보가 되지 않는다.
- **카드 종류:** 도입·핵심·포인트·인용·숫자·변화·비교·정리. 같은 문구 카드가 연속되면 모양을 바꾼다(관련성 유지).
- **수정 주의:**
  - `cards.fit_text`(글자 실제 폭 측정)를 지우지 말 것.
  - 카드 내용은 화면 위 62% 안에 둔다. 아래는 자막 자리다.
  - `script_split._checked`는 대본에 없는 숫자를 막는다.
  - `llm._ask_claude_code`의 `max_turns=3`을 1로 되돌리지 말 것. 대본 작성이 실패한다.
- **검증:** 테스트 77개 통과. 실제 MP4는 `output/visuals_{A,B,C}_20260930_223207/`에 있고, 보고서는 `output/visuals_report_20260930_223207.json`이다. 자세한 내용은 `IMPLEMENTATION_PLAN.md` 2D 절에 있다.

## 2026-09-30 — 2C 실제 TTS 길이 기반 타임라인

### 상태·브랜치
- 브랜치 `feature/auto-video-mvp`. 시작 전 `563c59f`(2B+문서)가 `origin/feature/auto-video-mvp`와 일치(0/0)하고 clean인 것을 확인했다. 2B는 이미 GitHub에 백업되어 있다.
- 2C는 **로컬 체크포인트 커밋만** 했고 push하지 않았다(사용자 지시). `main`·다른 브랜치·원격 히스토리는 건드리지 않았다.
- **다음 첫 작업은 2D**(설계도의 화면 종류 → 소스 대장 기반 장면 화면 자동 선택)다. 사용자는 "2C까지만 하고 멈추라"고 했으므로 2D는 승인 뒤에 시작한다.

### 무엇이 바뀌었나 (흐름)
완성 대본 또는 AI 대본 → 4~8장면 → 검토(④에 예상 시간) → **장면별 Edge TTS → 앞뒤 무음 정리 → 실제 길이 측정 → 설계도 시간 확정(`timing: tts_aligned`)** → 장면 화면·자막을 그 시간으로 → `timeline.json`과 설계도 대조 → 권리 가드 → 렌더.

- 장면 i는 자기 음성 시작에 시작하고, 다음 장면 음성 시작 때 끝난다. 장면 사이 여백은 0.25초, 마지막 장면만 여운 0.5초다. 영상 길이 = 실제 음성 합 + 0.25×(장면 수−1) + 0.5.
- 설계도 필드(모두 선택, 옛 JSON 호환):
  - 장면: `actual_tts_duration`, `timeline_start`, `speech_end`, `timeline_end`. `start/end/duration`은 확정 후 실제값이 된다. `estimated_duration`은 보존한다.
  - 전체: `actual_duration`, `scene_gap`, `tail`.
- **새로 찾아 고친 문제 2가지:**
  - Edge TTS 파일마다 앞 약 0.35초, 뒤 약 1.1초의 무음이 있어 장면 전환마다 약 1.8초씩 멈췄다. `media.trim_edge_silence`로 앞뒤 무음만 잘라 **약 0.46초**로 줄였다.
  - `edge-tts` 7.x의 기본값이 문장 단위 경계라 **단어 시간이 오지 않았다**. 그래서 자막이 추정 시간으로 돌고 있었다. `tts/edge.py`에 `boundary="WordBoundary"`를 명시했다.
- **TTS 실패:** 장면마다 최대 3회 시도한다(`tts.retries`=2, `tts.retry_wait`=1.5). 빈 파일·길이 측정 실패도 실패다. 끝내 실패하면 `run.TTSFailed`에 "N번 장면 음성 생성 실패(3회 시도): 원인 · 내레이션: '…'"를 담아 잡을 `error`로 만든다. 설계도는 `estimated`로 남고 `timeline.json`·`final.mp4`는 만들지 않는다. **가짜 길이로 대체하지 않는다.**

### 변경 파일
| 파일 | 변경 |
|---|---|
| `app/pipeline/models.py` | `BlueprintScene`·`VideoBlueprint`에 실측 시간 필드(선택) 추가 |
| `app/pipeline/blueprint.py` | `align_to_audio`, `scene_durations`, `check_timeline`, `TAIL` |
| `app/pipeline/run.py` | `TTSFailed`, `_synthesize_one`(재시도·검증·무음 정리), `_fit_words`, 단어를 장면 음성 안으로 제한, 두 경로 모두 검토용 설계도, TTS 직후 설계도 확정·저장·진행 로그, 렌더 길이를 설계도에서, 렌더 전 `check_timeline` |
| `app/pipeline/media.py` | `edge_silence_sync`, `trim_edge_silence`, `concat_audio(tail=)` (기본 0이라 기존 호출 영향 없음) |
| `app/pipeline/tts/edge.py` | 단어 경계(`WordBoundary`) 요청 |
| `app/static/app.js`, `app/templates/index.html`, `app/static/style.css` | ④ 예상 시간 안내, ⑧ 「장면 타임라인」 표 |
| 신규 `tests/test_tts_timeline.py` | 14개: 짧은/긴/8장면, 옛 설계도 호환·왕복, 불일치 감지, 재시도·전체 실패·빈 파일·측정 실패, 무음 정리 후 단어 이동, 자막 경계, 직접 대본·AI 대본 경로, 실패 시 렌더 안 함 |
| 신규 `scripts/verify_tts_timeline.py` | 실제 Edge TTS로 A·B·A2 MP4를 만들고 자동 검증(표 출력, 확인용 프레임 저장) |
| `IMPLEMENTATION_PLAN.md`, `HANDOFF.md` | 2C 완료·실제 구현 차이·다음 2D |

### 검증 결과
- 자동 테스트 **64개 통과**(기존 50 + 신규 14): `.venv\Scripts\python.exe -m unittest discover -s tests -q`
- 실제 MP4(무료 Edge TTS + 내부 카드, CapCut·유료 API·LLM 호출 없음). 모두 1080×1920이고, 설계도 길이 = MP4 길이, 장면 밖 자막 0줄, 장면 전환 무음 약 0.46초, 끝 무음 0.66초다.

  | 편 | 내용 | 영상 길이 | 산출물 |
  |---|---|---|---|
  | A | 직접 대본 5장면 | 20.78초 | `output/tts_timeline_A_short_20260930_215251/` |
  | B | 경제 8장면 | 52.53초 | `output/tts_timeline_B_econ_20260930_215251/` |
  | A2 | 주제 경로 4장면 (리서치·대본만 고정 데이터) | 16.37초 | `output/tts_timeline_A2_topic_20260930_215251/` |

- 자막 동기화(B): 장면별 첫 자막과 실제 말 시작의 차이는 평균 −0.05초, 최대 0.07초다. 마지막 자막은 음성 끝 +0.15초에 사라지고 다음 장면으로 넘어가지 않는다.
- 재현: `.venv\Scripts\python.exe scripts/verify_tts_timeline.py` (인터넷·ffmpeg 필요). A·B의 장면 분할은 LLM 없이 실제 문장 경계 대체 경로를 쓴다.
- 브라우저: ⑧ 「장면 타임라인」 표에 실제 B 설계도로 8행과 합계(예상 61.62초 / 실제 음성 50.28초 / 영상 52.53초)가 표시되는 것을 확인했다. 가로 넘침 없음.

### 남은 제약·주의
- 첫 단어 자막은 Edge 단어 경계 기준으로 소리보다 약 0.05~0.25초 먼저 뜰 수 있다(허용 범위로 판단).
- AI 없이 문장 단위로 나눈 직접 대본은 상단 키워드에 문장 전체가 들어가 화면 양옆이 잘린다(2B 대체 분할의 기존 동작, 2D/2E에서 다룰 것).
- 사람이 해야 할 것: 실제 청취로 억양·끊김 확인, 브라우저에서 실제 잡으로 끝까지 클릭해 보기, GPT 실호출, 게시 전 사실 확인.
- 수정 주의: `trim_edge_silence`의 −40dB·앞 0.05초·뒤 0.15초 여유를 줄이면 음절이 잘릴 수 있다. `check_timeline`을 끄지 말 것. `concat_audio`의 `tail`은 2C 파이프라인만 사용한다.
- `.env.example` 머리말("ANTHROPIC_API_KEY 필수")은 여전히 오래된 안내다(범위 밖, 미수정).

### 이번 체크포인트에서 이어받을 상태 (2B 당시 기록)

- 현재 브랜치는 `feature/auto-video-mvp`이며 2B 기능 커밋은 `1845fca`다. 체크포인트 시작 시 작업 폴더는 clean, 원격 `origin/feature/auto-video-mvp`는 `503db41`로 로컬보다 1개 뒤였다. 이번 요청에서는 아래 2B 코드를 고치지 않고 이 문서만 갱신해 별도 체크포인트 커밋을 만든 뒤 두 커밋을 현재 원격 브랜치로 일반 push한다. 기존 커밋 변경·force push·다른 브랜치 수정은 금지한다.
- 2B 커밋에 포함된 **13개 파일**: 새 파일 `app/pipeline/script_split.py`, `scripts/demo_script_split_mvp.py`, `tests/test_script_split.py`; 수정 파일 `HANDOFF.md`, `IMPLEMENTATION_PLAN.md`, `README.md`, `app/jobs.py`, `app/main.py`, `app/pipeline/blueprint.py`, `app/pipeline/models.py`, `app/pipeline/run.py`, `app/static/app.js`, `app/templates/index.html`. 각 파일의 역할은 아래 표에 적었다. 이번 체크포인트에서 코드/기능 변경은 없다.
- 현재 진행 중인 기능 개발은 없으며 **다음 첫 개발 작업은 2C**다. 현재 확인된 차단 오류는 없다. 남은 제약은 설계도의 시간값이 TTS 실측 전 추정치라는 점(2C), 설계도 화면 종류·모션이 아직 실제 렌더 선택에 연결되지 않았다는 점(2D/2E), 주장별 팩트체크가 아직 없다는 점(후속 A)이다. 실제 GPT 호출과 브라우저의 전체 클릭 흐름은 미검증이다. `.env.example`의 “ANTHROPIC_API_KEY 필수” 머리말은 현재 기본 `config.yaml`의 `provider: claude`와 맞지 않는 오래된 안내다. Claude Code 로그인만으로 기본 AI 경로를 사용할 수 있으며, 예시 안내 수정은 후속 문서 정리로 남긴다.
- 우선순위: ① 2C TTS 실측 시간으로 `blueprint.json` 갱신 및 `timeline.json`과 대조 ② 2D 허용 소스 기반 화면 자동 배치 ③ 2E 장면별 자막/모션 연결 ④ 2F/2G 최종 자동 렌더·제작 버튼 ⑤ 주장별 출처·팩트체크와 검토 게이트. 처음부터 편집기를 새로 만들지 말고 기존 TTS·ASS·FFmpeg·소스 대장을 재사용한다.
- 이 문서의 아래 과거 절에 있는 “2B 미구현”, “다음은 2B/팩트체크”, “원격에 push하지 않음” 등은 **당시 이력**이다. 현재 기능·우선순위와 브랜치 상태는 이 체크포인트와 바로 아래 2B 절을 기준으로 한다.

## 2026-09-29 — 자동 제작 MVP 2B 완료 (현재 상태)

### 프로젝트·브랜치·안전한 시작점

- 이 프로젝트는 개인용 한국어 쇼츠 제작기다. 목표 흐름은 주제/URL 또는 완성 대본 → 대본/장면 설계 → TTS → 권리 확인 화면 자료 → 자동 자막/효과 → 세로 MP4다. Python 3.12, FastAPI, 순수 JS, 기존 Claude Code/GPT 연동, Edge TTS, FFmpeg를 사용한다. CapCut 없이 기존 파이프라인으로 완성 MP4를 만든다.
- 작업 브랜치는 `feature/auto-video-mvp`. 2B 시작 전 깨끗한 `503db41`을 `origin/feature/auto-video-mvp`에 push하고 양쪽 커밋 ID 일치를 확인했다. 2B 기능 커밋 `1845fca`는 당시 요청에 따라 처음에는 로컬에만 뒀으며, **이번 체크포인트에서 현재 브랜치로 push한다.** `main`, 기존 `feature/source-registry`/`checkpoint/source-registry-stage1`은 건드리지 않고 원격 커밋 히스토리를 덮어쓰지 않는다.
- 우선순위는 `IMPLEMENTATION_PLAN.md`의 2C→2G, 그 뒤 주장별 팩트체크와 검토 게이트, 스타일·차트·스톡 등이다. 팩트체크는 삭제된 기능이 아니다.

### 2B 구현과 사용자 흐름

- ② 소재에서 **「완성 대본 직접 입력」** 탭에 최소 4문장의 완성 대본을 붙여넣고 ③ **「대본으로 쇼츠 만들기」**를 누른다. 기존 **주제/URL → AI 대본 생성** 경로는 그대로다. 직접 대본은 별도 리서치·재작성 없이 원문을 보존한다.
- 기존 `ask_structured()`로 Claude/GPT가 원문 문장 번호를 의미별로 4~8묶음으로 계획한다. Hook/상황/핵심/변화/근거/결론/CTA, 화면 종류·설명, 강조 문구, 줌/팬·전환, 소스 요구·메모를 제안한다. 원문 순서/누락, 장면 수, 화면 선택지, 과도한 길이를 검사한다. API/JSON/계획 오류는 문장 경계에서 길이를 균형 있게 나누는 내부 카드 계획으로 대체한다. AI 없이도 이 대체 경로는 사용 가능하다. 최소 4문장 미만은 입력 오류를 안내한다.
- `PlannedScene/PlannedScript`는 기존 `Scene/Script`의 별도 하위 모델이다. 주제/URL 대본용 AI 구조화 응답 형식을 바꾸지 않는다. `blueprint.json`에 `scene_id`, `scene_type`, 예상 시작/종료/길이, 내레이션/자막, 화면 종류/설명, 강조 문구, 움직임/전환, `source_requirement`, `notes`를 기록한다.
- 직접 대본은 `review=false`여도 ④ 검토에서 **반드시 일시정지**한다. 장면 순서·나레이션·자막·화면 설명·예상 시간을 확인한다. 기존 UI에서 나레이션·키워드를 수정하고 장면을 삭제할 수 있다. 나레이션 수정 시 설계도 자막도 함께 바꾼다. 승인 후 기존 TTS·자막·소스 대장 가드·렌더가 실행된다. 기존 화면 자료 선택/렌더는 설계도 `visual_type`을 아직 직접 사용하지 않는다(2D/2E).
- 주제/URL의 기존 생성 대본도 2A 설계도로 이어진다. 직접 대본은 출처/숫자를 자동 확인하지 않는다. 타인 영상·기사·댓글은 참고 전용이며 실제 화면에는 권리 확인된 첨부·AI 생성 이미지·내부 카드를 쓴다. 게시 전 사실 검토가 필요하다.

### 이번 변경 파일

| 파일 | 실제 변경 |
|---|---|
| 신규 `app/pipeline/script_split.py` | 문장 분리, 구조화 AI 장면 계획, 원문/길이 검증, 오류 시 길이 균형 대체. |
| `app/pipeline/models.py`, `app/pipeline/blueprint.py` | 2B 전용 계획 모델과 확장된 장면 설계도. 기존 `Script` 계약 유지. |
| `app/pipeline/run.py` | `script` 입력 모드, 검토 전 설계도 저장, 검토 후 재생성, 기존 렌더 경로 연결. |
| `app/jobs.py`, `app/main.py` | 직접 대본 API 모드, 강제 검토, 승인 수정 보존, 설계도/AI 대체 상태 노출. |
| `app/static/app.js`, `app/templates/index.html` | 직접 대본 입력 탭·버튼, ④ 장면 계획 미리보기와 실패 안내. |
| 신규 `tests/test_script_split.py` | 짧은/긴/경제 대본, 원문·정보 보존, AI 실패, API 입력, 검토 전 설계도, 승인 수정 테스트 9개. |
| 신규 `scripts/demo_script_split_mvp.py` | 새 입력 경로의 무료 실제 렌더 재현. AI 응답만 고정 목. |
| `README.md`, `IMPLEMENTATION_PLAN.md`, `HANDOFF.md` | 사용자 사용법, 2B 완료 상태·검증 결과·다음 단계 갱신. |

### 검증·남은 일·실행

- 기존 41개 + 신규 9개 = **50개 자동 테스트 통과**: `.venv\Scripts\python.exe -m unittest discover -s tests -q`. 실제 Claude Code 구조화 호출 1회에서 4장면/원문 보존을 확인했다. GPT API 실호출과 실제 브라우저 클릭 흐름은 미검증이다.
- 새 경로에서 Edge TTS(20.1초) → 내부 생성 카드 4장 → ASS 자막 → FFmpeg로 **20.07초, 1080×1920 MP4**를 실제 만들었다. 2B 전용 모델 분리 후 재검증한 산출물: `output/mvp_script_split_20260929_214546/final.mp4`, 같은 폴더의 `blueprint.json`/`sources.json`/`timeline.json`. MP4는 968,119바이트이며 대장에 기록된 5개 소스는 모두 사용 가능 상태다. `output/`은 Git 제외. 재현: `.venv\Scripts\python.exe scripts/demo_script_split_mvp.py`; 이 데모의 AI 계획만 고정 목이며 음성/렌더는 실제다.
- 다음 **2C**: `blueprint.json`의 추정 시간을 장면별 TTS 실제 길이에 맞춰 갱신하고 `timeline.json`과 일치시킨다. 현재 MP4는 기존 실측 타임라인으로 정상 렌더되지만 설계도의 `timing`은 `estimated`다. 장면별 `visual_type` 렌더 적용은 2D, 장면별 모션은 2E, 원클릭 전체 제작은 2G다. BGM 자동 선택/효과음/차트 실제 생성/여러 편 동시 제작은 이번 2B 범위가 아니다.
- 실행: 루트 `AI Shorts 실행.cmd` 더블클릭 또는 `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765`. 기존 서버를 켜 둔 상태라면 새 코드가 반영되도록 서버를 재시작해야 한다. 테스트에는 `.venv`, FFmpeg가 필요하고 실기기 데모의 Edge TTS는 인터넷 연결이 필요하다. 실제 AI 분석은 로그인한 `claude.exe` 또는 `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`가 필요하며 실패 시 문장 경계 대체가 동작한다. `.env`, 키, 토큰, `output/`, 참고 원본 영상을 Git에 넣지 말 것.
- 절대 건드리지 말 것: 기존 완료 영상, CapCut 드래프트/`root_meta_info.json`, 원격 히스토리·다른 브랜치. 수정 주의: `SourceRegistry`/`guard_timeline`의 권리 검사, `Script`의 기존 LLM 구조화 계약, `timeline.json`의 재렌더 계약, `awaiting_review` 이벤트 상태. 자세한 역사적 설계·환경 변수는 아래 기록과 `.env.example`을 참조한다.

## 2026-09-29 — 자동 MP4 제작 우선순위와 2A 장면 설계도

### 목표·상태

- 최종 사용 목표는 주제/URL 또는 직접 대본 → 분석/장면 분할 → TTS → 권리 확인 영상/이미지/차트/모션 → 자동 자막·기본 효과·허용 BGM → **CapCut 없이 앱에서 1080×1920 MP4 완성**이다. 완벽한 편집기보다 안정적인 끝까지 제작을 우선한다. 기존 FastAPI/Python/FFmpeg/Edge TTS/ASS 자막/소스 대장을 재사용하며 Remotion은 도입하지 않는다.
- 개발 순서는 `IMPLEMENTATION_PLAN.md`의 **2A~2G 자동 제작 MVP가 먼저**, 그다음 주장별 출처·팩트체크(후속 A), 선택형 검토 게이트(후속 B), 화면 품질·스톡·모션 등이다. 기존 팩트체크 요구는 삭제하지 않았다. 검토 옵션을 끄면 자동 완료, 필요하면 사용자가 대본/장면을 고치는 방향이다.
- 시작 전 `feature/source-registry`의 1단계 커밋 `860b787`을 `checkpoint/source-registry-stage1` 브랜치에 별도로 고정했다. 현재 작업 브랜치는 **`feature/auto-video-mvp`**. `main`과 원격은 이번 단계에서 변경하지 않는다.
- **이번에 완료한 범위는 2A뿐이다.** 기존 `Script`를 장면별 `VideoBlueprint`로 변환해 잡별 `blueprint.json`과 `GET /api/jobs/{id}/blueprint`로 제공한다. 장면에는 예상 시작/종료/길이, 나레이션, 자막 문구, 화면 종류·이미지 지시, 기본 줌 방향·전환, 강조 문구, 향후 소스 ID가 있다. 기존 `timeline.json` 렌더 계약은 바꾸지 않았다. 기존 9~10장면도 그대로 수용하며 4~8장면 강제 분할은 **2B**다.

### 이번 변경 파일

| 파일 | 내용 |
|---|---|
| 신규 `app/pipeline/blueprint.py` | 기존 대본 → 추정 장면 설계도, JSON 원자 저장·로드. TTS 측정은 하지 않음. |
| `app/pipeline/models.py` | `BlueprintScene`, `VideoBlueprint` 자료 구조. |
| `app/pipeline/run.py` | 대본이 확정된 뒤 설계도 저장·결과 포함. 기존 TTS·비주얼·FFmpeg 경로 그대로. |
| `app/jobs.py`, `app/main.py` | 설계도를 잡 결과와 읽기 전용 API에 노출. |
| 신규 `tests/test_blueprint.py` | 구조·시간·저장·기존 파이프라인·API 테스트 6개. |
| 신규 `scripts/demo_blueprint_mvp.py` | 무료 내부 재료만으로 기존 전체 파이프라인을 돌리는 재현 스크립트. 고정 대본이므로 LLM 호출은 목으로 대체. |
| `IMPLEMENTATION_PLAN.md` | 2A~2G를 최우선으로 재정렬하고 이전 단계는 후속 A~L로 보존. |
| `README.md` | 현재 자동 제작 경로, 직접 대본 입력 미완료, 안전한 실기기 데모 실행법 안내. |

### 실제 검증과 사용자 흐름

- 기존 35개 + 2A 테스트 6개 = **41개 자동 테스트 통과**: `.venv\Scripts\python.exe -m unittest discover -s tests -q`. 파이썬 문법, `git diff --check`도 확인한다.
- 무료 Edge TTS와 기존 `run_pipeline()`으로 **4장면, 20.07초, 1080×1920/24fps MP4**를 실제 생성했다. 안전한 고정 테스트 대본 → 장면 설계도 → 실제 TTS → 내부 생성 대체 카드 4장 → 12줄 자동 자막 → FFmpeg 줌/페이드 → `final.mp4`까지 자동 실행. `sources.json`의 5개 재료(음성 1·카드 4)는 모두 사용 가능으로 확인했고 최종 가드를 통과했다. 3/10/17초 프레임을 육안 확인했다. **CapCut, 타인 영상, 유료 이미지 API, 유료 LLM은 사용하지 않았다.**
- 데모 산출물: `output/mvp_blueprint_demo_20260929_212147/final.mp4`, 같은 폴더의 `blueprint.json`, `timeline.json`, `sources.json`. `output/`은 Git 제외다. 재현: `.venv\Scripts\python.exe scripts/demo_blueprint_mvp.py` (Edge TTS 인터넷 연결과 ffmpeg 필요).
- 현재 화면에서 주제/URL 자동 제작은 기존 「대본 만들기」를 사용한다. 「대본 먼저 확인하고 렌더링」을 끄면 기존 파이프라인이 승인 대기 없이 MP4까지 간다. **직접 쓴 완성 대본을 넣어 AI가 4~8장면으로 나누는 입력·버튼은 아직 없다(2B/2G).** 데모 스크립트는 사용자를 위한 원클릭 UI가 아닌 개발 검증 도구다.

### 주의·미완료와 다음 첫 작업

- `blueprint.json`의 시간은 글자 수 기반 **추정치**다(이번 데모 추정 22.982초, 실제 MP4 20.07초). 실제 TTS 길이를 설계도에 반영하고 타임라인과 일치시키는 작업은 **2C**. 현재 렌더는 기존 파이프라인의 TTS 실측 타임라인을 쓰므로 영상 자체는 정상이다.
- 설계도의 `motion`/`transition`은 현재 렌더의 기존 줌·페이드를 기록한 기본 제안이며 장면별로 렌더에 전달되지는 않는다(2E). 차트·모션그래픽, 권리 확인 BGM/효과음, 직접 대본 입력은 아직 아니다. 소스 규칙은 1단계 그대로 적용하며 금지 자료를 임의로 허용하지 말 것.
- 다음 작업자는 **2B: 직접 쓴 짧은 대본 → 4~8장면 자동 분할**만 구현한다. 기존 `Script`와 새 `VideoBlueprint`를 재사용하고 현재 41개 테스트 및 20~30초 렌더 경로를 유지한다. 이후 2C~2G를 순서대로 진행한다. 팩트체크는 MVP 뒤 필수 후속 작업이다.
- 권리 정보와 API 키는 `.env`/사용자 설정에만 두며 Git에 올리지 않는다. 큰 영상·프레임·`output/`은 Git 제외. 기존 CapCut 드래프트·1단계 체크포인트·원격 브랜치를 변경하지 말 것.

## 2026-09-29 — 1단계 소스 대장 완료 (`feature/source-registry`)

### 프로젝트와 현재 상태

- 한국어 AI 쇼츠를 주제·유튜브/기사 URL·업로드 영상·핫이슈에서 만들고, 조사→대본 검토→TTS→장면→9:16 MP4·메타 파일을 생산하는 개인 PC용 FastAPI 웹앱이다. Claude Code 구독 또는 OpenAI/Anthropic API를 선택할 수 있다. 완성 후 자막·댓글 이미지 편집, 재렌더, CapCut·재료 ZIP 내보내기가 있다. 자동 유튜브 업로드와 원격 웹앱은 없다.
- 기술 스택: Python 3.12, FastAPI, Jinja/순수 JS, asyncio 단일 잡 큐, Pydantic, ffmpeg, yt-dlp, edge-tts. 실행은 루트 `AI Shorts 실행.cmd`, 주소 `http://127.0.0.1:8765/`.
- `main`의 설계 문서 체크포인트 `8cbc5b5`는 GitHub에 push 완료. 이후 개발은 `feature/source-registry`에서만 진행했고 2단계(주장별 팩트체크) 이후는 미착수. `REFERENCE_VIDEO_ANALYSIS.md`는 영상 분석 근거, `IMPLEMENTATION_PLAN.md`는 단계·비용·저작권·장기 설계다.

### 완료된 1단계와 수정 파일

| 파일 | 실제 변경 |
|---|---|
| **신규** `app/pipeline/sources.py` | 잡별 `sources.json` 저장·로드, 권리 판정, 경로 이동/삭제, 렌더 전 검사. 기본 불허. |
| **신규** `tests/test_sources.py` | 권리 유형·증빙·최초/재렌더/내보내기 차단·API 오류·장면 경로 이동 테스트 12개. |
| `app/pipeline/models.py` | `SourceItem` 모델과 가공 결과의 원본 `parent_id`. |
| `app/pipeline/run.py` | 업로드·리서치 URL·영상 후보·댓글 참고자료·TTS·장면 결과를 등록. 허용된 업로드 영상만 broll, 기사 이미지는 제외, 타인 댓글은 화면에서 제외, 외부 YouTube 클립 렌더 차단. 최초 렌더 전 검사. 권리 미확인 BGM 제외. |
| `app/pipeline/timeline.py`, `app/pipeline/capcut.py` | 소스 대장이 있는 작업의 직접 렌더·CapCut·ZIP 출력 직전에 재검사. |
| `app/main.py` | `GET /api/jobs/{id}/sources`, 장면/댓글 이미지 업로드 권리 입력, 재렌더·내보내기에서 명확한 409 안내. |
| `app/jobs.py` | 업로드 파일별 권리 정보 전달, 장면 번호 변경 시 대장 경로도 이동. |
| `app/static/app.js`, `app/static/style.css`, `app/templates/index.html` | 파일별 권리 유형·링크·근거·출처·확인 UI, 장면 후보 허용 배지와 댓글 참고 전용 안내. |
| `README.md` | 사용자용 사용 흐름·소스 규칙을 새 정책에 맞게 갱신. |
| `config.yaml` | `source_policy: strict`, 빈 `my_channels` 자리. 실제 채널 ID는 넣지 않는다. |
| `tests/test_timeline_export.py` | 기존 ‘재렌더 실패 시 원본 보존’ 테스트에서 권리 검사만 격리. 정책의 허용/차단은 새 테스트에서 검증. |
| `IMPLEMENTATION_PLAN.md` | 1단계 완료 표시, 실제 구현 차이 기록. |

### 사용 규칙과 주의

- 잡마다 `output/<id>/sources.json`에 소스 유형, URL/경로, 권리 종류·증빙·확인일, 상업/수정/제3자 권리, 사용 가능 여부, 사용처를 저장한다. `output/`과 `.env`는 Git 제외. API 키·토큰·개인 설정값을 Git에 넣지 말 것.
- 업로드 기본값 `unknown`: 파일명이나 내 채널이라는 선택만으로 허용되지 않는다. 내 제작물/AI 생성 업로드는 권리 확인 체크와 개별 근거 링크 또는 설명이 필요하다. Pexels/Pixabay/공공누리 0·1유형은 개별 저작물 링크와 출처 표기까지 필요하다. 공공누리 2~4유형, 외부 유튜브/기사/댓글은 참고 전용이다. 프로그램이 새로 만든 음성·장면·카드는 대장에 기록해 사용한다. 업로드를 리사이즈한 장면은 `parent_id`로 원본 권리를 잇는다.
- 기존 완료 잡의 `final.mp4`는 건드리지 않는다. 권리 대장이 없는 예전 잡은 재렌더/CapCut/ZIP을 막고 안내한다. 장면 파일을 삭제·교체·번호 이동할 때 대장 경로도 갱신할 것. CapCut 기존 드래프트 및 `root_meta_info.json`은 건드리지 말 것. 강제 push/기존 히스토리 수정 금지.
- 검토 화면에서는 참고 후보를 보여주지만 외부 영상 체크박스는 비활성화한다. 타인 댓글 후보는 대본 참고용이다. 증빙 없는 업로드는 장면 재료에서 제외해 AI 이미지/카드로 대체한다. 기존 자막·TTS·이미지 제작·출력 구조를 유지한다.

### 확인 결과, 한계, 다음 작업

- 기존 자동 테스트 23개 + 신규 12개 = **35개 통과** (`.venv\Scripts\python.exe -m unittest discover -s tests -v`). `python -m compileall -q app tests`, `node --check app/static/app.js`, `git diff --check` 통과. 로컬 ffmpeg로 생성 이미지·음성의 2초짜리 180×320 MP4 실제 렌더 성공. 실제 유튜브/기사·유료 이미지 API·CapCut 데스크톱 열기 전체 시나리오는 이번 단계에서 실행하지 않았다.
- 남은 제약: 채널 소유권을 URL로 자동 검증하지 않아 원격 URL 클립은 모두 차단한다. `my_channels`는 현재 미사용 설정이다. BGM은 별도 권리 입력 경로가 없어 새 영상에서 사용하지 않는다. AI 이미지 제공자별 약관 자동 검증은 없다. 사용자 권리 확인 진술의 진위와 스톡/공공누리 링크 내용은 자동 조사하지 않는다. 기존 완료 영상 자체는 지우거나 변경하지 않는다. 완성 화면의 실제 브라우저 사용성/CapCut 실기기 검증은 필요하다.
- **다음 첫 작업은 2단계 주장별 팩트체크**다. `IMPLEMENTATION_PLAN.md`의 2단계만 별도로 구현하고, 기존 35개 회귀 테스트를 유지한다. 그 다음 3단계에서 G1 주제·G2 대본·G3 렌더 승인 게이트를 만든다. 권리 검사 우회가 생기지 않도록 신규 영상·음성·파일 경로를 항상 대장에 연결할 것.
- 필요한 서비스: ffmpeg/ffprobe 필수. `claude.exe` 로그인 또는 `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`, 선택 기능에 `GEMINI_API_KEY`, `YOUTUBE_API_KEY` 등 기존 `.env.example` 참고. 테스트 자체는 유료 API를 호출하지 않는다. 사용자용 상세 실행법은 `README.md` 참고.

## 2026-09-24 오후 — 단계별 사이드바 UI · 자막 수정 · 댓글 캡처 · CapCut 내보내기 (다음 작업자는 여기서 시작)

### 한눈에 보기

- **프로젝트:** 한국어 유튜브 쇼츠(9:16) 자동 제작 웹 도구다. 개인 PC에서 쓰고, 자동 업로드는 없다.
  - 입력: 주제 / 유튜브·기사 링크 / 업로드 영상 / 핫이슈 자동.
  - 흐름: 자료 조사 → 대본 → 검토 → TTS → 화면(이미지·영상 짜깁기) → MP4와 `meta.txt`.
  - 완성 후: 자막·댓글 수정, CapCut 내보내기.
- **현재 단계:** 이번 요청(사이드바 UI, 자막 수정, 댓글 캡처, CapCut 내보내기, 레퍼런스 댓글 자동 배치)의 **코드와 목 테스트는 완성됐다.** 실제 영상으로 해 보는 시험은 사용자 지시에 따라 **아직 하지 않았다.**
- **다음 작업 (우선순위 순):**
  1. **(사용자 신호 후)** 주제 1건을 실제로 제작해 `timeline.json` 생성을 확인한다. 이어서 ⑦에서 자막 1줄 수정과 캡처 1장을 넣고 「다시 만들기」로 결과 영상을 확인한다.
  2. ⑧ CapCut 프로젝트로 보내기를 눌러, CapCut 9.3 목록에 뜨고 열리는지 확인한다. 트랙 배치와 자막 크기(추정값)도 확인해서 필요하면 `capcut.py`를 조정한다. 목록에 안 뜨면 `root_meta_info.json` 등록을 검토하되, 기존 파일이므로 사용자 확인 후 백업을 거쳐서만 한다.
  3. 재료 묶음 zip을 받아 내용을 확인한다.
  4. 키가 있을 때 스타일 분석과 댓글 배치 분석을 1회 해 본다.
  5. 이전부터 남은 검증: 업로드 영상 전체 흐름, broll 자동 소스 수집, 기사 이미지, Gemini 경로 (§6).
  6. 남은 UI 과제: `visual_mode` 드롭다운, 잡 취소 버튼. Phase F(Omni 영상)는 후순위다.
- **막혀 있는 것과 원인:**
  - 실사용 검증은 "샘플·유료 호출 금지, 사용자 신호 후 테스트" 조건 때문에 대기 중이다.
  - 댓글 배치 분석, 댓글 자동 수집, Gemini 경로는 각각 Gemini/OpenAI 키, `YOUTUBE_API_KEY`가 있어야 한다.
  - CapCut 드래프트 형식은 공식 문서가 없어서, 실제 파일을 역으로 참고해 만들었다. 그래서 실제로 열어 보기 전에는 확신할 수 없다.
- **알려진 미해결 오류:** 새로 발견된 런타임 오류는 없다. 미검증 항목과 제약은 §7 "미해결"을 볼 것.
- **실행:** `AI Shorts 실행.cmd`를 더블클릭하면 된다. 브라우저 주소는 `http://127.0.0.1:8765/`다. 명령 창을 닫으면 서버도 꺼진다.
- **테스트:**
  - 목 테스트 23개: `.venv\Scripts\python.exe -m unittest discover -s tests -v`. 네트워크·ffmpeg 렌더·유료 API를 쓰지 않는다.
  - 문법·공백 검사: `.venv\Scripts\python.exe -m compileall -q app`, `git diff --check`.
- **환경변수·외부 서비스:** §2와 `.env.example`을 볼 것.
  - 이번 작업에서 새 키는 없다. 댓글 배치 분석은 기존 `GEMINI_API_KEY` 또는 `OPENAI_API_KEY`를 쓴다.
  - 외부 프로그램으로 CapCut 데스크톱이 새로 쓰인다(선택 사항). 없으면 재료 묶음 zip만 쓰면 된다.
- **중요 조건:** §9를 볼 것. 특히 이번에 추가된 8·9·10번(자막·댓글은 선택 사항, 단계 메뉴와 CapCut, Git 규칙)이다.
- **건드리면 안 되는 것과 수정 주의:** §10을 볼 것. 이번에 CapCut 기존 드래프트 보호, `overlays/` 분리, 다시 만들기의 원본 보존, `timeline.py`, `capcut.py` 관련 항목을 추가했다.

**사용자 요청:** TubeFactory처럼 왼쪽에 단계별 메뉴를 두고, 자막 수정, 댓글 캡처 직접 추가, CapCut 내보내기, 레퍼런스 영상 분석으로 댓글 자동 배치를 만든다. 순서는 이 네 가지 그대로였다. **자막·댓글은 선택 사항이다.** 아무것도 넣지 않고 넘어가도 영상이 완성돼야 한다.

**핵심 설계 — `timeline.json`:**
- 첫 렌더 직전에 렌더 재료(장면·길이·비주얼 경로·나레이션·BGM·자막 줄과 단어 타이밍·키워드·출처·댓글·스타일 댓글 자리)를 `output/<잡>/timeline.json`에 저장한다.
- 최초 렌더와 ⑦의 「다시 만들기」는 같은 함수 `timeline.render_timeline()`을 쓴다. 다시 만들기는 LLM·TTS를 부르지 않아 무료이고, 1~3분 걸린다.
- 다시 만들기는 `final_new.mp4`로 렌더한 뒤 성공했을 때만 `final.mp4`를 교체한다. 실패하면 기존 영상이 그대로 남고, 잡 상태는 `done`으로 돌아가며 message에 실패 사유를 남긴다.
- CapCut·재료 묶음 내보내기도 `timeline.json`만 읽는다.
- 이 기능 이전에 만든 잡이나 클립 재편집(`visual_mode=clip`) 잡에는 timeline이 없다. 그런 잡은 ⑦과 CapCut을 막고 안내만 하며, MP4 다운로드는 그대로 된다.

**화면 구조 (`index.html`/`app.js`/`style.css` 전면 재구성):** 왼쪽 사이드바는 ① 프로젝트 목록 ② 소재 ③ 스타일·지침 ④ 대본 ⑤ 음성 ⑥ 화면 배치 ⑦ 자막·댓글 ⑧ 내보내기, 그리고 ⚙ 설정·API 키로 되어 있다.
- **단계 활성 조건**(`stepEnabled`):
  - ②③: 새 프로젝트일 때만.
  - ④⑤⑥: 잡이 `awaiting_review`일 때.
  - ⑦⑧: `result.video`가 있을 때.
- **자동 이동:** 상태가 바뀌면 검토 대기 → ④, 완성 → ⑦(timeline이 없으면 ⑧)로 이동한다. 진행 중인 잡은 상단 `#runbar`에 진행 막대와 로그를 보여준다.
- **⑤ 음성:** 승인할 때 `tts_provider`/`voice`를 보낸다. 서버의 `run._apply_voice`가 TTS 전에 적용한다.
- **⑥ 장면 삭제:** 승인할 때 `scene_map`(새 번호별 원래 번호)을 보낸다. `jobs._remap_scene_files`가 `uploads/scene_NN_*`의 번호를 다시 매기고, 삭제된 장면의 파일은 `_removed_`로 바꾼다. 이 수정으로 **장면을 지우면 고정 파일이 다른 장면으로 밀리던 기존 버그가 해결됐다.**
- **③ 자막 옵션:** 「하단 자막 넣기」/「상단 키워드 넣기」 체크박스를 추가했다. 옵션 `subtitles`/`titles`로 전달되고, `merge_options`에서 `cfg.video.subtitles/titles`가 된다. 프리셋 기본값은 `subtitle.enabled`다.
- **⑦ 편집 범위:** 자막 줄의 문구·시작·끝 수정, 삭제, 추가. 자막·키워드 켜기/끄기, 장면별 키워드 수정, 댓글 시작·길이·위치(위/가운데/아래)·크기 조절과 삭제. 캡처를 끌어다 놓으면 추가된다. 「저장」은 PUT이고, 「적용해서 다시 만들기」는 저장 후 rerender를 호출한다. 「건너뛰기」는 ⑧로 이동한다.
- **⑦ 문구를 고친 줄:** 단어 시간을 글자 수 비율로 다시 나눠 노래방식 강조를 유지한다(`timeline.respread`). 문구·시간을 그대로 둔 줄은 원래 TTS 단어 타이밍을 유지한다.

**댓글 캡처 (이미지 오버레이):**
- **저장 위치:** `output/<잡>/overlays/`. `uploads/`에 두면 장면 배경으로 잘못 쓰이므로 반드시 분리한다.
- **렌더:** `render._apply_overlays`가 `overlay=...:enable='between(t,s,e)'`와 알파 페이드로 합성한다. ASS 자막보다 먼저 합성해서 자막이 캡처 위에 온다.
- **기본 배치:** 재생 위치를 지정하면 그 시점부터 3.5초, 아니면 둘째 장면부터 한 장씩이다. 스타일에 댓글 자리가 있으면 그 자리가 우선한다.

**CapCut 내보내기 (`capcut.py`):**
- **드래프트 폴더 탐색 순서:** `config.capcut.drafts_dir`, CapCut `User Data\Config\globalSetting`의 `currentCustomDraftPath`, 기본 `com.lveditor.draft` 순이다. 이 PC에서는 `C:\capcutproject\CapCut Drafts`로 확인했다(CapCut 9.3 설치).
- **드래프트 형식:** CapCut이 실제로 불러들여 재저장한 스크립트 생성 드래프트(`신발 뒤꿈치…\draft_info.json`, version 360000 / new_version 161.0.0)의 최소 키 구성을 **읽기 전용으로 참고해** 맞췄다. 시간 단위는 µs이고, `clip.transform`은 가운데가 0, 반 화면이 1, 위가 +다.
- **트랙 구성:** 장면 video, 댓글 캡처 video(PIP), 나레이션 audio, BGM audio(짧으면 반복), 하단 자막 text(`type:"subtitle"`), 상단 키워드 text, 출처·텍스트 댓글 text 순이다. 자막을 끈 영상에는 자막 트랙이 없다.
- **파일:** 재료는 드래프트 폴더의 `Resources/`에 복사한다. `draft_content.json`과 같은 내용의 `draft_info.json`, 그리고 `draft_meta_info.json`을 쓴다.
- **기존 파일 보호:** 기존 드래프트와 CapCut 목록 파일(`root_meta_info.json`)은 **절대 수정하지 않는다.** 같은 이름이 있으면 `_2`를 붙인다. 계획에는 "root_meta_info 백업 후 등록"과 "CapCut 실행 중이면 차단"이 있었지만, 기존 파일을 건드리지 않는 쪽이 안전해서 둘 다 넣지 않았다. 대신 "켜져 있었다면 껐다 켜라"고 UI에 안내한다. **실제 CapCut에서 목록에 뜨고 열리는지는 아직 미검증이다.** 안 뜨면 그때 root_meta_info 등록을 검토할 것.
- **옮겨지지 않는 것:** 켄번즈 확대, 장면 전환, 노래방식 강조는 CapCut으로 넘어가지 않는다(UI에 표기).
- **재료 묶음:** `capcut.export_pack(tl, job_dir, out_zip)`이 zip을 만든다. 저장 경로 `output/<잡>/capcut_pack.zip`은 `main.py`의 `/export/pack` 라우트가 정한다. 안에는 `NN_장면.jpg|mp4`(broll은 쓴 구간만 ffmpeg로 잘라 둔다), `narration.mp3`, `bgm.*`, `subtitles.srt`, `keywords.srt`, `comments/`, `순서.txt`가 들어간다.

**레퍼런스 보고 댓글 자동 배치 (`comment_layout.py`):**
- **분석 조건:** 스타일 분석 창의 「댓글 캡처가 언제·어디에 뜨는지도 분석」 체크박스를 켰을 때만 실행된다. API는 `/api/styles/analyze`의 `comment_layout:true`이고, **Gemini 또는 OpenAI 키가 필요하며 사용량 요금이 발생할 수 있다.**
- **분석 방법:** 참고 영상을 받아 2.5초 간격으로 최대 24장 화면을 뽑는다. 각 화면을 비전으로 판별해 "댓글 있음 + 위/가운데/아래"를 얻고, 연속 구간을 슬롯 `{at_ratio, seconds, y}`로 만든다. 여러 영상은 평균 개수만큼 순서별로 평균낸다. 분석한 영상 원본은 지운다.
- **저장:** 스타일 yaml에 `comment_slots`·`comment_pattern`으로 저장한다. 스타일 편집 창에서 「댓글 자동 배치 끄기」로 지울 수 있다.
- **잡에서 쓰는 방식:** 좋아요 많은 댓글을 슬롯 수만큼(최대 2) ④에서 미리 체크한다(`result.suggested_comment_ids`). 검토를 끈 잡은 자동 선택된다. 시작 시간은 `at_ratio × 전체 길이`이고, ⑦에서 올린 캡처도 빈 슬롯부터 채운다.
- **실패 처리:** 분석이 실패해도 말투·구성 분석 결과는 저장되고, findings에 실패 사유가 남는다. **실제 호출은 미검증이다(키 필요).**

**이번 작업 파일:**

| 구분 | 파일 | 내용 |
|---|---|---|
| 신규 | `app/pipeline/timeline.py` (260줄) | timeline 저장·로드·수정 반영(`apply_edit`)·렌더 진입점 |
| 신규 | `app/pipeline/capcut.py` (530줄) | CapCut 드래프트·재료 묶음 |
| 신규 | `app/pipeline/comment_layout.py` (163줄) | 참고 영상 댓글 자리 분석·슬롯 배치 |
| 신규 | `tests/test_timeline_export.py` (318줄) | 목 테스트 18개 |
| 수정 | `run.py` | 렌더 블록을 timeline 방식으로, `rerender()`, `_apply_voice()`, 자막 끄기, 스타일 댓글 자리 |
| 수정 | `render.py` | `_apply_overlays`, 두 렌더 함수에 `overlays` 인자 |
| 수정 | `subtitles.py` | `build_ass(lines=...)`, `words_to_lines`, `write_srt`, 댓글 카드 변수명 충돌 수정 |
| 수정 | `jobs.py` | 큐 `(id, action)`, rerender 작업, 승인 시 음성·`scene_map`, `touch_result` |
| 수정 | `main.py` | 새 라우트 8개, `/files` 하위폴더(overlays·scenes·uploads만) 허용, 스타일 댓글 배치 |
| 수정 | `config.py` | `subtitles`/`titles` 옵션 병합 |
| 수정 | `styles.py` | 스타일에 `comment_slots`·`comment_pattern` 저장 |
| 수정 | `models.py` | `SceneVisual.kind`에 `broll` 추가(기존에 Literal 밖 값 대입하던 문제) |
| 수정 | `presets/*.yaml` | `subtitle.enabled: true` |
| 전면 재구성 | `index.html`(517) · `app.js`(1233) · `style.css`(288) | 사이드바 8단계 UI |

**검증:**
- **자동 점검:** `unittest discover -s tests` **23개 전부 통과**(기존 5 + 신규 18), `compileall` 통과, `git diff --check` 통과.
- **테스트 범위:** timeline 수정·자막 재배분·자막 끄기·SRT·오버레이 필터·렌더 인자·재렌더 실패 시 원본 보존·장면 번호 재매김·CapCut JSON 구조와 참조 무결성·기존 드래프트 보존·zip 구성·댓글 슬롯 계산·스타일 슬롯으로 댓글 자동 선택.
- **브라우저 확인:** 서버를 재시작한 뒤(당시 대기 잡 없음) 1280px과 375px에서 8단계 이동, 활성·비활성, 가로 넘침 0px, JS 오류 없음을 확인했다. ④~⑧은 **브라우저 안에서만 만든 가짜 잡 데이터**로 편집·저장·승인 payload(`scene_map` [0,2] 등)를 확인했다. 서버·파일에는 아무것도 만들지 않았다.
- **서버 라우트:** timeline 없는 잡은 409, 경로 조작은 404, CapCut 폴더 탐지는 정상이었다.

**아직 안 한 것 — 사용자 신호 후 실제 테스트:**
1. 주제 1건 실제 제작 → `timeline.json` 생성 확인 → ⑦에서 자막 1줄 수정 + 캡처 1장 → 다시 만들기 → 영상 확인.
2. ⑧ CapCut 프로젝트 보내기 → CapCut 9.3 목록에 뜨고 열리는지, 트랙·위치·자막 크기가 적절한지 확인. `size` 13/15/8/5는 추정값이다. 안 뜨거나 깨지면 `capcut.py`를 조정한다.
3. 재료 묶음 zip 다운로드 확인.
4. (키가 있을 때) 스타일 분석 + 댓글 배치 분석 1회.

## 2026-09-24 체크포인트 (오전)

> 아래는 오전 기록이다. "다음 작업 우선순위"와 테스트 개수(5개)는 위 오후 섹션이 대체한다(현재 23개). 설계·키·제약 설명은 여전히 유효하다.

**목적:** 한국어 유튜브 쇼츠를 개인 PC에서 만드는 웹 도구다. 주제, 유튜브·기사 링크, 핫이슈, 업로드 영상을 입력받아 자료 조사 → 대본 검토 → 음성·영상 편집 → MP4와 업로드용 문구를 만든다. 자동 유튜브 게시 기능은 없다. 연예·정치·일상·공학/건축 카테고리 프리셋이 있다.

**현재 상태:** 기본 주제 모드 전체 제작과 장면별 이미지 업로드 렌더, 로컬 소스로 만든 broll 렌더는 이전에 실검증했다. 최근 추가한 참고 영상 지침 생성, 영상 업로드 분석, 관련 소스·공개 댓글 후보 검토는 코드와 목 테스트가 있으며, 실제 사용자 영상 및 외부 API를 모두 거치는 제작은 아직 검증하지 않았다. 2026-09-24에 `unittest discover -s tests -v`의 5개 테스트가 모두 통과했다. 지금은 기능을 더 붙이기보다 전체 사용 경로를 확인하고 오류를 고칠 단계다. 이번 체크포인트에서는 이 문서만 새로 수정했다.

**이번 체크포인트의 새 파일** (아래 네 파일과 테스트 파일이 Git 신규 항목):

| 파일 | 내용 |
|---|---|
| `AI Shorts 실행.cmd` | `.venv` Python으로 더블클릭 실행 |
| `app/launcher.py` | 기존 8765 서버 감지, 서버 시작 및 브라우저 열기, PATH 갱신 |
| `app/pipeline/reference.py` | 업로드 영상 프레임 최대 8개 추출·음성 전사·주제와 관련 검색어 생성 |
| `app/pipeline/comments.py` | YouTube Data API로 공개 댓글 후보 수집, 원문 주소 보관 |
| `tests/test_reference_workflow.py` | 업로드 분석·로컬 소스·GPT 화면 분석·댓글 카드·검토 흐름의 외부 응답 목 테스트 5개 |

**이번 체크포인트의 수정 파일** (기존 파일은 변경 이유를 함께 기록):

| 파일 | 변경 내용 |
|---|---|
| `.env.example` | 댓글 수집용 `YOUTUBE_API_KEY` 빈 예시 추가 |
| `HANDOFF.md` | 이전 검증 기록을 보존하면서 현 상태·남은 검증·파일 변경점 갱신 |
| `README.md` | 더블클릭 실행, GPT/Claude, 링크 지침 분석, 업로드·관련 영상·댓글 사용법 추가 |
| `app/config.py` | 사용자 설정 폴더의 `settings.env` 로드 |
| `app/jobs.py` | 대본 검토 화면의 소스·댓글 선택과 업로드 참고 파일을 작업에 전달 |
| `app/main.py` | 업로드 모드 검증, 키 등록 API, 참고 영상 분석의 AI 선택, 검토 승인 항목 추가 |
| `app/pipeline/broll.py` | 로컬 업로드 소스를 다운로드 없이 사용하고 관련 소스 처리 보강 |
| `app/pipeline/llm.py` | Claude/GPT 선택 시 모델 처리 보강 |
| `app/pipeline/models.py` | 스타일의 감정 흐름 필드 추가 |
| `app/pipeline/render.py` | 댓글 카드 자막을 영상 렌더로 전달 |
| `app/pipeline/run.py` | 업로드 분석부터 자료 검색, 관련 영상·댓글 후보, 검토, 편집까지 연결 |
| `app/pipeline/script.py` | 감정 흐름을 대본 지침에 반영 |
| `app/pipeline/styles.py` | 참고 영상 최대 5개 분석, 감정 흐름·지침 생성 확장 |
| `app/pipeline/subtitles.py` | 선택한 댓글을 익명 ASS 텍스트 카드로 표시 |
| `app/pipeline/vision.py` | Gemini 비전 외 GPT 화면 분석 경로 추가 |
| `app/static/app.js` | 업로드 모드, AI·키 선택, 참고 링크 자동 지침, 소스·댓글 검토 UI 동작 |
| `app/static/style.css` | 새 화면 요소 스타일 |
| `app/templates/index.html` | 업로드·AI 선택·키 입력·후보 선택 화면 |
| `requirements.txt` | `faster-whisper` 등 새 분석 경로 의존성 반영 |

**다음 작업 우선순위:** ① 진행 중인 `awaiting_review` 작업이 있으면 사용자가 먼저 검토·완료하도록 하고, 그 뒤 서버를 재시작해 새 코드가 적용됐는지 확인한다(재시작하면 대기 작업은 오류 처리됨). ② 실제 업로드 영상 1건으로 분석 → 자료·영상·댓글 후보 검토 → MP4·`meta.txt`까지 확인한다. 외부 영상 다운로드와 댓글 API는 YouTube 제한·키·할당량에 따라 실패할 수 있으므로 실패 원인을 구분한다. ③ 참고 유튜브 링크로 지침 생성과 GPT 실제 호출을 키가 준비된 경우에만 확인한다. ④ 기사 이미지·출처, Gemini 이미지·비전, Google Flow 실제 이미지 사용을 각각 검증한다. ⑤ 확인된 오류를 고치고 필요한 UI 개선을 한다. Phase F 생성 영상은 미착수이며 후순위다.

**현재 막힘·제약:** 댓글 후보는 `YOUTUBE_API_KEY`가 없으면 비어 있다. GPT 경로는 `OPENAI_API_KEY`, Claude 경로는 CLI 로그인이 필요하다. 업로드 화면 분석은 Gemini 키 또는 GPT 키가 필요하며, 음성도 없는 영상은 화면 분석 키가 없으면 분석할 수 없다. Claude 쪽 업로드 음성 전사는 로컬 Whisper의 첫 모델 다운로드가 필요하다. 실제 댓글 API 호출, 유튜브 소스 다운로드·자막·매칭을 포함한 전체 영상 제작은 미검증이다. `typecast.py` 실호출과 기사 이미지 수집도 미검증이다. 확인된 새 오류는 없으나 검증되지 않은 경로를 완료로 표시하지 말 것. 저장된 `awaiting_review` 작업이 있는지 먼저 확인하고 서버를 종료할 것.

**설계·사용자 요구:** Claude Code 구독 로그인과 GPT API 키 중 선택; 지침 칸의 유튜브 링크 1~5개에서 자막 기반 후킹·전개·감정 흐름·문장 방식 추출(화면·음악 분석은 아님); 업로드 영상은 음성·표본 화면으로 주제를 정하고 관련 영상을 검색; 소스와 공개 댓글은 사용자가 검토 후 선택; 댓글은 실제 캡처가 아닌 익명 텍스트 카드; 자동 게시 없음. 이미지 생성 비용 0원이 기본이고 유료 API는 선택적으로 사용한다. 정치·연예 콘텐츠의 사실 확인과 출처 표기, 저작권 관련 제한을 유지할 것. 중요한 불변조건과 수정 주의는 §9~10을 따른다.

**실행·테스트:** Windows에서 `AI Shorts 실행.cmd`를 더블클릭하거나 `.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765`로 실행한다. 브라우저 주소는 `http://127.0.0.1:8765/`. 의존성은 `requirements.txt`로 설치한다. 점검은 `.venv\\Scripts\\python.exe -m unittest discover -s tests -v`, `.venv\\Scripts\\python.exe -m compileall -q app`, `git diff --check`를 사용한다. 실제 제작 시험은 API 호출·영상 다운로드·비용이 발생할 수 있으니 테스트 대상을 정하고 실행한다.

**키·외부 서비스:** 키 이름과 용도는 §2 및 `.env.example`을 참고한다. `OPENAI_API_KEY`, `GEMINI_API_KEY`, `YOUTUBE_API_KEY`는 웹에서 등록할 수 있으며 Windows `%LOCALAPPDATA%\\AIShorts\\settings.env`에 저장된다. `.env`도 지원하지만 Git에는 포함하지 않는다. YouTube 검색·자막·다운로드는 yt-dlp, 공개 댓글은 공식 YouTube Data API, 음성은 Edge TTS 또는 선택한 서비스, 화면 분석은 Gemini 또는 GPT, 렌더는 ffmpeg에 의존한다. 비밀값·`output/`·`.venv/`는 절대 커밋하지 말 것.

## 2026-09-23 추가: 업로드 참고 영상 → 연관 영상·댓글 검토

- `영상 업로드` 모드: 업로드 목록에서 동영상 한 개를 참고 영상으로 선택한다. `reference.py`가 영상 전체에서 최대 8개 프레임을 고르게 추출하고 음성을 전사한다. Claude 선택 시 로컬 `faster-whisper`, GPT 선택 시 OpenAI `whisper-1` 전사를 쓴다. Gemini 키가 있으면 프레임의 화면 내용도 설명한다. 음성·화면 분석 둘 다 실패하면 명시적 오류를 낸다.
- 분석 결과의 검색어로 뉴스 자료와 관련 유튜브 영상 후보를 찾는다. 업로드 원본도 첫 번째 편집 소스 후보가 된다. `broll.py`는 로컬 소스를 다운로드하지 않고 기존 파일을 그대로 쓴다.
- `broll` 제작 방식에서는 대본 검토 전에 영상 후보를 수집해 체크 목록으로 보여준다. 사용자가 선택한 후보만 이후 장면 매칭에 사용한다.
- `comments.py`는 **선택 사항**인 `YOUTUBE_API_KEY`로 공식 `commentThreads.list` API를 호출한다. 최대 8개 후보를 보여주고 사용자가 고른 최대 2개만 자막 카드로 재구성한다. 작성자 이름은 출력하지 않으며 원문 링크를 `meta.txt`에 기록한다. 실제 스크린샷 수집 기능은 아니다.
- 새 테스트 `tests/test_reference_workflow.py`: 업로드 음성·프레임 분석, 로컬 소스 다운로드 생략, 댓글 수집·카드, 대본 검토까지의 연결을 외부 응답 목으로 검증했다.
- 실제 유튜브 검색으로 관련 영상 메타데이터 2건 반환 확인. 댓글 카드 ASS를 ffmpeg로 1초 영상에 합성하는 스모크 테스트 성공. 실제 소스 다운로드와 댓글 API 키 호출은 미검증.
- `requirements.txt`에 `faster-whisper`를 추가했다. 설치본의 `.venv`에도 설치했다. 최초 로컬 전사는 Whisper 모델 다운로드가 필요하다.
- Gemini 키와 YouTube 키는 웹 화면에서 등록할 수 있다. Gemini 키가 없고 GPT를 선택하면 OpenAI 비전 API로 화면을 분석한다. Claude 선택 시 Gemini 키도 없으면 업로드 영상은 음성 중심으로 분석된다. YouTube 키가 없으면 댓글 카드 후보는 표시되지 않는다. 키는 `USER_ENV`에 저장한다.
- 기존 서버가 실행 중이면 새 코드를 사용하려면 재시작이 필요하다. 작업 중 `awaiting_review` 상태가 있으면 재시작 시 그 작업은 중단 처리되므로 먼저 검토를 끝낼 것.

### 목차

| § | 내용 | |
|---|---|---|
| 1 | 이 프로젝트는 무엇인가 · **구현된 주요 기능** | |
| 2 | 빠른 시작 · **환경변수 / 외부 서비스** | |
| 3 | 완료된 작업 (Phase A~E) | 검증 상태 표 |
| 4 | 파일 구조와 각 파일의 역할 | 신규/수정 구분 |
| 5 | 아키텍처 핵심 | 설계 방향 |
| 6 | **지금 작업 중인 것 / 막혀 있는 것** | ⚠ **가장 먼저 읽을 것** |
| 7 | 알려진 버그 · 제약 | |
| 8 | 다음에 할 일 (우선순위) | ⚠ **여기서 이어서 시작** |
| 9 | 사용자가 요청한 조건 | 반드시 지킬 것 |
| 10 | 건드리면 안 되는 것 · **수정 시 주의** | |
| 11 | 실행 · 테스트 방법 | API·비용 포함 |
| 12 | 정합성 확인 | 문서↔코드 대조 결과 |

---

## 1. 이 프로젝트는 무엇인가

**한국어 유튜브 쇼츠(9:16 세로 영상) 자동 생성기.** 개인용, 로컬 실행, 웹 UI.

```
입력 ──┬─ 주제 한 줄
       ├─ 링크 (유튜브 / 뉴스 기사 / 커뮤니티 글, 여러 개 가능)
       ├─ 핫이슈 자동 (Google Trends KR)
       └─ 업로드 참고 영상 (음성·표본 화면 분석)
                    ↓
     리서치 → 구성 설계 → 대본 → TTS 나레이션 → 비주얼 → ffmpeg 렌더
                    ↓
     output/<잡ID>/final.mp4  +  meta.txt (제목 3안·설명·해시태그·출처)
```

**핵심 목표**: 채널 운영에 실제로 쓸 수 있을 것. 그래서 ①벤치마킹 채널 스타일 모방,
②링크 하나로 끝내기, ③카테고리별 편집 방식 분기, ④비용 최소화가 설계의 축이다.

유튜브 업로드는 하지 않는다 (사용자 요청). mp4와 업로드용 텍스트만 만든다.

### 구현된 주요 기능

| 기능 | 설명 | 상태 |
|---|---|---|
| **4가지 입력 모드** | 주제 한 줄 / 링크(유튜브·기사) / 핫이슈 자동(Google Trends KR) / 업로드 영상 | 주제 ✅ · 링크·핫이슈·업로드 전체 제작 미검증 |
| **자동 리서치** | 네이버 뉴스 API + DuckDuckGo 검색 → trafilatura 본문 추출 | ✅ 검증 (6건 수집) |
| **구성 자동 설계** | 스타일 미지정 시 소재를 먼저 분석해 전개·훅·장면수·`visual_mode` 결정 | ✅ 검증 |
| **스타일 벤치마킹** | 참고 영상 URL → 자막 분석 → 훅 공식·말투·호흡을 지침으로 추출·저장·적용 | ✅ 검증 |
| **대본 생성** | 장면별 나레이션 + 이미지 프롬프트 + 화면 키워드 + 제목 3안·설명·해시태그·출처 | ✅ 검증 |
| **대본 검토·수정** | 웹 UI에서 렌더 전에 멈추고 장면별로 고칠 수 있음 | ✅ 검증 |
| **한국어 TTS** | edge-tts 무료, 단어 단위 타임스탬프 제공. OpenAI·ElevenLabs·Typecast 교체 가능 | edge ✅ · 나머지 미검증 |
| **카라오케 자막** | 현재 읽는 단어만 색 강조(ASS). 화면 키워드·출처 크레딧 별도 스타일 | ✅ 검증 |
| **파일 첨부** | 드래그로 올린 사진·영상을 AI가 내용 보고 장면 배치. `scene_NN_*`은 해당 장면 고정 | 업로드 ✅ · 배치 미검증 |
| **기사 이미지 수집** | 링크에서 본문 이미지를 받아 사용, 화면에 출처 자동 표기 | ⚠ 미검증 |
| **AI 이미지 생성** | Gemini(Nano Banana 2) / fal / HuggingFace / OpenAI / Pollinations | ❌ 미검증 |
| **영상 짜깁기(broll)** | 소스 영상 자동 검색·후보 선택·구간 매칭, 원본 소리 12% + 나레이션 | 로컬 소스 렌더 ✅ · 자동 수집 전체 경로 미검증 |
| **관련 영상·댓글 후보** | 대본 검토 전 영상·공개 댓글을 확인해 선택. 댓글은 익명 텍스트 카드 | 목 테스트 ✅ · 실제 댓글 API 미검증 |
| **렌더링** | 1080×1920 30fps h264+aac. 켄번즈·xfade·BGM 믹스·자막 번인 | ✅ 검증 |
| **웹 UI** | 잡 큐(순차), SSE 실시간 진행상황, 결과 미리보기·다운로드, 비용 표시 | ✅ 부분 검증 |
| **3계층 지침** | 프리셋(카테고리) < 스타일(벤치마킹) < 이번 영상 지침 | ✅ 검증 |
| **안전 강등** | 어느 단계가 실패해도 하위 수단으로 내려가 영상은 반드시 완성 | ✅ 검증 |

---

## 2. 빠른 시작

```bash
cd shorts-ai
.venv\Scripts\activate
uvicorn app.main:app --port 8765
```

→ http://localhost:8765

**Claude를 선택한 경우 최초 1회 로그인** — Claude Code 구독을 사용한다. GPT를 선택하면 대신 OpenAI API 키가 필요하다.

```
claude-login.cmd  (탐색기에서 더블클릭)
```
브라우저가 열리면 로그인 → Authorize → 표시된 코드를 검은 창에 우클릭 붙여넣기 → Enter.
`"loggedIn": true` 가 나오면 성공. 상태 확인은 `python -m app.pipeline.llm status`.

`.env`는 **없어도 동작한다.** Claude 로그인이 있으면 기본 대본·렌더가 가능하다. GPT·댓글·화면 분석·유료 이미지 등은 해당 키가 필요하다.

### 환경변수 · 외부 서비스

`.env.example`은 빈 키 이름 예시다. 실제 키는 웹 화면에서 사용자 설정 폴더에 저장하거나 개인 `.env`에 둔다. 두 파일 모두 Git에 올리지 않는다.

| 환경변수 | 쓰이는 곳 | 없으면 | 비용 |
|---|---|---|---|
| *(없음)* | **Claude 선택 시 대본 생성** — `claude.exe` 구독 로그인 | Claude 경로 사용 불가; GPT 키가 있으면 GPT 선택 가능 | 구독 한도 사용 |
| `GEMINI_API_KEY` | 이미지 생성(`images/gemini.py`), 첨부 파일 비전 분석(`vision.py`) | 이미지는 단색 카드, 첨부는 올린 순서대로 배치 | 이미지 49~194원/장 |
| `FAL_KEY` | 이미지 생성(`images/fal.py`) | 해당 provider 선택 시 단색 카드 | 약 4원/장 |
| `HF_TOKEN` | 이미지 생성(`images/huggingface.py`) | 〃 | 무료(일일 한도) |
| `OPENAI_API_KEY` | GPT 대본·참고 영상 분석, 업로드 음성 전사·화면 분석, 이미지·TTS 선택 기능 | GPT 경로 사용 불가 | 종량제 |
| `YOUTUBE_API_KEY` | 공식 YouTube Data API로 공개 댓글 후보 수집 | 댓글 없이 제작 | API 할당량 필요 |
| `ELEVENLABS_API_KEY` | TTS(`tts/elevenlabs.py`) | 〃 | 종량제 |
| `TYPECAST_API_KEY` | TTS(`tts/typecast.py`) | 〃 | 종량제 |
| `ANTHROPIC_API_KEY` | LLM을 구독 대신 API로 쓸 때 | 구독 경로가 기본이라 불필요 | 종량제 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 뉴스 검색(`research.py`) | DuckDuckGo만 사용 (동작함) | 무료 |

**키 없이 외부와 통신하는 것** (별도 설정 불필요):
- **yt-dlp** — 유튜브 메타·자막·영상 다운로드 (`youtube.py`, `broll.py`)
- **Google Trends RSS** (`geo=KR`) — 핫이슈 자동 모드. 비공식이라 실패 시 네이버 랭킹으로 대체
- **DuckDuckGo 검색** (`ddgs`) — 리서치
- **trafilatura** — 기사 본문 추출
- **Pollinations** — 키 없는 무료 이미지(저화질+워터마크, 최후 수단)

**로컬 필수 도구**:
- **Python 3.12.10** (`.venv`)
- **ffmpeg 9.0.1** — winget 설치. PATH에 없어도 `media.require_ffmpeg()`이 설치 경로를 자동 탐색
- **claude.exe** — Claude Code CLI. 데스크톱 앱 번들(`%APPDATA%\Claude\claude-code\<버전>\`)을 자동 탐색
- **git 2.55** — `C:\Program Files\Git\cmd` (PATH에 없어 전체 경로 필요)

> ⚠️ **`.env`는 `.gitignore`에 있다.** 절대 커밋하지 말 것. `.env.example`은 값이 비어 있어 커밋해도 안전하다.

---

## 3. 완료된 작업 (Phase A~E)

**⚠ 검증 상태 열을 반드시 확인할 것.** "코드만"은 실제로 실행해 본 적이 없다는 뜻이다.

| Phase | 내용 | 검증 상태 |
|---|---|---|
| **초기** | 주제 → 리서치 → 대본 → TTS → 이미지 → mp4 기본 파이프라인, 웹 UI, 잡 큐/SSE | ✅ **실제 실행** — CLI로 6단계 전부 완주 확인 (2026-09-22). 1080×1920 h264+aac, 자막·키워드·싱크 정상 |
| **A** 스타일 지침 | 참고 영상 URL → 자막 분석 → 스타일 지침 자동 추출·저장·적용 | ✅ **실제 실행** — 건축 채널 2편 분석, 스타일 적용/미적용 대본 차이 확인 |
| **B** 링크 분석 | 유튜브가 아닌 링크를 기사 모드로 분기, 본문+이미지 수집, 출처 자동 표기 | ⚠️ **부분 실검증** — 실제 정부 기사 본문 1건 추출. 이미지 수집·전체 영상은 미검증 |
| **C** 파일 첨부 | 업로드(토큰 staging), Gemini 비전으로 내용 파악 후 장면 매칭 | ⚠️ **부분** — 브라우저의 장면별 업로드→배치→영상 반영 확인. 비전 매칭은 키가 없어 미검증 |
| **D** Gemini 이미지 | Nano Banana 2 3종 provider, UI 실시간 비용 표시 | ❌ **코드만** — API 호출 0회 |
| **E** 영상 짜깁기 | 소스 자동검색/링크 지정 → 장면별 구간 매칭 → 원본 소리 덕킹 + 나레이션 | ⚠️ **부분 실검증** — 로컬 소스 2개+이미지 실제 렌더 성공. 자동검색·다운로드·매칭은 미검증 |
| **E** Flow 워크플로 | 이미지 프롬프트 복사 → Flow에서 무료 생성 → 장면별 업로드 | ⚠️ **부분 실검증** — 브라우저에서 복사→장면별 업로드→렌더 성공. Google Flow 서비스에서 직접 생성하는 단계는 미검증 |

**Phase F (Omni Flash 영상 생성)는 착수하지 않았다.**

---

## 4. 파일 구조와 각 파일의 역할

아래 표의 `■`/`▲`와 줄 수는 **2026-09-22 이전 확장 당시 기록**이다. 이번 체크포인트의 정확한 신규·수정 목록은 맨 위 표를 볼 것. 주요 파일의 현재 역할은 다음과 같다.

### 파이프라인 (`app/pipeline/`)

| 파일 | 줄수 | 역할 |
|---|---|---|
| `run.py` ▲ | 당시 502 | **오케스트레이터.** 4개 입력 모드, 후보 검토, 6단계 제작, CLI 겸용 |
| `models.py` ▲ | 172 | 모든 pydantic 모델. LLM 구조화 출력 스키마 겸용 |
| `script.py` ▲ | 170 | Claude 프롬프트 4종: 구성설계(`make_plan`)·대본(`write_script`)·클립계획·트렌드선택 |
| `llm.py` ▲ | 216 | LLM provider 3종 (claude 구독 / openai / anthropic). `claude.exe` 자동 탐색 |
| `styles.py` ■ | 200 | 스타일 지침 CRUD + 참고 영상 자동 분석 |
| `article.py` ■ | 246 | 기사·글 링크 본문 추출 + 이미지 수집 + 출처 문구 |
| `assets.py` ■ | 206 | 첨부 파일 관리 + **장면별 비주얼 우선순위 결정** |
| `vision.py` ■ | 당시 120 | Gemini/GPT 비전으로 이미지 내용 파악 → 장면 매칭 |
| `broll.py` ■ | 당시 228 | 소스 영상 검색·수집, 로컬 소스 사용, 자막 타임라인, 장면별 구간 매칭·정규화 |
| `reference.py` | 신규 | 업로드 참고 영상의 음성·화면 분석으로 주제·검색어 추출 |
| `comments.py` | 신규 | 공개 댓글 후보 수집, 검토용 출처 제공 |
| `timeline.py` | 260 (09-24) | 렌더 재료 `timeline.json` 저장·수정 반영·렌더 진입점 (⑦ 다시 만들기) |
| `capcut.py` | 530 (09-24) | CapCut 드래프트 생성 + 재료 묶음 zip |
| `comment_layout.py` | 163 (09-24) | 참고 영상 화면에서 댓글 자리 분석 → 스타일 `comment_slots` |
| `render.py` ▲ | 305 | ffmpeg 3종: `render_slideshow` / `render_clips` / `render_broll`(신규) |
| `subtitles.py` ▲ | 119 | ASS 자막 생성. `Sub`(카라오케)·`Title`(키워드)·`Credit`(출처, 신규) |
| `media.py` ▲ | 135 | ffmpeg 유틸. `extract_frames`·`has_audio` 신규, ffmpeg 경로 자동 탐색 |
| `youtube.py` ▲ | 169 | yt-dlp 메타·자막(단어 타임스탬프)·다운로드, whisper 대체 |
| `research.py` | 134 | 뉴스 검색(네이버/DDG) + 본문 추출, Google Trends KR |
| `clips.py` | 42 | 클립 모드 구간 정규화·자막 리타이밍 |

### Provider 어댑터

| 폴더 | 파일 | 비고 |
|---|---|---|
| `images/` | `base.py`, `gemini.py` ■, `fal.py`, `huggingface.py`, `openai_img.py`, `pollinations.py` | `__init__.get_images()`가 분기. **`none`이면 `None` 반환** |
| `tts/` | `base.py`, `edge.py`, `openai_tts.py`, `elevenlabs.py`, `typecast.py` | 기본 `edge`(무료, 단어 타임스탬프 제공) |

### 웹

| 파일 | 줄수 | 역할 |
|---|---|---|
| `app/main.py` ▲ | 당시 305 | FastAPI. 업로드 모드·키 등록·참고 영상 분석·잡 API + SSE |
| `app/jobs.py` ▲ | 당시 212 | 잡 큐(순차 1개씩), 대본·영상·댓글 검토, 상태 영속화, 업로드 이동 |
| `app/config.py` ▲ | 114 | config/preset/style 로딩, `merge_options` 우선순위 |
| `app/templates/index.html` ▲ | 517 (09-24) | 단일 페이지. 왼쪽 8단계 사이드바 + 단계별 패널 |
| `app/static/app.js` ▲ | 1233 (09-24) | 전체 UI 로직 (빌드 없음). `stepEnabled`/`go`/`onJob`이 단계 이동의 중심 |
| `app/static/style.css` ▲ | 288 (09-24) | 다크 테마. 760px 이하에서 사이드바가 위쪽 가로 메뉴로 |

### 설정·데이터

```
config.yaml           기본 provider·해상도·길이·볼륨
presets/*.yaml        카테고리 4종 (daily/engineering/entertainment/politics)
styles/*.yaml         저장된 스타일 지침 (현재 1개: style-f8b83e20)
assets/bgm/           mp3 넣으면 자동 사용 (현재 비어 있음)
assets/fonts/         otf/ttf (현재 비어 있음, 맑은 고딕 사용 중)
output/<잡ID>/        결과물·검증 작업·업로드 임시 파일 — .gitignore 제외
claude-login.cmd      Claude CLI 로그인 헬퍼
AI Shorts 실행.cmd     Windows 더블클릭 실행
app/launcher.py       서버 실행·브라우저 열기
```

---

## 5. 아키텍처 핵심

### 파이프라인 6단계 (`run.py: run_pipeline`)

```
1 리서치/입력분석  → mode별 분기 (topic / url→유튜브·기사 / auto / upload→음성·화면)
2 구성 설계        → 스타일 없으면 AutoPlan 으로 구성·장면수·visual_mode 자동 결정
3 대본            → Script (장면별 나레이션·이미지프롬프트·화면키워드 + 제목/설명/태그)
     ↕ review 콜백으로 여기서 멈추고 대본·관련 영상·댓글 후보를 사용자에게 검토받음
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

## 6. 지금 작업 중인 것 / 막혀 있는 것 — **가장 중요**

### 6.0 지금 어디까지 와 있나

**단계: 기존 기능과 9월 23일 추가 기능의 실검증 진행 중.** 새 기능 개발보다 실제 사용 흐름 확인이 우선이다.

Phase A~E와 업로드·관련 영상·댓글 선택 경로의 코드는 작성됐고, 지금은 **하나씩 실제로 돌려 보며 버그를 잡는 중**이다.
직전에 무과금 전체 경로(주제 → 대본 → TTS → 렌더)를 2회 돌려 길이 버그 1건을 찾아 고쳤다(§7).

| 검증 | 상태 |
|---|---|
| 주제 모드 CLI 전체 실행 | ✅ 완료 (2026-09-22) |
| 웹 UI Flow 워크플로 (프롬프트 복사 → 업로드 → 렌더) | ✅ 기존/테스트 이미지로 완료 (2026-09-23). Flow 서비스에서 이미지 생성은 미검증 |
| `render_broll` 실제 렌더 | ✅ 6.1초 샘플 성공 (2026-09-23). 자동 소스 수집 흐름은 미검증 |
| 기사 링크 모드 | ⚠️ 실제 정책 기사 본문 1건 추출 성공. 이미지 수집·전체 영상은 미검증 |
| Gemini 이미지·비전 | ⬜ 키 없어 보류 |
| 8단계 사이드바 UI (2026-09-24) | ✅ 브라우저 확인(1280px·375px, 가짜 잡 데이터로 ④~⑧ 조작). 실제 잡으로는 미확인 |
| ⑦ 자막 수정·댓글 캡처 → 다시 만들기 | ⚠️ 목 테스트만. 실제 `timeline.json` 생성·재렌더는 미실행 |
| ⑧ CapCut 드래프트·재료 묶음 | ⚠️ 목 테스트만(임시 폴더). **CapCut에서 실제로 열리는지 미확인** |
| 참고 영상 댓글 자리 분석 | ⬜ 키 필요 · 목 테스트만 |
| Phase F (Omni 영상) | ⬜ 미착수 (기능 자체가 없음) |

다음 두 경로는 외부 준비가 필요하다:
- **Gemini 경로** — 사용자가 화면에서 또는 개인 `.env`에 `GEMINI_API_KEY`를 넣어야 함
- **Flow 워크플로** — 사용자가 Google Flow에서 이미지를 만들어 업로드해야 전 구간 확인 가능

### 6.1 Phase B~E 실검증 범위

사용자가 2026-09-23 테스트 진행을 요청했다. 기존의 문법·가짜 데이터 점검에 더해 다음을 실행했다:

- `python -m compileall app` 통과
- import·FastAPI 라우트 등록 확인
- **가짜 데이터로 순수 로직 검증** (HTML 파서, 우선순위 배치, 구간 정규화, 파일명 규칙)
- 실제 정부 정책 기사에서 본문 1,048자를 추출했다. 해당 테스트는 사진을 내려받지 않았다.
- 브라우저에서 프롬프트 복사 버튼, 장면별 사진 2장 업로드, 대본 승인, 1080×1920 MP4 완성을 확인했다. 기존 대본·음성을 재사용했다.
- 서로 다른 색의 테스트 이미지가 완성 영상의 첫 장면과 둘째 장면에 각각 나타나는지 프레임으로 확인했다.
- `render_broll`에 영상(음성 있음/없음)·이미지·반복 소스·BGM을 섞어 실제 렌더했다.
- Claude Code CLI를 설치하고 구독 로그인 및 구조화 응답 호출을 확인했다.

### 6.2 가장 위험한 미검증 지점

| 위험도 | 항목 | 이유 |
|---|---|---|
| 🔴 높음 | **broll 전체 흐름** | yt-dlp 검색 → 자막 → 매칭 → 720p 다운로드까지 외부 의존이 4단계 |
| 🟡 중간 | **Gemini 이미지·비전** | `.env` 없어 한 번도 호출 못 함. 응답 파싱은 가짜 JSON으로만 확인 |
| 🟡 중간 | **기사 이미지 수집** | 실제 뉴스 사이트는 지연로딩·CDN·referer 검사가 제각각. 가짜 HTML만 통과 |
| 🟢 낮음 | 첨부 비전 매칭 | 키 없으면 "올린 순서대로" 경로로 자동 강등되므로 최악에도 동작 |

### 6.3 환경 상태

- **9월 23일 확인 당시 `.env` 없음.** 현재 키 유무는 값 자체를 노출하지 말고 웹 화면의 등록 상태로 확인할 것. 웹 등록 키는 프로젝트 밖 `USER_ENV`에 있다
- Claude Code CLI 2.1.268을 공식 WinGet 패키지로 별도 설치. 구독 로그인 `loggedIn: true`와 구조화 응답 호출 확인
- Python 3.12.10 / ffmpeg 9.0.1 (winget 설치, `media.py`가 경로를 자동으로 찾음)
- `styles/`에 1개 (`style-f8b83e20`)
- CapCut 데스크톱 9.3 설치됨. 새 드래프트 저장 폴더는 `C:\capcutproject\CapCut Drafts`다. `%LOCALAPPDATA%\CapCut\User Data\Config\globalSetting`의 `currentCustomDraftPath`에서 읽는다. 기존 드래프트 4개(경제 작업·릴스·신발 뒤꿈치 등)는 사용자 작업물이므로 절대 수정하지 말 것
- `output/`에는 기존 검증 산출물과 웹 작업이 있을 수 있다. Git 제외 대상이며, 진행 중인 `awaiting_review` 작업은 서버 재시작 전에 처리할 것

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
| **영상이 목표보다 18% 길어짐** (55초 요청 → 64.9초) | ① `CHARS_PER_SEC`가 4.7로 실제(6.35)보다 35% 낮아 글자수를 적게 요청 ② 그마저도 Claude가 무시하고 412자 작성(요청 218~278자) | `CHARS_PER_SEC = 6.35`(실측)로 정정 + 프롬프트에 상한을 강하게 명시하고 장면당 평균 글자수까지 제시. **재실행 결과 347자 → 56.3초 (오차 +2.4%)** |
| broll 렌더 즉시 실패 | `afade` 시작 시간이 `-1.5`초로 고정되어 ffmpeg가 거부 | 전체 클립 길이에서 마지막 1.5초 시작 시점을 계산. 음성·무음 영상과 이미지 혼합 렌더 성공 |
| 결과 화면 비주얼 요약 누락 | `Job.public()`이 `visuals` 정보를 제외 | API 결과에 포함하고 broll도 요약 표기. 브라우저에서 `첨부 2` 확인 |
| 업로드 설명에 출처 URL 중복 | 이미 설명에 들어 있는 URL을 UI가 다시 덧붙임 | 설명에 없는 URL만 추가. 브라우저에서 중복 제거 확인 |
| 검토 중 장면을 지우면 올린 사진이 옆 장면으로 밀림 (2026-09-24) | `scene_NN_` 파일은 원래 번호 기준인데, 장면 삭제 후 번호가 당겨짐 | 승인 시 `scene_map` 전송 → `jobs._remap_scene_files`가 번호 재매김, 삭제 장면은 `_removed_` (테스트 있음) |
| `SceneVisual.kind`에 없는 `"broll"` 대입 (2026-09-24) | Literal 목록 누락 | `models.py` Literal에 `broll` 추가 |
| 오류 잡의 상태 문구가 "오류:" 뒤 빈칸 (2026-09-24) | 재시작 중단 잡은 `error` 필드가 비고 `message`에만 사유가 있음 | UI가 `error || message` 표시 |

### 미해결 / 제약

- **UI에서 `visual_mode`를 직접 고를 수 없다.** 프리셋 값 또는 "원본 클립 재편집" 체크박스로만 결정된다.
  `run_pipeline(visual_mode=)` 인자와 CLI `--visual`은 있으므로, UI 드롭다운만 추가하면 된다
- ~~검토 화면에 비주얼 미리보기가 없다~~ → 2026-09-24 ⑥ 화면 배치에 장면별 올린 파일 썸네일 추가(`GET /api/jobs/{id}/scene-visuals`). 단, 자동 배치(기사 이미지·AI 생성)될 결과는 렌더 전에는 "자동"으로만 표시된다
- **CapCut 드래프트 실사용 미검증.** 트랙·좌표·자막 글자 크기(`size` 13/15/8/5)는 추정값이다. CapCut 목록에 안 뜨면 `root_meta_info.json` 등록이 필요할 수 있으나, 기존 파일 수정이므로 사용자 확인 후 백업을 거쳐서만 할 것
- **⑦ 미리보기는 마지막 렌더 결과다.** 편집 중 실시간 미리보기는 없다(수정 후 다시 만들기 필요)
- **timeline 없는 잡**(2026-09-24 이전 잡, 클립 재편집 잡)은 ⑦·CapCut 불가. MP4 다운로드만 된다
- **다시 만들기 중 서버를 재시작하면** 잡은 디스크상 `done`으로 남는다(재렌더 대기 상태는 저장하지 않음). 기존 `final.mp4`는 보존된다
- **`typecast.py`의 API 스펙 미확인.** 문서 기준으로 작성했고 호출해 본 적 없다
- **Pollinations 무료 티어는 저화질+워터마크.** 모델을 바꿔도 같은 이미지가 나온다(실측). 최후 수단
- **잡은 순차 1개씩** 처리된다. 동시 실행 불가
- 서버 재시작 시 진행 중이던 잡은 `error`로 표시된다 (`jobs.py:_load_from_disk`)

---

## 8. 이전 작업 목록 (2026-09-23 기준 기록)

**현재 우선순위는 문서 맨 위의 2026-09-24 체크포인트 목록을 따른다.** 아래는 이전 검증의 경과와 남아 있던 과제 기록이다.

### ~~1️⃣ 키 없이 되는 경로 실검증~~ ✅ 완료 (2026-09-22)

CLI 전체 실행 2회로 확인했다. 6단계 전부 통과, `final.mp4` 1080×1920 h264+aac 생성,
자막·화면 키워드·싱크 정상, `meta.txt`에 제목 3안·설명·해시태그·출처 정상 기록.
이 과정에서 길이 버그를 찾아 고쳤다(§7 참고).

**2026-09-23 추가 검증**: 웹 UI에서 대본 검토 → 프롬프트 복사 버튼 → 장면별 `＋` 업로드 → 렌더를 완주했다.
`scene_NN_*` 고정 배치와 영상 속 장면 순서도 확인했다. Google Flow 사이트에서 이미지 생성은 아직 직접 시험하지 않았다.

### ~~2️⃣ `render_broll` 실제 렌더 1회~~ ✅ 완료 (2026-09-23)

로컬 mp4 2개(음성 있는 영상·무음 영상)와 이미지, 반복 소스, BGM을 넣어 실제 렌더했다.
처음에는 음수 `afade` 시작 시간 때문에 실패했고, 수정 후 360×640 h264+aac 6.1초 MP4가 생성됐다.
남은 것은 실제 유튜브 소스 자동검색·자막·매칭·다운로드를 거치는 **전체 broll 흐름**이다.

### 3️⃣ 기사 링크 모드 실검증

정부 정책 기사 URL에서 본문 1,048자 추출은 확인했다. 사진을 내려받지 않은 테스트다.
남은 것은 사이트별 이미지 수집과 출처 표시가 실제 영상에서 보이는지 확인하는 일이다.

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
- ~~검토 화면 장면별 비주얼 미리보기 + 교체~~ ✅ 2026-09-24 ⑥ 화면 배치 (올린 파일 썸네일·교체)
- 잡 취소 버튼
- ~~단계별 사이드바·자막 수정·댓글 캡처·CapCut 내보내기~~ ✅ 2026-09-24 코드 완성 (실사용 검증은 맨 위 목록)

---

## 9. 사용자가 요청한 조건 — 반드시 지킬 것

1. **개발 중에는 사용자 신호 없이 샘플 영상·대본을 만들지 않는다.** 유료 API 호출과 Claude 구독을 쓰는 실행 금지.
   사용자가 2026-09-23 테스트 진행을 요청하여 기존 자료를 이용한 렌더와 Claude 구독 구조화 응답 1회를 확인했다.
   *허용*: import·문법·라우트 확인, 가짜 데이터 로직 테스트, 브라우저 DOM 확인(잡 생성 없이)
2. **이미지 비용 0원이 기본.** `images.provider: none` + Flow에서 만든 이미지 첨부.
   유료 provider는 UI에서 명시적으로 골라야만 쓰인다
3. **영상 짜깁기는 원본 소리를 12%로 깔고 나레이션을 위에** 얹는다 (완전 음소거 아님)
4. **대본 AI는 Claude 구독 로그인 또는 GPT API 키 중 선택.** Claude 경로에는 API 키를 요구하지 않는다
5. **유튜브 자동 업로드는 하지 않는다.** mp4 + 메타 텍스트까지만
6. 지침은 3계층으로 분리해 각각 저장·재사용할 수 있어야 한다
7. 웹 UI로 혼자 쓰는 도구. 복잡한 빌드 체인 없이
8. **자막·댓글은 선택 사항** (2026-09-24). 자막이 필요 없는 영상도 있으니 아무것도 넣지 않고 넘어가도 영상이 완성돼야 한다. ⑦은 「건너뛰기」가 가능해야 하고, ③에서 자막을 처음부터 끌 수 있어야 한다
9. **왼쪽 단계 메뉴 UI** (TubeFactory 참고) + 마지막에 **CapCut으로 내보내기**. 댓글 캡처는 직접 올리는 방법과 레퍼런스 분석으로 자동 배치하는 방법 둘 다
10. **Git:** 기존 커밋 히스토리 삭제·수정 금지, force push 금지. 비밀값은 절대 커밋하지 않는다. 인증 문제는 우회하지 말고 사용자에게 설명한다

---

## 10. 건드리면 안 되는 것

| 대상 | 이유 |
|---|---|
| **`script.CHARS_PER_SEC = 6.35`** | edge-tts ko-KR + rate `+5%` 에서 **실측한 값**. 추측으로 바꾸지 말 것. TTS provider나 `config.yaml`의 `tts.rate`를 바꿨다면 재실측해 갱신 (나레이션 총 글자수 ÷ `narration.mp3` 길이) |
| **스타일 id의 ASCII 규칙** (`styles.slugify`) | 한글 파일명은 Windows/OneDrive NFC/NFD 불일치로 조회 실패·중복을 일으킨다. 실제로 겪은 버그 |
| **`_prepare_visuals`의 fallback 체인** | "무슨 일이 있어도 영상은 완성된다"가 설계 원칙. 각 단계 실패 시 다음으로 강등되는 구조를 깨지 말 것 |
| **저작권 장치** | 출처 자동 표기(ASS `Credit`), 소스당 길이 상한, UI 경고 문구. 법적 리스크 완화 장치이므로 임의로 제거 금지 |
| **`youtube.py`의 자막 재시도·백오프** | 없애면 429로 바로 실패한다 |
| **영상별 하위 폴더 분리** (`ref{n}/`, `src{n}/`) | 같은 폴더에 받으면 자막 파일명이 충돌한다 |
| **`llm.py`의 `CLAUDE_CODE_*` 환경변수 제거** | Claude Code 안에서 실행될 때 중첩 세션이 꼬인다 |
| **정치·연예 프리셋의 사실기반·중립 규칙** | 명예훼손·허위정보 리스크 |
| `.venv/`, `output/`, `.env` | 각각 의존성, 결과물, 비밀값 |
| **사용자의 기존 CapCut 드래프트와 `root_meta_info.json`** | 사용자 작업물. `capcut.export_draft`는 새 폴더만 만들고 이름이 겹치면 `_2`를 붙인다. 이 원칙을 깨지 말 것 |
| **댓글 캡처는 `overlays/`에** | `uploads/`에 넣으면 `assets.load_assets`가 장면 배경으로 가져간다 |
| **다시 만들기의 "새 파일로 렌더 후 교체"** (`run.rerender`) | 실패해도 기존 `final.mp4`가 남아야 한다 |

### 수정할 때 특히 주의할 것

위가 "손대지 말 것"이라면, 아래는 **고쳐도 되지만 잘못 고치기 쉬운 곳**이다.

| 위치 | 주의점 |
|---|---|
| `run.py` | 파이프라인 전체가 한 함수(`run_pipeline`)에 들어 있다. 단계 순서에 의존하는 변수(`gap`·`durations`·`all_sources`·`broll_picks`)가 많으니, 블록을 옮기면 정의 전에 참조하는 일이 생긴다 |
| `render.py` 필터그래프 | ffmpeg 필터는 문자열 조립이라 **오타가 런타임에만 드러난다**. 고친 뒤 반드시 실제 렌더로 확인할 것. 라벨(`[v0]`, `[a0]`)은 유일해야 하고 모두 소비돼야 한다 |
| `models.py`의 pydantic 필드 | **LLM 구조화 출력 스키마를 겸한다.** `Field(description=...)`이 곧 모델에게 주는 지시다. 설명을 지우면 출력 품질이 떨어진다 |
| `script.py` 프롬프트 | 블록 순서(`preset → style → autoplan → instructions`)가 곧 지침 우선순위다. 순서를 바꾸면 3계층 규칙이 깨진다 |
| `assets.py`의 `SCENE_PIN` 정규식 | `\b`를 쓰면 `scene_03_x` 를 놓친다(숫자와 `_`가 둘 다 단어문자). `(?!\d)`를 유지할 것 |
| `subtitles.py`의 ASS 문자열 | 색은 `&HAABBGGRR`(BGR 역순)이다. RGB로 착각하기 쉽다 |
| `config.py`의 `merge_options` | 우선순위가 `config < 프리셋 < UI`다. 새 옵션을 추가할 때 이 순서를 지킬 것 |
| provider 어댑터 추가 | `ImageProvider`/`TTSProvider` 인터페이스를 지키고, **실패 시 반드시 예외를 던질 것**. 조용히 실패하면 fallback 체인이 동작하지 않는다 |
| 잡 상태(`jobs.py`) | `awaiting_review`는 `asyncio.Event`로 대기한다. 상태 전이를 바꾸면 검토 화면이 영영 안 풀릴 수 있다. 큐 항목은 `(job_id, "run"|"rerender")` 튜플이다 |
| `timeline.py` | 첫 렌더와 다시 만들기가 **같은 `render_timeline`**을 쓴다. 한쪽만 고치지 말 것. `apply_edit`는 클라이언트 입력을 검증한다(시간 범위 자르기, 모르는 댓글 id 무시, 이미지 경로 변경 불가). 이 검증을 약하게 만들지 말 것 |
| `render._apply_overlays` | 오버레이 입력 번호는 나레이션·BGM 입력 **뒤**부터 매겨진다. 입력 순서를 바꾸면 번호가 어긋난다. ASS 자막보다 먼저 합성해야 자막이 위에 온다 |
| `capcut.py` | 시간은 µs, `clip.transform`은 가운데 0·반 화면 1·위가 +다. 소재 id와 `extra_material_refs`가 서로 맞아야 CapCut이 연다(테스트가 참조 무결성을 검사) |
| `app.js`의 단계 이동 | `stepEnabled`(활성 조건)·`go`(표시)·`onJob`(SSE 반영·자동 이동)이 중심이다. ⑦ 편집 중(`capDirty`)에는 이동 전에 확인창을 띄운다 |
| `/files/{job_id}/{name:path}` | 하위 폴더는 `overlays`·`scenes`·`uploads`만 허용하고 `..`·`\`를 막는다. 허용 목록을 넓힐 때 주의 |

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

### API 엔드포인트 (현재 `app/main.py`의 사용자 정의 라우트 32개 — 아래 목록 + 소스 대장 `GET /api/jobs/{job_id}/sources`, 설계도 `GET /api/jobs/{job_id}/blueprint`)

```
GET     /                                    웹 UI

POST    /api/settings/gemini-key
POST    /api/settings/youtube-key
POST    /api/settings/openai-key

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
GET     /api/jobs/{job_id}/scene-visuals     ⑥ 장면별로 올린 파일 목록 (미리보기)
GET     /api/jobs/{job_id}/sources           소스 대장 (권리·사용 가능 여부)
GET     /api/jobs/{job_id}/blueprint         장면 설계도 (2C 이후 실제 음성 시간 포함)
GET     /api/jobs/{job_id}/events            SSE 진행상황

GET     /api/jobs/{job_id}/timeline          ⑦ 렌더 재료 (없으면 409)
PUT     /api/jobs/{job_id}/timeline          ⑦ 자막·키워드·댓글 수정 저장 (done 일 때만)
POST    /api/jobs/{job_id}/rerender          ⑦ 영상만 다시 만들기 (큐에 들어감)
POST    /api/jobs/{job_id}/overlays          ⑦ 댓글 캡처 이미지 추가 (overlays/ 에 저장)
GET     /api/capcut                          CapCut 드래프트 폴더 탐지 결과
POST    /api/jobs/{job_id}/export/capcut     ⑧ CapCut 프로젝트 만들기
POST    /api/jobs/{job_id}/export/pack       ⑧ 재료 묶음 capcut_pack.zip

GET     /files/{job_id}/{name:path}          결과물. 하위폴더는 overlays·scenes·uploads 만
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

**아래 표는 2026-09-22 당시의 검증 기록으로, 현재 수치가 아니다.** 현재 신규·수정 파일 목록과 검증 상태는 맨 위 체크포인트를 따른다. 현재 사용자 정의 라우트는 `app/main.py`에서 22개이며, `.env.example`에는 `YOUTUBE_API_KEY`가 추가됐다.

2026-09-22에 실제 파일 상태와 대조한 당시 결과:

| 항목 | 문서 | 실제 | |
|---|---|---|---|
| 소스 파일 수 | 47개 (HANDOFF 제외) | 47개 | ✅ |
| `app/` 코드량 | 36파일 5,208줄 (.py 4,190줄) | 동일 | ✅ |
| 파일별 줄 수 (§4 표) | 21개 파일 전부 | 동일 | ✅ |
| API 엔드포인트 | 18개 (+ `GET /`) | 18개 | ✅ |
| 라우트 경로·파라미터명 | `{job_id}`/`{preset_id}`/`{style_id}`/`{token}` | 동일 | ✅ |
| 환경변수 8종 | 문서·`.env.example`·코드 3중 대조 | 전부 일치 | ✅ |
| `CHARS_PER_SEC` | 6.35 | 6.35 | ✅ |
| image provider 8종 / tts 4종 | 문서 목록 | `get_images`/`get_tts` 분기와 일치 | ✅ |
| `images.provider` | `none` | `none` (`get_images()`→`None`) | ✅ |
| `llm.provider` / model | `claude` / `claude-opus-5` | 동일 | ✅ |
| 프리셋 visual_mode | daily·engineering=images, entertainment·politics=broll | 동일 | ✅ |
| broll 설정 | 볼륨 0.12 / 소스 4개 / 소스당 15초 | 동일 | ✅ |
| 스타일 | 1개 (`style-f8b83e20`) | 1개 | ✅ |
| `output/` | 검증 산출물 2개 (gitignore) | v1_topic, v2_len | ✅ |
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

### 2026-09-22 추가 — 무과금 전체 실행 검증

`--topic "엘리베이터 케이블이 끊어져도 안 떨어지는 이유" --preset engineering` 으로 2회 실행.

| | v1 (수정 전) | v2 (수정 후) |
|---|---|---|
| 장면 / 글자수 | 9장면 412자 | 8장면 347자 |
| 영상 길이 | 64.9초 (목표 55초 대비 **+18%**) | **56.3초 (+2.4%)** |
| 해상도·코덱 | 1080×1920 h264 + aac 44.1kHz | 동일 |
| 자막·키워드·싱크 | 정상 | 정상 |
| `meta.txt` | 제목 3안·설명·태그·출처 정상 | 정상 |

v1에서 길이 버그를 발견해 `CHARS_PER_SEC`를 실측값으로 고치고 프롬프트를 강화한 뒤 v2로 재검증했다.
이 커밋 이후 `output/`의 `v1_topic`·`v2_len`은 검증용 산출물이며 `.gitignore`로 제외된다.

### 2026-09-23 추가 — 웹 업로드·broll·기사 실검증

- 웹 UI에서 대본 검토 대기 → 프롬프트 복사 버튼 → 장면별 사진 2장 업로드 → 승인 → MP4 다운로드까지 확인했다. 대본과 음성은 9월 22일 산출물을 재사용했다.
- 빨강/파랑 테스트 이미지를 각각 업로드한 별도 실행에서 완성 영상 1초·11초 프레임의 색이 순서대로 일치했다.
- 로컬 소리 있는 영상·무음 영상·이미지·반복 영상·BGM을 섞은 `render_broll()` 6.1초 영상이 생성됐다. 초기 음수 `afade` 오류를 고쳤다.
- 실제 정부 정책 기사 1건에서 본문 1,048자를 추출했다. 이미지 수집과 기사 모드 영상 렌더는 아직 검증하지 않았다.
- 공식 WinGet Claude Code CLI 2.1.268 설치 후 `loggedIn: true`와 구조화 응답 1회를 확인했다. 유료 이미지 API는 호출하지 않았다.
- 남은 주요 검증은 외부 유튜브 소스 자동검색부터 이어지는 전체 broll 흐름, 실제 기사 이미지·출처 렌더, Google Flow에서 직접 만든 이미지, Gemini API(키 필요)다.

### 2026-09-23 추가 — 더블클릭 실행

- 프로젝트 루트의 `AI Shorts 실행.cmd`가 `.venv`의 Python으로 `app.launcher`를 실행한다. 서버가 준비되면 기본 브라우저에서 `http://127.0.0.1:8765/`를 연다.
- 기존 AI Shorts 서버가 있으면 브라우저만 열고, 다른 프로그램이 포트를 쓰면 오류를 알린다. 실행 창을 닫으면 새로 띄운 서버가 종료된다.
- 설치 직후 Windows 탐색기가 오래된 PATH를 유지하는 경우를 대비해 사용자 PATH를 다시 읽는다. 이 경로에서 Claude CLI와 ffmpeg를 찾는 것을 확인했다.
- 현재 실행 중인 서버를 건드리지 않고 임시 8766 포트에서 서버 시작·준비 확인·브라우저 호출·종료 흐름을 검증했다.

### 2026-09-23 추가 — 지침 칸의 참고 영상 분석과 AI 선택

- `이번 영상 지침`에 유튜브 링크 1~5개를 넣으면 분석 버튼이 나타난다. `만들기`를 바로 눌러도 `POST /api/styles/analyze`를 `save=false`로 먼저 호출해 편집 가능한 지침으로 바꾼 뒤 잡을 만든다. 자유 메모는 보존하고 분석 근거를 별도로 표시한다.
- 분석 결과에 `emotional_arc`를 추가해 저장 스타일·지침·대본 프롬프트에 연결했다. 시간별 자막을 최대 12,000자 사용하며 자막이 없으면 제목만으로 스타일을 추측하지 않고 오류를 반환한다. 화면과 음악은 분석 범위 밖이다.
- 분석 API가 화면에서 선택한 Claude 또는 GPT의 provider/model을 받는다. GPT API 키는 로컬 화면에서 `%LOCALAPPDATA%/AIShorts/settings.env`에 등록 가능하며, 실행 중인 서버 환경에도 즉시 반영된다. OneDrive 프로젝트 폴더에 키를 저장하지 않고, 키 자체를 응답으로 돌려주지 않는다.
- FastAPI TestClient에서 provider 전달, 키 저장, 잘못된 URL·자막 없음 처리를 가짜 외부 호출로 검증했다. 임시 서버의 브라우저 UI에서 링크 2개 감지, GPT 선택 시 키 등록 안내를 확인했다. 실제 유튜브 자막 수집과 실제 GPT 호출은 사용자가 제공한 링크/API 키가 없어 미검증이다.
- 기존 8765 서버에는 `awaiting_review` 잡이 있어 작업 중단을 피하려고 재시작하지 않았다. 새 코드는 서버를 다시 시작한 뒤 8765 화면에 반영된다.
