# 햄토리치 (hamtorich_01) — 브랜드 기본 캐릭터

- 최상위 기준: `master/design_sheet.png` (마스터 레퍼런스). 얼굴형·귀·눈·털 색·네이비 상의·민트 넥타이·그림체·비율은 이 시트를 따른다.
  `master/design_sheet_original.webp` 는 받은 파일 그대로 보관한 원본이다.
- 제작용 포즈: `poses/*.png` (투명 배경 1254×1254). 감정·자세·마스터 시트와의 차이는 `bible.json` 의 `poses` 에 있다.
- 기본 캐릭터 설정: `config.yaml` 의 `carousel.character`, `topic_strategy.character`. 토리(`tory_01`)는 `--character tory_01` 로 계속 쓸 수 있다.

## 새 포즈를 추가할 때

1. `master/design_sheet.png` 를 참조 이미지로 함께 넣고 만든다. `bible.json` 의 `prompt_lock` 과 `design_rules` 를 그대로 붙인다.
2. 투명 배경 PNG, 정사각형(1254×1254 권장), 캐릭터 주변 여백은 기존 포즈와 비슷하게. 그림 안에 글자·말풍선을 넣지 않는다.
3. 파일 이름은 `감정_자세.png` (영문 소문자, 예: `surprised_round_mouth.png`), `poses/` 에 넣는다.
4. `bible.json` 의 `poses` 에 항목을 추가한다:
   `{"file": "poses/…png", "emotion": "surprised", "pose": "standing", "also_emotions": [], "also_poses": [], "description": "…", "differences": [], "approved": false}`
   감정 값: neutral, happy, surprised, worried, thinking, confident, sad, angry. 자세 값: standing, pointing, waving, arms_crossed, thinking, cheering, shrug (+ 자유 값).
5. `python -m app.factory characters show hamtorich_01` 로 저장 상태를 확인한다.
6. 마스터 시트와 대조한 뒤 `characters approve --item hamtorich_01/poses/…png`로 승인한다. 미승인 포즈는 기본 포즈와 reference_images 경로로도 렌더에 쓰지 않는다.

## 아직 없는 그림 (마스터 시트에는 있음)

- 놀람: 동그란 눈·O자 입·느낌표 → 현재는 `happy_cheering` 로 대신함
- 행복(눈웃음 ^^ + 하트) → 현재는 눈 뜬 웃음 포즈로 대신함
- 생각(물음표·다문 입) → 현재 `thinking_chin` 은 미소 표정
- 슬픔·화남 → 현재 `worried_hands` 로 대신함
- 시트 고유 소품(갈색 가방+집 열쇠고리, '돈도 아는 햄토리치' 책, 도토리 지갑, 집 열쇠)을 든 포즈
