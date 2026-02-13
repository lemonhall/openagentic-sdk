from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests._harness import make_options


class TestE2EFlowPermissionsPromptNoAnswererDeniesRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_mode_without_answerer_prompts_then_denies(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"PROMPT_NO_ANSWERER_{uuid.uuid4().hex}"
            p = root / "no_answerer.txt"

            opts0 = make_options(root, allowed_tools=["Write"])
            gate = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=None)
            opts = replace(opts0, permission_gate=gate, max_steps=12)

            for attempt in range(6):
                if p.exists():
                    p.unlink()
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 1 completes.\n"
                    "Step 1: Call Write to write ./no_answerer.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "Step 2: If you were prompted and then denied, reply with exactly: PROMPT_DENY_OK\n"
                    "Do not attempt any other tools.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)

                saw_question = any(getattr(e, "type", None) == "user.question" for e in r.events)
                denied = [
                    e
                    for e in r.events
                    if getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", "") == "PermissionDenied"
                ]
                if saw_question and denied and (r.final_text or "").strip() == "PROMPT_DENY_OK" and not p.exists():
                    return

            self.fail("prompt mode without user_answerer did not deny safely after 6 attempts")


if __name__ == "__main__":
    unittest.main()

