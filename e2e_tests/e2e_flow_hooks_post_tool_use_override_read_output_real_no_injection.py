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


class TestE2EFlowHooksPostToolUseOverrideReadOutputRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_post_tool_use_can_override_read_content_visible_to_model(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"HOOK_SRC_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token + "\n", encoding="utf-8")

            async def override_read_output(payload: Mapping[str, Any]) -> HookDecision:
                if payload.get("tool_name") != "Read":
                    return HookDecision()
                out = payload.get("tool_output")
                if not isinstance(out, dict):
                    return HookDecision()
                out2 = dict(out)
                out2["content"] = "REDACTED"
                return HookDecision(action="rewrite_read_output", override_tool_output=out2)

            hooks = HookEngine(post_tool_use=[HookMatcher(name="override-read", tool_name_pattern="Read", hook=override_read_output)])
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, max_steps=10)

            for attempt in range(4):
                prompt = (
                    "You are graded by whether you follow tool output.\n"
                    "You MUST use tools.\n"
                    "Step 1: Call Read on ./a.txt.\n"
                    "Step 2: Reply with exactly the content you saw from the Read tool.\n"
                    "Do not add any other text.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                if (r.final_text or "").strip() == "REDACTED":
                    return

            self.fail("model did not return overridden Read output after 4 attempts")


if __name__ == "__main__":
    unittest.main()

