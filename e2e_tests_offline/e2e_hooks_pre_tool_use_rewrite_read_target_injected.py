from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _ReadWithRewriteHookProvider:
    name = "offline-hooks-rewrite-read"

    def __init__(self) -> None:
        self._n = 0

    async def complete(self, *, model: str, input, **kwargs):  # noqa: A002
        _ = model, kwargs
        from openagentic_sdk.providers.base import ModelOutput, ToolCall

        items = list(input)
        self._n += 1

        if self._n == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "./a.txt"})],
                response_id="resp-rewrite-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-read-1")
            if payload.get("is_error") is True:
                raise AssertionError(f"expected read success, got: {payload!r}")
            if "B_TOKEN_" not in str(payload.get("content") or ""):
                raise AssertionError(f"expected rewritten read content to include B_TOKEN_, got: {payload!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_HOOK_REWRITE_OK",
                tool_calls=(),
                response_id="resp-rewrite-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineHooksPreToolUseRewriteReadTargetInjected(unittest.IsolatedAsyncioTestCase):
    async def test_pre_tool_use_rewrites_read_target_deterministically(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token_a = f"A_TOKEN_{uuid.uuid4().hex}"
            token_b = f"B_TOKEN_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token_a, encoding="utf-8")
            (root / "b.txt").write_text(token_b, encoding="utf-8")

            async def _rewrite_read(payload):  # noqa: ANN001
                if payload.get("tool_name") != "Read":
                    return HookDecision()
                ti = payload.get("tool_input")
                fp = ti.get("file_path") if isinstance(ti, dict) else None
                if fp == "./a.txt":
                    return HookDecision(action="rewrite_read", override_tool_input={"file_path": "./b.txt"})
                return HookDecision()

            hooks = HookEngine(pre_tool_use=[HookMatcher(name="rewrite-a-to-b", tool_name_pattern="Read", hook=_rewrite_read)])
            opts0 = make_options_offline(root, provider=_ReadWithRewriteHookProvider(), allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="read with rewrite hook", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_HOOK_REWRITE_OK")

            saw_hook = any(
                getattr(e, "type", None) == "hook.event" and getattr(e, "hook_point", "") == "PreToolUse" for e in r.events
            )
            self.assertTrue(saw_hook, "expected a PreToolUse hook.event")

            read_results = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", None) == "call-read-1"
            ]
            output_text = str(getattr(read_results[-1], "output", "") or "") if read_results else ""
            self.assertIn(token_b, output_text)


if __name__ == "__main__":
    unittest.main()

