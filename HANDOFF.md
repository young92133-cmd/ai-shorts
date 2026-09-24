# HANDOFF — 개발 인수인계 문서

> 이 문서만 읽고 바로 작업을 이어갈 수 있도록 쓴 **개발자/AI용** 문서입니다.
> 사용자용 사용법은 [`README.md`](README.md)에 있습니다. 중복되는 내용은 그쪽을 참고하세요.
>
> **최종 갱신: 2026-09-24 (오후)** · §12의 9월 22일 숫자와 검증 결과는 당시 기록이다. 현재 상태는 아래 체크포인트 요약을 우선한다.

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

### API 엔드포인트 (현재 `app/main.py`의 사용자 정의 라우트 30개)

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
