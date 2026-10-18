# AI 콘텐츠팩토리 — Claude Code 전용 메모

공통 규칙은 AGENTS.md 하나다(Codex 와 같이 씀). 아래 줄로 그대로 가져온다. **규칙을 고칠 때는 AGENTS.md 만 고친다.**

@AGENTS.md

## Claude Code 에서만 해당하는 것

- 시작 순서는 AGENTS.md '작업 시작 · 종료'를 따른다: `git status` → `HANDOFF.md` 맨 위 '현재 상태'. 사용자 메모리(`~/.claude/projects/.../memory`)는 배경 참고일 뿐, 규칙은 AGENTS.md 가 우선이다.
- Claude 구독 로그인 확인: `claude auth status` (authMethod `claude.ai` 이면 구독). 풀렸으면 사용자에게 `claude-login.cmd` 실행만 안내한다.
  Factory 의 `--llm claude`·`toon --writer claude` 는 SDK 환경에서 `ANTHROPIC_API_KEY`·토큰을 비워 구독 경로로만 호출한다.
- 실제 제작·테스트 명령은 오래 걸리므로 넉넉한 제한 시간(10분)을 주거나 백그라운드로 돌리고, 결과는 요약만 보고한다.
- 파일은 필요한 부분만 읽고(Read offset/limit, Grep), 고칠 때는 전체를 다시 쓰지 말고 바꿀 부분만 수정한다.
- 작업을 끝내거나 사용자가 Codex 로 넘기기 전에 `HANDOFF.md` '현재 상태'를 갱신한다.
