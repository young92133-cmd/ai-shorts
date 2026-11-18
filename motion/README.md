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
