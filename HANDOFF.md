# HANDOFF — 현재 상태 (2026-10-27, Codex)

> 공통 규칙 AGENTS.md. 이전 인계는 docs/history/HANDOFF_2026-10-21_styles_before_resume_2026-10-27.md에 원문 보존.

## 작업 위치 / 분리
- 현재: ../shorts-ai-styles, feature/character-styles. HEAD 96bc82a (미커밋 시제품).
- V1.0: ../shorts-ai, feature/agent-content-factory, HEAD/origin 96bc82a. 운영 문서 미커밋 5파일은 그대로 보존.
- ../shorts-ai-benchmark-v2는 detached dce81da, 다른 컨셉과 미커밋 작업이 있어 변경하지 않음. 브랜치를 합치지 않는다.
- 재개 전 변경 사본: ../backups/resume-styles-20261027-223923/ (세 작업 폴더 변경 및 해시 보존).

## 완료 / 이어서 한 일
- 이전 완료: 기본 그림체 5종, 민지·도트, 참고 이미지 색/선 추출, Factory/스튜디오 선택·set_look·undo 연결. 새로 만들지 않음.
- 민지 + clean_webtoon 한 조합에 집중: face=editorial 선택형 무료 프로필, 옆가르마 곡선·작은 타원 얼굴·코·봉제선·고정 민트 머리핀.
- 얼굴/머리/의상 기준 좌표와 색 고정. 감정은 눈·눈썹·입, 자세는 기존 팔 그리기 재사용.
- 토리·도트 8감정×3자세 = 48조합, 변경 전/후 픽셀 동일. 햄토리치 원본·기본 그림체·V1.0 경로는 변경 안 함.
- QA: output/character_quality_20261027_ehrsa9kv/ (before_after, identity_sheet, overview, deck/insta_toon 8장).
  기존 관리비 원고/계획 재사용, 이미지·LLM·외부 호출 0, 1080x1350·fallback0. 원고의 외부 사실 재검증은 아님.
- 기존 output/style_samples_2026-10-21/ 비교판·A~H 8세트(122파일)는 해시 검사로 보존.
- 이번 변경: app/carousel/mascot.py, characters/minji_01/bible.json, tests/test_art_styles.py,
  캐릭터 README·그림체 문서·현재 HANDOFF/이전 인계 보존본. 그 외 시제품 변경은 기존 작업 유지.

## 검증
- 재개 기준 V1.0 전체406 / 그림체 시제품 전체414 통과. 실패/오류/skip0, 외부 호출 시도0, 원본 변경0.
- 새 회귀4개: 8감정의 고정 머리/의상, 자세/뒤집기, guide/panel 동일 외형, 준비된8장 AI미호출.
- 수정 후 전체418개 통과(추가4개), 실패/오류/skip0, 외부 호출 시도0, 테스트 중 원본 변경0. 로그/JSON은 위 백업의 styles-final/.
- 기본 그림체의 기존 툰/카드뉴스16장은 PNG 바이트 동일. 검증 output/character_quality_20261027_ucnk_qyj/default_compatibility.json.

## 다음 작업 / 한계
- 원본/샘플 보존 검사와 결과 보고 → 새8장 검수본에서 외형/장면 품질 검토 → 같은 주인공으로 후속 품질 개선.
- 현재는 무료 벡터형 프로필의 개선본이다. 정교한 손그림/측면·각도별 자산·복잡한 손/배경 조명은 아직 미완성.
- 햄토리치를 유지하되 주력 강제하지 않음. 사람형 민지와 clean_webtoon을 먼저 다듬고 다른 그림체 확장은 보류.
- 추가 품질 작업도 같은 주인공/원고/8장으로 비교하고 특정 작가를 복제하지 않는다. 유료 생성은 별도 승인 전 금지.
- 경량화1~4단계 완료. 캐시/로그·옛 데모·사용자 영상/결과 정리는 승인 없이 삭제하지 않음. 기존 .venv도 보존.

## 안전
- commit/push 별도 승인 대기. .env/키/output/캐시/백업은 커밋하지 않음.
- 다른 세션의 변경·운영 문서를 덮어쓰지 않음. 같은 파일이 움직이면 편집 중단.
