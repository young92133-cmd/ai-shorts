# HANDOFF — 현재 상태 (한 장)

> 규칙: AGENTS.md '작업 시작 · 종료'. 이 파일은 80줄 이하로 유지하고, 끝난 기록은 `docs/history/` 로 옮긴다.
> 지난 기록: `docs/history/HANDOFF_2026-10-21_studio_v1.md`(카드 스튜디오 V1.0), `docs/history/HANDOFF_2026-09_10.md`.

## 현재 상태 (2026-11-06, Claude → Codex) — 유튜브 AI 쇼츠 전용 + 경쟁 채널 벤치마킹

> **Codex 는 먼저 `docs/CODEX_HANDOFF_2026-11-06.md` 를 읽는다.** 카드뉴스·인스타툰·캐릭터 기능은 제거됐고 다시 만들지 않는다.
> 다음 작업: HyperFrames 1단계(Node 22 설치는 사용자 승인 후) → 장면 소스 적합성 개선.

- 작업 폴더 `../shorts-ai-shorts` (git worktree), 브랜치 `feature/shorts-only` ← `feature/agent-content-factory` 96bc82a.
  2026-11-06 사용자 승인으로 commit·일반 push (이후 commit·push 는 다시 승인 필요).
- 백업: `../backups/shorts-only-before-20261105/` (모든 브랜치 bundle, 세 작업 폴더의 미커밋 patch·tar, 소스 스냅샷, SHA256SUMS, `RESTORE.md`).
- 손대지 않은 것: `../shorts-ai`(운영 문서 미커밋), `../shorts-ai-styles`(10-27 Codex 미커밋), `../shorts-ai-benchmark-v2`(Codex 소유),
  output·reference.mp4·.venv·samples/·characters/(사용자 결정: 그대로 둠).

## 2026-11-05 밤 추가 (미커밋) — 경쟁 채널 벤치마킹 · 품질 수정
- 새 파일: `app/pipeline/channels.py`(수집·지표·AI 패턴·비교·복사 감시), `app/factory/channels.py`(`channel analyze/list/show/topics/make/auto`, 캐시
  `output/_factory/channels/`), `tests/test_channels.py`(14). 웹 '경쟁 채널 분석' 화면(index.html·app.js·main.py `/api/channels*`), 웹 잡에 `benchmark` 전달(jobs.py).
  batch 후보가 패턴 옵션(instructions·benchmark·seconds)을 함께 넘김.
- 품질: `script_split.short_phrase` 꾸밈말·연결어미에서 안 자름, `cards.fit_text` 단어 중간 줄바꿈 전 글자 축소, 훅 카드 물음표 겹침 제거. edge-tts 공용 .venv 7.3.1 로 올림.
- 실제 확인: Claude 구독 재로그인(pro). 짤잉 @zzal_ing 목록 150·상세 45·자막 6, 패턴 분석 Claude 2회(수정 전·후). 검토→수정→승인→MP4 `output/20261105_231559_d127`(29.7초).
- 2주제 순차 제작(C) 성공: `batch_20261105_232321_ab58` 2/2 완성(25.6초·25.5초, 1080x1920).
- 벤치마킹 기반 쇼츠(D, 2026-11-06): 1차(`20261106_220410_91bf`)는 추천 제목 '작년 신인상 후보…'가 **야구로 조사**됨(분야 누락).
  → `TopicIdea.search_query`(분야·대상 포함 조사 문장) 추가, 후보 `topic`=조사 문장·`title`=제목 후보, batch --select 도 `channel_benchmark.json` 기록.
  2차 `output/20261106_221220_cad4/final.mp4` 성공: K팝 신인 걸그룹 근황, curiosity_update_story(패턴 강제), 22.2초·1080x1920·30fps·AAC, 7장면, 자막 15줄,
  원본 자막 겹침 0.0, AI 5회(구독). 공개 자료 0건 → 전부 자체 카드. 출처가 블로그 2곳뿐 — 수상·차트 사실은 게시 전 확인 필요.
- 전체 테스트 2026-11-06: **343개 통과** (예전 '344' 는 추정치였음).
- 백업: `../backups/shorts-only-bench-20261106/` (이 폴더 미커밋 변경 patch·untracked tar, SHA256 OK, apply --check OK, RESTORE.md).
- HyperFrames 렌더러: 0단계 보고만 함. 확정 구조 = timeline.json 재사용 · 기본 FFmpeg 유지 · `renderer: hyperframes` 선택형 ·
  `presets/render/*.json` · Noto Sans KR · Node 22+ · 공식 CLI·플러그인. **Node 설치·플러그인 설치·브라우저 다운로드는 아직 하지 않음 (승인 대기).**

## 구조

```
채팅(Claude Code/Codex) → app/factory (make·resume·batch·inspect·edit-scene·set-visual·rerender·export·trends·benchmark·topics)
                        → app/pipeline (조사·대본·장면·TTS·화면·자막·렌더)   ← Web UI app/main.py · static/app.js · templates/index.html
                        → app/topics (수집·검증·추천·승인·캘린더 → brief.shorts_brief → core.make)
```

## 완료

- 삭제(git rm): `app/carousel/`(22), `app/studio/`(4), `app/factory/{toon,intent}.py`, `tests/test_{carousel,studio}.py`,
  `scripts/sample_free_instatoon.py`, `카드뉴스 스튜디오 실행.cmd`, `assets/inbox/README.md`, 미사용 `pipeline/assets.plan_sourced`.
- 정리: `core.py`(캐러셀 분기·output_format 제거, 옛 카드 프로젝트는 `LEGACY_FORMATS` 로 알아보고 resume/pack 거절),
  `__main__.py`(toon·characters·--format 출력값·--template/--character/--pages/--request/--research-file 제거, `--tone`=`--format` 톤값),
  `main.py`·`launcher.py`·`index.html`(스튜디오 라우터·링크·인자 제거), `config.yaml`(carousel 절·topic 캐릭터 제거).
- 주제 전략(사용자 결정 "쇼츠용으로 바꿔 유지"): `topics/story.py` → `brief.py`(검증된 사실·출처·방향 → make 지시문),
  `engine.create(dry_run, review, seconds, preset)` → `core.make(topic, instructions)`. plan·캐릭터 필드 제거,
  예전 저장 파일의 옛 필드는 `schema.LEGACY_FIELDS` 로 읽을 때 버림. 자연어 판별은 `factory/topics.detect_topic_request`.
- 문서: AGENTS·CLAUDE·README·TOPIC_STRATEGY·AGENT_REFERENCE 쇼츠 전용으로. 옛 카드 문서는 `docs/history/carousel_2026-10/`.
  `.ignore` 추가(docs/history·samples·characters·cat-box 데모를 검색에서 제외).
- `requirements.txt`: `edge-tts>=7.3.1` (7.2.8 은 Microsoft 서버 403).

## 테스트·실제 검증

- 전체 `unittest discover`: **327개 통과** (2026-11-05). 모든 app 모듈 import OK. 웹 화면(8766) 콘솔 오류 0, `/studio` 404.
- 실제 쇼츠 1편 `output/20261105_223157_b176/final.mp4` (이 worktree): 완성 대본 → Edge TTS → 카드 5장면 → ASS 자막 → H.264 1080×1920 30fps AAC 27.0초.
  첫 실행은 TTS 403 으로 `blueprint_complete` 에서 실패 → edge-tts 7.3.1 로 `resume` 성공(실패 후 이어 만들기 실제 확인). 비용 0원.
- 주제 → MP4(Claude 대본) 실제 제작은 **미검증**: Claude 구독 OAuth 만료(`claude auth status` 는 loggedIn 으로 보임).
  `output/20261105_223111_2c5f` 는 대본 전 실패 기록.

## 남은 작업 / 다음 작업

1. 사용자: `claude-login.cmd` 로 다시 로그인, `..\shorts-ai\.venv` 의 edge-tts 를 7.3.1 로 올리기(`pip install -U edge-tts`).
2. 그 뒤 `make --topic "…" --review` → `resume` 로 주제→MP4 실제 1편, `batch --topic … --count 2 --review` 순차 확인.
3. 사용자 승인 후 commit·push (이 worktree 만. 다른 작업 폴더의 미커밋 변경은 섞지 않는다).
4. 개선 후보: LLM 없는 완성 대본 분할은 화면 문구가 문장 중간에서 잘림("셋째, 내복이나 얇은") · 공개 자료 0건이면 카드만 나옴.
5. [승인 대기] 옛 MVP 데모·verify 스크립트 정리, Git 밖 대용량(reference.mp4 1GB, output) 정리 — 사용자 데이터.

## 주의

- 유료 API·commit·push·위험한 삭제·대규모 구조 변경은 사용자 승인 후. `.env`·키·output 은 커밋하지 않는다.
- 카드뉴스·인스타툰을 되살리려면 `../backups/shorts-only-before-20261105/RESTORE.md`.
