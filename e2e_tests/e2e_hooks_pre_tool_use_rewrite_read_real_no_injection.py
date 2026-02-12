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


class TestE2EHooksPreToolUseRewriteReadRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_pre_tool_use_rewrites_read_target(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token_a = f"A_TOKEN_{uuid.uuid4().hex}"
            token_b = f"B_TOKEN_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token_a, encoding="utf-8")
            (root / "b.txt").write_text(token_b, encoding="utf-8")

            async def rewrite_read(payload: Mapping[str, Any]) -> HookDecision:
                tool_name = payload.get("tool_name")
                tool_input = payload.get("tool_input")
                if tool_name != "Read" or not isinstance(tool_input, dict):
                    return HookDecision()
                fp = tool_input.get("file_path") or tool_input.get("filePath")
                if str(fp) == "./a.txt":
                    return HookDecision(action="rewrite_read", override_tool_input={"file_path": "./b.txt"})
                return HookDecision()

            hooks = HookEngine(pre_tool_use=[HookMatcher(name="rewrite-read-a-to-b", tool_name_pattern="Read", hook=rewrite_read)])

            for attempt in range(3):
                opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
                opts = replace(opts0, max_steps=8)
                prompt = (
                    "Step 1: Call Read on ./a.txt\n"
                    "Step 2: Reply with exactly the token you saw in the tool output.\n"
                    "Do not guess.\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_hook = any(
                    getattr(e, "type", None) == "hook.event" and getattr(e, "hook_point", "") == "PreToolUse" for e in r.events
                )
                read_uses = [
                    e for e in r.events if getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Read"
                ]
                read_id = getattr(read_uses[-1], "tool_use_id", None) if read_uses else None
                read_results = (
                    [
                        e
                        for e in r.events
                        if getattr(e, "type", None) == "tool.result"
                        and getattr(e, "tool_use_id", None) == read_id
                        and getattr(e, "is_error", False) is False
                    ]
                    if read_id
                    else []
                )
                output_text = str(getattr(read_results[-1], "output", "") or "") if read_results else ""
                if saw_hook and token_b in output_text:
                    return

            self.fail("pre_tool_use hook did not rewrite Read target as expected after 3 attempts")


if __name__ == "__main__":
    unittest.main()
