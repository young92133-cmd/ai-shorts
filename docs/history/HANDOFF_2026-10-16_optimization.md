# 경량화 1~4단계 기록 (2026-10-16, HANDOFF 에서 옮김)

### 완료 (경량화 1~4단계)

1. 문서 단일화: 공통 규칙은 `AGENTS.md` 하나. `CLAUDE.md` 는 `@AGENTS.md` + Claude 전용 몇 줄.
   AGENTS 에서 뺀 내부 구현 메모는 `docs/AGENT_REFERENCE.md` 로 그대로 옮김.
2. HANDOFF 경량화: 옛 HANDOFF·IMPLEMENTATION_PLAN 은 `git mv` 로 `docs/history/` 에 보존(삭제 없음), 이 파일을 새로 씀.
3. 공통 모듈: 글꼴 로더 4벌 → `app/pipeline/fonts.py` 의 `font(size, bold=True)` (캐시).
   `cards._font`·`images/base._font`·`quote._font` 는 얇은 별칭으로 남김(`scripts/verify_visuals.py` 가 `cards._font` 사용).
   `carousel/render.font` 는 같은 이름으로 다시 가져와 `nametag.py` 등 기존 import 그대로 동작.
   `research._strip_tags` 는 `article._strip_tags` 를 가져다 씀.
4. 참조 0 함수 8개 삭제(재확인 후): `render.render_clips`, `assets.resolve_visuals`·`save_upload`, `clips.retime_words`,
   `article.credit_line`, `run._find_bgm`, `carousel/effects.screentone`, `carousel/asset_gen.report_json`.
   이로써 안 쓰게 된 import 3개(`SceneVisual`, `Word`, `json`)도 정리.

