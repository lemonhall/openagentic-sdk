from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.permissions.interactive import InteractiveApprover

from e2e_tests._harness import make_options


class TestE2EFlowPermissionsPromptInteractiveDeniesRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_interactive_prompt_denies_without_user_question(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"INTERACTIVE_DENY_{uuid.uuid4().hex}"
            p = root / "interactive_deny.txt"

            approver = InteractiveApprover(input_fn=lambda _prompt: "no")
            gate = PermissionGate(permission_mode="prompt", interactive=True, interactive_approver=approver)
            opts0 = make_options(root, allowed_tools=["Write"])
            opts = replace(opts0, permission_gate=gate, max_steps=10)

            for attempt in range(6):
                if p.exists():
                    p.unlink()
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 1 completes.\n"
                    "Step 1: Call Write to write ./interactive_deny.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "Step 2: If you were denied, reply with exactly: INTERACTIVE_DENY_OK\n"
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
                if not saw_question and denied and (r.final_text or "").strip() == "INTERACTIVE_DENY_OK" and not p.exists():
                    return

            self.fail("interactive prompt did not deny without user.question after 6 attempts")


if __name__ == "__main__":
    unittest.main()

