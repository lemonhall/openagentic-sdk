from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _WriteBlockedByHookProvider:
    name = "offline-hooks-block-write"

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
                tool_calls=[
                    ToolCall(
                        tool_use_id="call-write-1",
                        name="Write",
                        arguments={"file_path": "blocked.txt", "content": "NOPE", "overwrite": True},
                    )
                ],
                response_id="resp-hook-block-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-write-1")
            if payload.get("is_error") is not True:
                raise AssertionError(f"expected is_error true, got: {payload!r}")
            if payload.get("error_type") != "HookBlocked":
                raise AssertionError(f"expected HookBlocked, got: {payload.get('error_type')!r}")
            msg = str(payload.get("error_message") or "")
            if "no-write" not in msg:
                raise AssertionError(f"expected hook block reason in error_message, got: {msg!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_HOOK_BLOCK_OK",
                tool_calls=(),
                response_id="resp-hook-block-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineHooksPreToolUseBlockWrite(unittest.IsolatedAsyncioTestCase):
    async def test_pre_tool_use_block_prevents_write_and_has_no_side_effect(self) -> None:
        async def _block_write(payload):  # noqa: ANN001
            if payload.get("tool_name") == "Write":
                return HookDecision(block=True, block_reason="no-write")
            return HookDecision()

        hooks = HookEngine(pre_tool_use=[HookMatcher(name="block-write", tool_name_pattern="Write", hook=_block_write)])

        with TemporaryDirectory() as td:
            root = Path(td)
            p = root / "blocked.txt"

            opts0 = make_options_offline(root, provider=_WriteBlockedByHookProvider(), allowed_tools=["Write"], hooks=hooks)
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="run hook-blocked write", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_HOOK_BLOCK_OK")
            self.assertFalse(p.exists(), "blocked write should not have created blocked.txt")

            saw_hook = any(
                getattr(e, "type", None) == "hook.event" and getattr(e, "hook_point", "") == "PreToolUse" for e in r.events
            )
            self.assertTrue(saw_hook, "expected a PreToolUse hook.event")


if __name__ == "__main__":
    unittest.main()

