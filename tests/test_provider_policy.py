"""V1 공급자 선택/유료 허용/전환 조건. 외부 호출 없이 검증한다."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from pydantic import BaseModel

from app.pipeline import llm, vision, reference


class Answer(BaseModel):
    text: str


class ProviderPolicyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.claude = AsyncMock(return_value=Answer(text="claude"))
        self.openai = AsyncMock(return_value=Answer(text="openai"))
        self.anthropic = AsyncMock(return_value=Answer(text="anthropic"))
        self.providers = patch.dict(llm.PROVIDERS, claude=self.claude, openai=self.openai, anthropic=self.anthropic)
        self.providers.start()
        self.addCleanup(self.providers.stop)
        self.events = []

    async def call(self, mode="auto", allowed=False, key=True):
        cfg = {"provider": mode, "model": "claude-model" if mode != "openai" else "gpt-model",
               "openai_model": "gpt-fallback", "allow_paid_openai": allowed}
        with patch.object(llm, "env", return_value="test-key" if key else None), llm.provider_session(cfg, self.events.append):
            return await llm.ask_structured(cfg, "system", "user", Answer)

    async def test_claude_never_uses_anthropic_key(self):
        result = await self.call("claude")
        self.assertEqual(result.text, "claude")
        self.openai.assert_not_awaited()
        self.anthropic.assert_not_awaited()
        self.assertEqual(self.events[0]["provider"], "claude")

    async def test_openai_requires_explicit_permission(self):
        with self.assertRaisesRegex(llm.ProviderError, "허용"):
            await self.call("openai")
        self.openai.assert_not_awaited()

    async def test_openai_requires_key(self):
        with self.assertRaisesRegex(llm.ProviderError, "키"):
            await self.call("openai", allowed=True, key=False)
        self.openai.assert_not_awaited()

    async def test_openai_explicit_selection(self):
        result = await self.call("openai", allowed=True)
        self.assertEqual(result.text, "openai")
        self.claude.assert_not_awaited()
        self.assertEqual(self.events[0]["status"], "success")

    async def test_auto_prefers_subscription(self):
        await self.call(allowed=True)
        self.openai.assert_not_awaited()

    async def test_auto_limit_does_not_spend_without_permission(self):
        self.claude.side_effect = RuntimeError("You've hit your limit")
        with self.assertRaises(llm.ProviderError):
            await self.call()
        self.openai.assert_not_awaited()
        self.anthropic.assert_not_awaited()

    async def test_auto_limit_requires_key_even_when_allowed(self):
        self.claude.side_effect = llm.ProviderError("usage_limit", "한도")
        with self.assertRaises(llm.ProviderError):
            await self.call(allowed=True, key=False)
        self.openai.assert_not_awaited()

    async def test_auto_falls_back_only_for_eligible_errors(self):
        for code in ("usage_limit", "authentication", "temporary"):
            with self.subTest(code=code):
                self.events.clear()
                self.claude.side_effect = llm.ProviderError(code, "테스트 오류")
                result = await self.call(allowed=True)
                self.assertEqual(result.text, "openai")
                self.assertEqual([(e["provider"], e["status"]) for e in self.events],
                                 [("claude", "failed"), ("openai", "success")])
                self.assertEqual(self.openai.await_args.args[0], "gpt-fallback")

    async def test_auto_does_not_recall_for_bad_content_or_schema(self):
        for error in (ValueError("bad JSON"), ValueError("bad JSON contains rate limit text"), RuntimeError("LLM 응답이 형식에 맞지 않습니다"),
                      RuntimeError("OpenAI 가 이 요청을 거부했습니다"), RuntimeError("maximum turns reached")):
            with self.subTest(error=str(error)):
                self.claude.side_effect = error
                with self.assertRaises(type(error)):
                    await self.call(allowed=True)
        self.openai.assert_not_awaited()

    async def test_schema_validation_with_limit_words_never_switches(self):
        with self.assertRaises(llm.ProviderError) as ctx:
            llm._validate(Answer, {"unexpected": "rate limit"})
        self.assertEqual(llm.error_kind(ctx.exception), "response_error")

    async def test_auto_sticks_to_successful_fallback_for_one_project(self):
        cfg = {"provider": "auto", "model": "claude-model", "allow_paid_openai": True}
        self.claude.side_effect = llm.ProviderError("authentication", "로그인 필요")
        with patch.object(llm, "env", return_value="test-key"), llm.provider_session(cfg, self.events.append):
            await llm.ask_structured(cfg, "s", "u", Answer)
            await llm.ask_structured(cfg, "s", "u", Answer)
        self.assertEqual(self.claude.await_count, 1)
        self.assertEqual(self.openai.await_count, 2)

    async def test_vision_and_transcription_cannot_spend_from_environment_keys(self):
        with llm.provider_session({}, self.events.append), patch.object(vision, "env", return_value="test-key"):
            self.assertFalse(vision.vision_available("gemini"))
            self.assertFalse(vision.vision_available("openai"))
            with self.assertRaisesRegex(RuntimeError, "허용"):
                await reference._transcribe_audio(None, True)

    async def test_context_permission_does_not_leak_to_next_project(self):
        await self.call("openai", allowed=True)
        self.assertFalse(llm.paid_allowed("openai"))

    async def test_anthropic_direct_call_is_blocked_by_default(self):
        with self.assertRaises(llm.ProviderError):
            await llm.ask_structured({"provider": "anthropic", "model": "m"}, "s", "u", Answer)
        self.anthropic.assert_not_awaited()

    async def test_http_status_classification(self):
        for status, expected in ((401, "authentication"), (429, "usage_limit"), (503, "temporary"), (400, "response_error")):
            request = httpx.Request("POST", "https://example.com")
            error = httpx.HTTPStatusError("error", request=request, response=httpx.Response(status, request=request))
            self.assertEqual(llm.error_kind(error), expected)

    async def test_claude_sdk_cannot_inherit_paid_credentials(self):
        captured = []
        class Message:
            is_error = False
            subtype = "success"
            structured_output = {"text": "subscription"}
        async def query(**kwargs):
            captured.append(kwargs["options"])
            yield Message()
        sdk = SimpleNamespace(ClaudeAgentOptions=lambda **kw: kw, ResultMessage=Message, query=query)
        with patch.dict("sys.modules", {"claude_agent_sdk": sdk}), patch.object(llm, "find_claude_cli", return_value="claude.exe"), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key", "ANTHROPIC_AUTH_TOKEN": "test-token"}):
            result = await llm._ask_claude_code("m", "s", "u", Answer, "medium")
        self.assertEqual(result.text, "subscription")
        self.assertEqual(captured[0]["env"]["ANTHROPIC_API_KEY"], "")
        self.assertEqual(captured[0]["env"]["ANTHROPIC_AUTH_TOKEN"], "")

    async def test_error_redaction(self):
        self.assertNotIn("testsecret", llm.safe_error("Bearer testsecret sk-testsecret"))
