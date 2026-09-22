"""LLM 호출 헬퍼 (구조화 출력). provider 는 config.yaml 의 llm.provider 로 선택.

- claude    : Claude Code 로그인(구독)으로 호출. API 키 불필요. (Claude Agent SDK)
- openai    : OpenAI GPT. OPENAI_API_KEY 필요.
- anthropic : Anthropic API 키로 직접 호출. ANTHROPIC_API_KEY 필요.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from ..config import env

T = TypeVar("T", bound=BaseModel)


# ---------- 공통 ----------

def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """OpenAI strict 모드용: 모든 object 에 additionalProperties=false, 모든 property 를 required 로."""
    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        return node
    return walk(json.loads(json.dumps(schema)))


def _extract_json(text: str) -> Any:
    """응답 텍스트에서 JSON 객체를 찾아 파싱 (코드펜스/설명이 섞여도 처리)."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("응답에서 JSON 을 찾지 못했습니다: " + text[:200])


def _validate(schema: type[T], data: Any) -> T:
    try:
        return schema.model_validate(data)
    except ValidationError as e:
        raise RuntimeError(f"LLM 응답이 형식에 맞지 않습니다: {e.errors()[:3]}") from e


# ---------- Claude (구독 로그인) ----------

def find_claude_cli() -> str | None:
    """PATH → 데스크톱 앱 번들 → ~/.claude/local 순으로 claude.exe 를 찾는다."""
    if p := shutil.which("claude"):
        if p.lower().endswith(".exe") or os.name != "nt":
            return p
    roots = [os.environ.get("APPDATA"), os.environ.get("USERPROFILE"), str(Path.home()), os.environ.get("LOCALAPPDATA")]
    cands: list[Path] = []
    for r in roots:
        if not r:
            continue
        for sub in ("Claude/claude-code", "AppData/Roaming/Claude/claude-code", "Claude/claude-code"):
            base = Path(r) / sub
            if base.exists():
                cands += list(base.glob("*/claude.exe"))
    cands = [c for c in cands if c.exists()]
    if cands:
        return str(max(cands, key=lambda x: x.stat().st_mtime))
    for name in ("claude.exe", "claude"):
        p2 = Path.home() / ".claude" / "local" / name
        if p2.exists():
            return str(p2)
    return None


async def _ask_claude_code(model: str, system: str, user: str, schema: type[T], effort: str) -> T:
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
    except ImportError as e:
        raise RuntimeError("`pip install claude-agent-sdk` 가 필요합니다.") from e

    cli = find_claude_cli()
    if not cli:
        raise RuntimeError("claude.exe 를 찾을 수 없습니다. PowerShell 에서 `irm https://claude.ai/install.ps1 | iex` 로 설치 후 `claude login` 하세요.")

    # 이 프로그램이 Claude Code 세션 안에서 실행될 때 상속되는 변수는 비워서 독립 프로세스로 돈다.
    clean_env = {k: "" for k in os.environ if k.startswith("CLAUDE_CODE_") or k == "CLAUDECODE"}
    opts = ClaudeAgentOptions(
        model=model,
        system_prompt=system,
        max_turns=1,
        allowed_tools=[],
        disallowed_tools=["Bash", "Read", "Write", "Edit", "WebSearch", "WebFetch", "Glob", "Grep", "Agent"],
        permission_mode="bypassPermissions",
        effort=effort if effort in ("low", "medium", "high", "xhigh", "max") else None,
        output_format={"type": "json_schema", "schema": schema.model_json_schema()},
        cli_path=cli,
        env=clean_env,
        setting_sources=[],
    )
    result: ResultMessage | None = None
    async for m in query(prompt=user, options=opts):
        if isinstance(m, ResultMessage):
            result = m
    if result is None:
        raise RuntimeError("Claude Code 로부터 응답을 받지 못했습니다.")
    if result.is_error or result.subtype != "success":
        raise RuntimeError(f"Claude Code 오류: {result.result or result.subtype}")
    data = result.structured_output
    if data is None:
        data = _extract_json(result.result or "")
    return _validate(schema, data)


# ---------- OpenAI ----------

async def _ask_openai(model: str, system: str, user: str, schema: type[T], effort: str) -> T:
    key = env("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY 가 .env 에 없습니다.")
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": schema.__name__, "strict": True, "schema": _strict_schema(schema.model_json_schema())}},
    }
    if model.startswith(("gpt-5", "o")):
        body["reasoning_effort"] = {"low": "low", "medium": "medium"}.get(effort, "medium")
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post("https://api.openai.com/v1/chat/completions",
                         headers={"Authorization": f"Bearer {key}"}, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"OpenAI 오류 {r.status_code}: {r.text[:300]}")
    choice = r.json()["choices"][0]
    if choice.get("finish_reason") == "content_filter" or choice["message"].get("refusal"):
        raise RuntimeError("OpenAI 가 이 요청을 거부했습니다. 주제를 바꿔 보세요.")
    return _validate(schema, _extract_json(choice["message"]["content"]))


# ---------- Anthropic API 키 ----------

async def _ask_anthropic(model: str, system: str, user: str, schema: type[T], effort: str) -> T:
    import anthropic

    if not env("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY 가 .env 에 없습니다.")
    client = anthropic.AsyncAnthropic()
    resp = await client.messages.parse(
        model=model, max_tokens=8000, system=system,
        messages=[{"role": "user", "content": user}], output_format=schema,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude 가 이 요청을 거부했습니다. 주제를 바꿔 보세요.")
    if resp.parsed_output is None:
        raise RuntimeError("Claude 응답을 파싱하지 못했습니다.")
    return resp.parsed_output


# ---------- 진입점 ----------

PROVIDERS = {"claude": _ask_claude_code, "openai": _ask_openai, "anthropic": _ask_anthropic}


async def ask_structured(llm: dict[str, Any], system: str, user: str, schema: type[T]) -> T:
    """llm = config 의 llm 섹션 ({provider, model, effort}). pydantic 모델로 검증된 응답을 돌려준다."""
    provider = llm.get("provider", "claude")
    fn = PROVIDERS.get(provider)
    if not fn:
        raise ValueError(f"알 수 없는 LLM provider: {provider}")
    return await fn(llm["model"], system, user, schema, llm.get("effort", "medium"))


if __name__ == "__main__":
    # python -m app.pipeline.llm login   → claude.exe 로 브라우저 로그인
    # python -m app.pipeline.llm status  → 로그인 상태
    # python -m app.pipeline.llm test    → 구조화 응답 스모크 테스트
    import asyncio
    import subprocess
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    cli = find_claude_cli()
    if cmd in ("login", "status"):
        if not cli:
            sys.exit("claude.exe 를 찾을 수 없습니다. `irm https://claude.ai/install.ps1 | iex` 로 설치하세요.")
        print("claude.exe:", cli)
        clean = {**os.environ, **{k: "" for k in os.environ if k.startswith("CLAUDE_CODE_") or k == "CLAUDECODE"}}
        sys.exit(subprocess.call([cli, "auth", cmd], env=clean))
    if cmd == "test":
        from ..config import load_config

        class Answer(BaseModel):
            answer: str
            confidence: float

        llm_cfg = load_config()["llm"]
        if len(sys.argv) > 2:
            llm_cfg["provider"] = sys.argv[2]
            llm_cfg["model"] = sys.argv[3] if len(sys.argv) > 3 else llm_cfg.get("openai_model", llm_cfg["model"])
        print(llm_cfg)
        print(asyncio.run(ask_structured(llm_cfg, "간단히 답하세요.", "하늘이 파란 이유를 한 문장으로.", Answer)))
