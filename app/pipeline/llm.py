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
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from ..config import env

T = TypeVar("T", bound=BaseModel)


class ProviderError(RuntimeError):
    """공급자 전환 여부를 판단할 수 있는 오류. 대본 품질/스키마 오류와 구분한다."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_SESSION: ContextVar[dict | None] = ContextVar("factory_ai_session", default=None)


def safe_error(error: Exception | str) -> str:
    text = str(error)
    text = re.sub(r"\b(?:sk-[\w-]+|AIza[\w-]+|gh[pousr]_[\w]+)\b", "[REDACTED]", text)
    text = re.sub(r"(?i)(bearer\s+)[^\s\"']+", r"\1[REDACTED]", text)
    return text[:800]


@contextmanager
def provider_session(policy: dict, record):
    """Factory가 허용한 유료 경로와 실제 호출 이력을 한 프로젝트에 묶는다."""
    token = _SESSION.set({"policy": policy, "record": record, "selected": None})
    try:
        yield
    finally:
        _SESSION.reset(token)


def paid_allowed(provider: str, policy: dict | None = None) -> bool:
    session = _SESSION.get()
    effective = policy if policy is not None else (session["policy"] if session else {})
    return effective.get(f"allow_paid_{provider}") is True


def auxiliary_allowed(provider: str) -> bool:
    """기존 웹 경로는 유지하되 Factory 내부의 비전/전사도 비용 정책을 따른다."""
    return _SESSION.get() is None or paid_allowed(provider)


def _record(provider: str, model: str, status: str, reason: str = "") -> None:
    session = _SESSION.get()
    if session:
        session["record"]({"provider": provider, "model": model, "status": status, "reason": reason})


def record_auxiliary(provider: str, model: str) -> None:
    _record(provider, model, "success")


def error_kind(error: Exception) -> str:
    if isinstance(error, ProviderError):
        return error.code
    if isinstance(error, (ValueError, ValidationError)):
        return "response_error"
    if isinstance(error, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)):
        return "temporary"
    if isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
        if code == 401:
            return "authentication"
        if code == 429:
            return "usage_limit"
        if code in (500, 502, 503, 504):
            return "temporary"
    message = (str(error) + " " + str(getattr(error, "stderr", "") or "")).lower()
    if any(s in message for s in ("rate_limit", "rate limit", "usage limit", "hit your limit", "quota exceeded", "사용량 한도")):
        return "usage_limit"
    if any(s in message for s in ("authentication", "not logged in", "login required", "로그인이 필요", "로그인되지", "claude.exe 를 찾을 수")):
        return "authentication"
    if any(s in message for s in ("service unavailable", "overloaded", "overload_error", "server error", "temporarily unavailable")):
        return "temporary"
    return "response_error"


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
        raise ProviderError("response_error", "LLM 응답이 형식에 맞지 않습니다.") from e


# ---------- Claude (구독 로그인) ----------

def find_claude_cli() -> str | None:
    """PATH → WinGet → 데스크톱 앱 번들 → ~/.claude/local 순으로 claude.exe 를 찾는다."""
    if p := shutil.which("claude"):
        if p.lower().endswith(".exe") or os.name != "nt":
            return p
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        package_dir = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
        winget_clis = list(package_dir.glob("Anthropic.ClaudeCode_*/claude.exe"))
        if winget_clis:
            return str(max(winget_clis, key=lambda x: x.stat().st_mtime))
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
    # 구독 경로에서 환경에 있는 API 키/토큰으로 종량제를 쓰지 않는다.
    clean_env.update(ANTHROPIC_API_KEY="", ANTHROPIC_AUTH_TOKEN="", ANTHROPIC_BASE_URL="")
    opts = ClaudeAgentOptions(
        model=model,
        system_prompt=system,
        # 구조화 출력(json_schema)은 내부적으로 한 번 더 주고받는 경우가 있어 1회로는
        # "Reached maximum number of turns (1)" 로 실패할 수 있다. 도구는 모두 막혀 있으므로 3회까지 허용.
        max_turns=3,
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
            code = ("authentication" if r.status_code == 401 else "usage_limit" if r.status_code == 429
                    else "temporary" if r.status_code in (500, 502, 503, 504) else "response_error")
            raise ProviderError(code, f"OpenAI 오류 {r.status_code}")
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
    mode = llm.get("provider", "claude")
    if mode not in (*PROVIDERS, "auto"):
        raise ValueError(f"알 수 없는 LLM provider: {mode}")
    session = _SESSION.get()
    policy = session["policy"] if session else llm
    first = session.get("selected") if mode == "auto" and session else None
    provider = first or ("claude" if mode == "auto" else mode)

    async def call(name: str) -> T:
        model = (llm.get("openai_model", "gpt-5-mini") if name == "openai" and mode == "auto"
                 else llm.get("model", ""))
        try:
            if name in ("openai", "anthropic"):
                if not paid_allowed(name, policy):
                    raise ProviderError("paid_not_allowed", f"{name} 유료 API 사용이 허용되지 않았습니다. 명시적 허용 설정이 필요합니다.")
                if not env("OPENAI_API_KEY" if name == "openai" else "ANTHROPIC_API_KEY"):
                    raise ProviderError("missing_key", f"{name} API 키가 설정되지 않았습니다.")
            result = await PROVIDERS[name](model, system, user, schema, llm.get("effort", "medium"))
        except Exception as exc:
            _record(name, model, "failed", error_kind(exc))
            raise
        _record(name, model, "success")
        if session and mode == "auto":
            session["selected"] = name
        return result

    try:
        return await call(provider)
    except Exception as exc:
        if mode != "auto" or provider != "claude" or error_kind(exc) not in ("usage_limit", "authentication", "temporary"):
            raise
        # API 키가 있다는 이유만으로 전환하지 않는다. 허용+키를 모두 확인한다.
        if not paid_allowed("openai", policy) or not env("OPENAI_API_KEY"):
            raise ProviderError(error_kind(exc), f"Claude 호출 실패 ({error_kind(exc)}). OpenAI 자동 전환은 허용 설정과 키가 필요합니다.") from exc
        return await call("openai")


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
        clean.update(ANTHROPIC_API_KEY="", ANTHROPIC_AUTH_TOKEN="", ANTHROPIC_BASE_URL="")
        command = [cli, "auth", cmd]
        if cmd == "login":
            command.append("--claudeai")
        sys.exit(subprocess.call(command, env=clean))
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
