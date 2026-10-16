# 품질 기준 샘플

`output/` 은 Git 에서 제외되므로, 품질 기준으로 채택한 최종 결과만 여기에 둔다 (중간 결과물 제외).

| 폴더/파일 | 내용 |
|---|---|
| `2026-10-09_hamtorich_free_instatoon_B/` | **채택된 시각 품질 기준 (B)** — 무료 렌더링 인스타툰 8장, contact_sheet, manifest, caption. 사람이 쓴 스토리. 수치는 국가데이터처 「2026년 9월 소비자물가동향」 원문, 대사는 창작 |
| `2026-10-09_compare_A_vs_B.png` | A(개선 전 기본 렌더링) vs B(스토리형) 비교 |
| `2026-10-09_hamtorich_auto_C/` | **자동 생성 C** — `toon --writer rules` (주제 입력 → 규칙 작가 → 연출 → PNG, AI 0회). story.json 에 초안·검증 결과·사용 fact id |
| `2026-10-09_compare_B_vs_C.png` | B(사람 작성) vs C(자동) 비교 |

C 다시 만들기: `.venv\Scripts\python.exe -m app.factory toon --topic "9월 소비자물가와 내 장바구니" --facts-from-topic topic_41047f0e217fafad`
B 다시 만들기: `.venv\Scripts\python.exe -m scripts.sample_free_instatoon B` (유료 API·AI 호출 0회).
전체 output 백업: `.venv\Scripts\python.exe -m scripts.backup_outputs` (Git 밖에 ZIP 으로).
