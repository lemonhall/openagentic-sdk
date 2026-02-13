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


class TestE2EFlowPermDefaultWriteDeniedRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_default_permission_write_denied_does_not_write(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"DENY_WRITE_{uuid.uuid4().hex}"
            p = root / "denied.txt"

            async def answer_no(_q: Any) -> str:
                return "no"

            for attempt in range(6):
                if p.exists():
                    p.unlink()
                opts0 = make_options(root, allowed_tools=["Write"])
                gate = PermissionGate(permission_mode="default", interactive=False, user_answerer=answer_no)
                opts = replace(opts0, permission_gate=gate, max_steps=12)
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after the tool attempt completes.\n"
                    "Step 1: Call Write to write ./denied.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "Step 2: If the tool was denied, reply with exactly: DENY_OK\n"
                    "Do not attempt any other tools.\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)

                saw_question = any(getattr(e, "type", None) == "user.question" for e in r.events)
                denied_results = [
                    e
                    for e in r.events
                    if getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", "") == "PermissionDenied"
                ]
                if saw_question and denied_results and (r.final_text or "").strip() == "DENY_OK" and not p.exists():
                    return

            self.fail("default permission did not deny Write safely after 6 attempts")


if __name__ == "__main__":
    unittest.main()
