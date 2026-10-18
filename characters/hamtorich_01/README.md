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

제작 결과의 `manifest.json` → `pose_gaps`(스튜디오 화면 위쪽 안내)에 "맞는 표정 그림이 없어 비슷한 그림으로 그린 컷"이 자동으로 나온다.
2026-10-18 점검(월급날 인스타툰 8장) 기준 우선순위:

| 순위 | 파일 이름(받은편지함) | 표정·자세 | 지금 대신 쓰는 그림 | 쓰이는 장면 |
|---|---|---|---|---|
| 1 | `햄토리치_슬픔_서있음.png` | 처진 귀·눈물 한 방울·입꼬리 내려감 | worried_hands | 잔액이 줄었을 때, 퇴근길 |
| 2 | `햄토리치_놀람_서있음.png` | 동그란 눈·O자 입·양손 볼 | worried_hands / cheering | 자동이체·청구서 발견 |
| 3 | `햄토리치_생각_턱.png` | 다문 입·한쪽 눈썹 올림(웃지 않음) | thinking_chin(미소) | 계산·고민 컷 |
| 4 | `햄토리치_슬픔_앉음.png` | 지친 얼굴: 반쯤 감긴 눈·어깨 처짐, 앉아 있음 | worried_hands | 밤·야근·월말 |
| 5 | `햄토리치_화남_팔짱.png` | 찌푸린 눈썹·볼 부풀림·팔짱 | worried_hands | 물가·수수료 |
| 6 | `햄토리치_기본_서있음.png` | 무표정(작은 입), 차렷 | happy_front(웃음) | 설명·나레이션 |
| 7 | `햄토리치_행복_만세.png` | 눈웃음(^^)+하트, 만세 | happy_cheering(눈 뜬 웃음) | 입금·보너스 |
| 8 | `햄토리치_놀람_휴대폰.png` 등 소품 포즈 | 휴대폰 보며 놀람, 지갑 열기, 가방 들고 걷기, 침대에 누움 | happy_phone 등 | 출근길·밤 |

만드는 방법(무료, 사람이 그림 → 앱이 등록):
1. ChatGPT 등에 `master/design_sheet.png` 와 기존 포즈 2~3장을 함께 올리고, `bible.json` 의 `prompt_lock`·`design_rules` 를 붙인다.
   "같은 캐릭터·같은 그림체·같은 네이비 정장과 민트 넥타이, 투명(또는 흰) 배경, 정사각형, 글자·말풍선·효과선 없음, 전신" 을 요청한다.
   감정 기호(눈물·땀·집중선)는 앱이 따로 그리므로 그림에는 넣지 않는 편이 좋다.
2. 위 이름으로 `assets/inbox/` 에 넣으면 다음 제작 때(또는 `characters import`) 등록된다. 등록 직후는 미승인이다.
3. 마스터 시트와 얼굴형·귀·털색·의상을 대조한 뒤 `characters approve --item hamtorich_01/poses/…png` 로 승인해야 렌더에 쓰인다.
4. 승인 뒤 스튜디오에서 해당 카드의 '저장하고 다시 그리기'만 누르면 새 표정으로 다시 그려진다(문구·AI 호출 다시 안 함).
