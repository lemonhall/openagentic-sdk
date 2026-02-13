from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options


class TestE2ERuntimeHookBlocksToolReal(unittest.IsolatedAsyncioTestCase):
    async def test_pre_tool_use_block_emits_hookblocked(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "fixture.txt").write_text("hello", encoding="utf-8")

            stage = 0

            async def inject_read_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_read",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-read-1",
                                    name="Read",
                                    arguments={"file_path": "./fixture.txt"},
                                )
                            ],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                if stage == 1:
                    stage = 2
                    return HookDecision(
                        action="inject_final_text",
                        override_tool_output=ModelOutput(
                            assistant_text="HOOK_BLOCK_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            async def block_read(_: Mapping[str, Any]) -> HookDecision:
                return HookDecision(block=True, block_reason="blocked-by-test", action="block_read")

            hooks = HookEngine(
                after_model_call=[HookMatcher(name="inject-read", tool_name_pattern="*", hook=inject_read_then_finish)],
                pre_tool_use=[HookMatcher(name="block-read", tool_name_pattern="Read", hook=block_read)],
            )

            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, max_steps=5)

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt="Read ./fixture.txt", options=opts):
                events.append(ev)

            saw_tool_use = any(
                getattr(e, "type", None) == "tool.use" and getattr(e, "tool_use_id", None) == "call-read-1" for e in events
            )
            self.assertTrue(saw_tool_use)

            blocked = [
                e
                for e in events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-1"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(blocked)
            self.assertEqual(getattr(blocked[-1], "error_type", None), "HookBlocked")
            self.assertIn("blocked-by-test", str(getattr(blocked[-1], "error_message", "") or ""))


if __name__ == "__main__":
    unittest.main()

