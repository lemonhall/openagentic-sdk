from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import openagentic_sdk
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests._harness import make_options


class TestE2EFlowPermissionsAcceptEditsReadPromptsAndDeniesRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_accept_edits_read_still_prompts_and_can_be_denied(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"ACCEPT_EDITS_READ_{uuid.uuid4().hex}"
            p = root / "a.txt"
            p.write_text(token, encoding="utf-8")

            async def answer_no(_q: Any) -> str:
                return "no"

            opts0 = make_options(root, allowed_tools=["Read"])
            gate = PermissionGate(permission_mode="acceptEdits", interactive=False, user_answerer=answer_no)
            opts = replace(opts0, permission_gate=gate, max_steps=10)

            for attempt in range(6):
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 1 completes.\n"
                    "Step 1: Call Read on ./a.txt.\n"
                    "Step 2: If you were prompted and then denied, reply with exactly: ACCEPT_EDITS_READ_DENY_OK\n"
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
                if saw_question and denied and (r.final_text or "").strip() == "ACCEPT_EDITS_READ_DENY_OK":
                    return

            self.fail("acceptEdits did not prompt+deny non-edit tool after 6 attempts")


if __name__ == "__main__":
    unittest.main()

