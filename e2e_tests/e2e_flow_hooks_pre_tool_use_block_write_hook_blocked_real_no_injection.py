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

from e2e_tests._harness import make_options


class TestE2EFlowHooksPreToolUseBlockWriteHookBlockedRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_pre_tool_use_blocks_write_as_hook_blocked(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"HOOK_BLOCK_{uuid.uuid4().hex}"
            p = root / "blocked.txt"

            async def block_write(payload: Mapping[str, Any]) -> HookDecision:
                if payload.get("tool_name") == "Write":
                    return HookDecision(block=True, block_reason="blocked by test hook", action="block_write")
                return HookDecision()

            hooks = HookEngine(pre_tool_use=[HookMatcher(name="block-write", tool_name_pattern="Write", hook=block_write)])
            opts0 = make_options(root, allowed_tools=["Write"], hooks=hooks)
            opts = replace(opts0, max_steps=12)

            for attempt in range(6):
                if p.exists():
                    p.unlink()
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 1 completes.\n"
                    "Step 1: Call Write to write ./blocked.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "Step 2: If the tool was blocked, reply with exactly: HOOK_BLOCK_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)

                saw_hook = any(
                    getattr(e, "type", None) == "hook.event" and getattr(e, "hook_point", "") == "PreToolUse" for e in r.events
                )
                blocked = [
                    e
                    for e in r.events
                    if getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", "") == "HookBlocked"
                ]
                if saw_hook and blocked and (r.final_text or "").strip() == "HOOK_BLOCK_OK" and not p.exists():
                    return

            self.fail("pre_tool_use did not block Write as HookBlocked after 6 attempts")


if __name__ == "__main__":
    unittest.main()

