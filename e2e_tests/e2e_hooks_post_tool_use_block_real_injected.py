from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options


class TestE2EHooksPostToolUseBlockRealInjected(unittest.IsolatedAsyncioTestCase):
    async def test_post_tool_use_block_turns_success_into_error(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"POST_BLOCK_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token + "\n", encoding="utf-8")

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
                            tool_calls=[ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "./a.txt"})],
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
                            assistant_text="POST_BLOCK_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            async def post_block_read(payload: Mapping[str, Any]) -> HookDecision:
                tool_name = payload.get("tool_name")
                if tool_name == "Read":
                    return HookDecision(block=True, block_reason="blocked by post tool hook", action="block")
                return HookDecision()

            hooks = HookEngine(
                after_model_call=[HookMatcher(name="inject-read", tool_name_pattern="*", hook=inject_read_then_finish)],
                post_tool_use=[HookMatcher(name="post-block-read", tool_name_pattern="Read", hook=post_block_read)],
            )
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, max_steps=8)

            r = await openagentic_sdk.run(prompt="Run Read but post-hook blocks it.", options=opts)
            self.assertEqual((r.final_text or "").strip(), "POST_BLOCK_OK")

            blocked = [
                e
                for e in r.events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-read-1"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(blocked)
            self.assertEqual(getattr(blocked[-1], "error_type", None), "RuntimeError")
            self.assertIn("blocked by post tool hook", str(getattr(blocked[-1], "error_message", "") or ""))


if __name__ == "__main__":
    unittest.main()

