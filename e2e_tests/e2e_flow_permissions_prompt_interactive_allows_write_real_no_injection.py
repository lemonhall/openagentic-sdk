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


class TestE2EFlowPermissionsPromptInteractiveAllowsWriteRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_interactive_prompt_allows_write_without_user_question(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"INTERACTIVE_ALLOW_{uuid.uuid4().hex}"
            p = root / "interactive_allow.txt"

            approver = InteractiveApprover(input_fn=lambda _prompt: "yes")
            gate = PermissionGate(permission_mode="prompt", interactive=True, interactive_approver=approver)
            opts0 = make_options(root, allowed_tools=["Write"])
            opts = replace(opts0, permission_gate=gate, max_steps=10)

            for attempt in range(6):
                if p.exists():
                    p.unlink()
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 1 completes.\n"
                    "Step 1: Call Write to write ./interactive_allow.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "After tool succeeds, reply with exactly: INTERACTIVE_ALLOW_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                if (r.final_text or "").strip() == "INTERACTIVE_ALLOW_OK" and p.exists():
                    if token in p.read_text(encoding="utf-8", errors="replace"):
                        saw_question = any(getattr(e, "type", None) == "user.question" for e in r.events)
                        if not saw_question:
                            return

            self.fail("interactive prompt did not allow write without user.question after 6 attempts")


if __name__ == "__main__":
    unittest.main()

