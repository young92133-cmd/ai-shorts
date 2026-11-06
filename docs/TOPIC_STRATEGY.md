# Topic Strategy Engine V1

주제 발굴부터 사람의 제작 승인까지 연결한다. `make`, `trends`, `batch` 의 기존 기본값은 그대로다. 제작은 쇼츠 `make` 로만 연결한다(카드뉴스·인스타툰은 2026-11-05 제거).
게시 API는 없다. `published`는 사용자가 이미 게시한 결과를 이력에 기록하는 명령이다.

## 운영 순서

프로젝트에서 기존 가상환경 Python으로 실행한다.

현재 Codex에서는 기존 `.venv` 실행 파일이 삭제된 Python 경로를 가리킨다. 원본은 보존하고 저장소 밖
`../.codex-envs/ai-shorts-py312/`에 Python 3.12.14를 구성해 기존 설치 패키지를 `.pth`로 재사용한다.
`./scripts/factory.ps1 topics --help`로 안전하게 실행을 확인할 수 있다. 래퍼는 정상 `.venv`를 우선하고,
복구 환경이 없으면 제공된 Python과 `site.addsitedir`를 사용한다(PYTHONPATH만으로는 pywin32 연결이 누락될 수 있다).
로컬 FFmpeg/FFprobe PATH는 래퍼 실행 중에만 추가한다. 기존 `.venv/Lib/site-packages`를 삭제하면 재사용 환경도 깨진다.
아래 `python -m app.factory`를 `./scripts/factory.ps1`로 바꿔 같은 명령을 실행할 수 있다.

```powershell
python -m app.factory topics collect --category all
python -m app.factory topics collect --topic "전세와 월세 중 어떤 선택이 더 유리할까?"
python -m app.factory topics collect --url "공식 자료 URL" --rss "사용자 지정 RSS URL"
python -m app.factory topics collect --input research.json
python -m app.factory topics collect --candidates trends_ID
python -m app.factory topics rank --limit 10
python -m app.factory topics recommend --limit 3
python -m app.factory topics recommend --b2b
python -m app.factory topics inspect --id TOPIC_ID
python -m app.factory topics edit --id TOPIC_ID --title "수정 제목" --direction "신혼부부의 주거비 비교"
python -m app.factory topics edit --id TOPIC_ID --facts facts.json
python -m app.factory topics verify --id TOPIC_ID
python -m app.factory topics approve --id TOPIC_ID
python -m app.factory topics create --id TOPIC_ID --dry-run
python -m app.factory topics create --id TOPIC_ID --review --seconds 45
python -m app.factory topics calendar --weeks 1
python -m app.factory topics calendar --weeks 4 --count 3
python -m app.factory topics schedule --id TOPIC_ID --date 2026-10-20
python -m app.factory topics hold --id TOPIC_ID
python -m app.factory topics release --id TOPIC_ID
python -m app.factory topics exclude --id TOPIC_ID
python -m app.factory topics review --id TOPIC_ID
python -m app.factory topics published --id TOPIC_ID --url "실제 게시 URL"
```

`collect`는 검색/공개 본문 수집만 하고 LLM을 호출하지 않는다. 등록한 RSS가 있으면 공식 사이트 검색을 대신해 먼저 읽는다.
공식 RSS/API 엔드포인트를 추측해서 넣지 않는다. 기본은 기관 도메인 검색(BOK·국토부·금융위·금감원·통계청/KOSIS·부동산원)
후 허용된 공개 본문을 읽는다. 로그인/봇 차단/robots 제한을 우회하지 않으며 장애는 출처별 errors로 남긴다.
RSS는 후보 탐색용이며 RSS 요약만으로 사실을 verified로 만들지 않는다. 검색·본문 추출은 기존 research/article을 재사용한다.
이미지를 수집하지 않는다. SourceRegistry에는 연구용 reference_only 출처로 등록한다.

점수 가중치는 관심 30, 스토리 25, 실용 25, 사업 20. 항목 0~5, 총점 0~100; 기본 80 이상 우선·65 이상 검토·미만 보류다.
기본 규칙 점수는 내부 추정이며 조회수·검색량 관측값이 아니다. `rank --ai`를 명시하면 기존 LLM 구조화 출력으로
점수와 의미 중복 검토를 받는다. 유료 API는 전략 평가 경로에서 꺼져 있고 실패 시 규칙 평가로 돌아간다.
의미 중복 LLM 결과는 `semantic_duplicate_review.json`의 사람 검토용 제안이다. 검증·병합·승인을 임의로 바꾸지 않는다.

## 사실 검증의 범위

`Fact`는 claim, kind(fact/forecast/opinion), citations(evidence_id/excerpt/result), as_of, unit, applies_to,
statistic_original_url, conflict_key, value, verification, checks를 갖는다. 예시는 **가상 입력 형식**이다.

```json
[{
  "fact_id": "f1",
  "claim": "등록한 원자료의 정확한 근거 문장",
  "kind": "fact",
  "important": true,
  "citations": [{"evidence_id": "ev_등록된ID", "excerpt": "해당 주장을 포함한 원문 문장", "result": "supports"}],
  "as_of": "2026-10-08",
  "unit": "%",
  "applies_to": "원문에 명시된 적용 대상",
  "statistic_original_url": "원통계의 등록된 URL",
  "conflict_key": "동일 지표 이름",
  "value": "원문 수치"
}]
```

- 공식 도메인 문자열 하나로 검증하지 않는다. 주장과 인용문이 등록된 원문에 실제로 있어야 한다.
- 공식 1차 자료 하나면 가능하다. 공식 자료 없으면 설정한 신뢰 언론의 서로 다른 발행 주체·원문·원출처가 필요하다.
  같은 원문을 재배포한 기사는 두 출처로 세지 않는다.
- 수치는 기준일·단위, 민감 제도/상품은 적용 대상, 통계는 원자료 URL을 추가로 검사한다. 빈 값은 추측하지 않는다.
- 수치 충돌(같은 지표/날짜/단위/대상), 명시적 contradicts, 오래된 사건일·발행일·기준일은 차단한다.
- 원문 일치 기반의 보수적 V1 게이트다. 독립 보도 여부의 완전한 판정, 서로 다른 문장으로 표현된 의미 충돌,
  복잡한 법률·세금 해석은 자동 입증하지 못한다. 해당 내용은 사람이 근거·scope·conflict_key를 보완해야 한다.
- 과장 제목은 자동 승인 보류 후 `edit --title`로 고친다. verified는 법적 적합성 또는 투자 판단의 보증이 아니다.
- 기한은 최근 가져온 원문 시점에 묶인다. 캐시를 재평가하여 기한을 계속 연장할 수 없다.
  뉴스는 실제 발행일 다시 가져오며 실패하거나 원문이 바뀌면 보류·재승인한다.

## 승인 및 제작

discovered → verified → scored → shortlisted → approved → planned → generated → reviewed → published.
별도로 excluded/held가 있다. 점수가 높아도 미검증·충돌·만료·중복·사용 권한 문제는 승인되지 않는다.
제목/방향/사실 수정은 승인을 무효화한다. 원자료와 승인 대상의 fingerprint로 변경을 추적한다.
`release` 후 다시 rank/verify/approve하면 보류된 주제를 재검토할 수 있다.
후속편: `approve --followup`, 또는 `edit --followup/--series-parent/--update-of`로 관계를 남긴다.

## 제작 (topics create → 쇼츠 make)

승인된 주제만 제작한다. `app/topics/brief.shorts_brief` 가 검증된 사실(전망·의견 표시, 발표일·적용 대상, 출처 자료명)과
방향·시청자를 지시문으로 묶고, `core.make(topic=제목, instructions=지시문, review=…)` 로 기존 쇼츠 엔진에 넘긴다(LLM 추가 호출 없음).
지시문은 `briefs/<topic_id>.json` 과 프로젝트 폴더 `topic_strategy.json` 에 남는다. `--dry-run` 은 지시문만 내고 렌더·API 호출이 없다.
`--review` 면 대본까지 만들고 멈추며(`script_review`), 이후 `resume <project_id>` 로 완성한다. 실패하면 다시 `create` 하면 된다.

## 캘린더와 기록

주 3편, 기본 다음 월요일(월/수/금). 주당 1~7편·1~4주 설정 가능. 요일별 분야 고정 없음.
최근 20개 발행 슬롯의 목표 9:7:4를 따르되 적격 주제만 사용한다. 부족 분야를 우선하고 예약 중인 다른 캘린더 주제는 중복 배치하지 않는다.
채울 수 없으면 unfilled_dates를 반환한다. 수집량이 적다고 낮은 점수·미검증 주제를 끼워 넣지 않는다.
뉴스 예약은 발행일 재검증 대상으로 표시한다. B2B는 교육용 업종·사례·납품물·리스크를 제안하고, 주별 적격 샘플이 없으면 null을 남긴다.

저장: `output/_factory/topics/`의 topics, evidence, evidence_history, audit, briefs, calendars, selections,
publication_history.json, duplicate_clusters.json, evaluations. JSON 교체는 원자적이며 원문 갱신 전 스냅샷을 보존한다.
단일 사용자 로컬 CLI용이다. 동시 프로세스에서 같은 레코드를 수정하는 다중 사용자 DB 기능은 제공하지 않는다.

## 자연어

```powershell
python -m app.factory topics request "오늘 쇼츠 만들 주제 5개 추천해줘"
python -m app.factory topics request "이번 주 부동산 주제만 보여줘"
python -m app.factory topics request "이번 주 콘텐츠 캘린더 만들어줘"
python -m app.factory topics request "B2B 영업에 쓰기 좋은 주제 추천해줘"
python -m app.factory topics request "1번 주제로 쇼츠 만들어줘" --selection selection_ID
```

의도 판별은 `app/factory/topics.detect_topic_request`. "대본만"·"검토"가 있으면 `--review` 로 멈춘다. 후보 번호는 사용자가 본 selection_ID에 반드시 연결한다.
번호 제작 요청은 그 선택의 사용자 승인으로 처리하지만 검증 게이트는 통과해야 한다.
후보가 비어 있으면 추천 요청은 공개 수집·규칙 평가를 먼저 한다. 이미 저장된 후보가 있으면 추가 LLM 호출 없이 목록을 사용한다.

## 오프라인 예시

`python -m scripts.demo_topic_strategy` → 별도 output 폴더의 REPORT.md, recommendations.json,
calendar_1week.json, calendar_4weeks.json, engine_delivery.json(make 에 넘길 지시문).
공식 자료를 가장하지 않도록 `.example` 도메인의 **가상 자료**와 격리된 데모 설정을 사용한다.
실제 운영의 공식 도메인 설정에서는 이 가상 자료가 verified가 되지 않는다. Claude/API/렌더 호출 0회.
모든 배포용 데모 JSON의 notice는 가상 근거 안내로 고정한다. 재실행은 새 하위 폴더를 써 이전 데모를 보존한다.

## 구현과 검증 상태

- 2026-11-05: 카드 기획(plan·8장 스토리·캐릭터)을 빼고 create 를 쇼츠 make 로 직접 연결. `tests/test_topics.py` 58개.
- 2026-10-08 Codex: V1 수집·주장/근거 검증·100점 평가·사건 중복/발행 이력·1~4주 캘린더·CLI 구현.
- 의미 중복은 기본 규칙 병합과 `rank --ai`의 사람 검토용 LLM 제안이다. 의미 이해에 따른 자동 검증·자동 병합 완료로 해석하지 않는다.
- 실제 Claude 평가·의미 중복 AI·Topic→쇼츠 실제 제작은 아직 실영상으로 검증하지 않았다 (mock 테스트만).
- 실 뉴스 수집/캐러셀 선행 검증 기록과 알려진 한계는 `history/carousel_2026-10/OPS_VALIDATION_2026-10-08.md`.
  공식 원문 자동 연결·사건일·상시 주제 분류·JS 본문·제목/CTA 및 강조 숫자 맥락은 후속 개선 대상이다.
