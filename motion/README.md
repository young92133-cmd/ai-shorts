# motion — 영상 연출 도구 (2026-11-18 설치)

쇼츠 엔진(`app/pipeline`, ffmpeg)과 별개인 자바스크립트 연출 도구 모음이다. 아직 팬 클립 렌더에 연결하지 않았다.

- 설치: Node.js LTS 설치 후 이 폴더에서 `npm install` (esbuild 설치 스크립트 허용: `npm install-scripts approve esbuild`)
- 확인: `npx remotion render src/index.ts Hello out/hello.mp4` (2초 테스트, 첫 실행 때 Remotion 전용 Chrome 을 내려받음)
- 패키지: Remotion(+lottie·three) · anime.js · motion · three · three-gpu-pathtracer · jolt-physics · postprocessing · three.quarks · tweakpane
- Remotion 라이선스: 개인·직원 3명 이하 회사 무료, 그 이상은 유료(https://remotion.dev/license)
- Remotion Skills(Claude Code): 저장소 루트에서 `npx skills experimental_install` (목록 `skills-lock.json`, 설치 위치 `.claude/skills/` 는 Git 제외)
- Blender MCP: Blender 설치 → https://github.com/ahujasid/blender-mcp 의 `addon.py` 를 Blender 애드온으로 설치·활성
  → `claude mcp add blender --scope local -- uvx blender-mcp`. 사용할 때 Blender 사이드바(N) BlenderMCP 에서 서버 켜기. `blender/` 폴더는 Git 제외
- Manim 은 Python 이라 프로젝트 `.venv` 에 설치(`pip install manim`)

## 제작 단계 지도 도구 (2026-11-18 추가 설치)

| 단계 | 도구 | 설치 위치 · 메모 |
|---|---|---|
| 레퍼런스 분석 | PySceneDetect 0.7.3 | `.venv` (`scenedetect` 명령) |
| 레퍼런스 분석 | watch-video (khou) | `.claude/skills/watch-video` — 완전 로컬(자막 또는 whisper.cpp, 프레임 추출) |
| 레퍼런스 분석 | claude-video `/watch` (bradautomates) | `.claude/skills/watch` — `~/.config/watch/.env` 를 local·backend none 으로 설정(Gemini 업로드·유료 전사 꺼짐) |
| 대본 | humanize-korean (epoko77-ai/im-not-ai) | `.claude/skills/humanize*` |
| 음성 | Supertonic 1.3.1 | `.venv`. 첫 사용 때 Hugging Face 에서 모델을 받는다. 모델 라이선스 OpenRAIL-M |
| 편집 | auto-editor 29.3.1 | `.venv` (말 없는 구간 자르기) |
| 편집 | video-use (browser-use) | `.claude/skills/video-use` (`uv sync` 완료). ElevenLabs 키가 필요한 기능은 사용자 승인 전 쓰지 않음 |
| 그래픽 | HyperFrames (HeyGen) | `.claude/skills/hyperframes*` 외 9개, 런타임 `npx hyperframes` 0.9.66 |
| 그래픽 | awesome-opus-videos | `motion/references/awesome-opus-videos` (yihui-dev, 참고 자료, Git 제외) |
| 전체 | OpenMontage | 저장소 밖 `../OpenMontage` (AGPL-3.0, 자체 `.venv`·Piper TTS·remotion-composer). `.env` 없음 = 유료 키 없음 |
| 올리기 | Aside | 설치 안 함 — 오픈소스가 아닌 상용 AI 브라우저(계정 필요). 필요하면 사용자가 공식 사이트에서 직접 설치 |

스킬 목록·버전: 저장소 루트 `skills-lock.json` (`npx skills experimental_install` 로 복원, watch-video 는 이름 충돌로 수동 설치).
