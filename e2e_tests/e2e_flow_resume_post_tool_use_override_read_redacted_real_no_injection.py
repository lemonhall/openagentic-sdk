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


class TestE2EFlowResumePostToolUseOverrideReadRedactedRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_resume_then_post_tool_use_override_redacts_read(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            token = f"RESUME_REDACT_{uuid.uuid4().hex}"

            opts0 = make_options(root, allowed_tools=["Write", "Read"])

            # Run 1: write file.
            p = root / "a.txt"
            for attempt in range(4):
                if p.exists():
                    p.unlink()
                opts1 = replace(opts0, resume=session_id, max_steps=12)
                prompt1 = (
                    "You MUST use tools.\n"
                    "Step 1: Call Write to write ./a.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "After tool succeeds, reply with exactly: TURN1_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r1 = await openagentic_sdk.run(prompt=prompt1, options=opts1)
                text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                if token in text and (r1.final_text or "").strip() == "TURN1_OK":
                    break
            else:
                self.fail("run1 did not write file after 4 attempts")

            # Run 2: enable post_tool_use redaction for Read.
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
            opts2 = replace(opts0, resume=session_id, hooks=hooks, max_steps=10)
            for attempt in range(4):
                prompt2 = (
                    "You MUST use tools.\n"
                    "Step 1: Call Read on ./a.txt.\n"
                    "Step 2: Reply with exactly the content you saw.\n"
                    "Do not add any other text.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r2 = await openagentic_sdk.run(prompt=prompt2, options=opts2)
                if (r2.final_text or "").strip() == "REDACTED":
                    return
            self.fail("run2 did not return REDACTED after 4 attempts")


if __name__ == "__main__":
    unittest.main()

