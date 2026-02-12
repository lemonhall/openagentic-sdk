from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests._harness import make_options


class TestE2EPermAcceptEditsEditRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_accept_edits_allows_edit_without_prompt(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"ACCEPT_EDIT_{uuid.uuid4().hex}"
            p = root / "a.txt"

            for attempt in range(3):
                p.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")
                opts0 = make_options(root, allowed_tools=["Edit"])
                gate = PermissionGate(permission_mode="acceptEdits", interactive=False)
                opts = replace(opts0, permission_gate=gate, max_steps=12)
                prompt = (
                    "You are graded by whether the file changes on disk and no prompt is shown.\n"
                    "You MUST call the Edit tool exactly once.\n"
                    "Do not reply with any text until after the Edit tool succeeds.\n"
                    "Step 1: Call Edit exactly once on ./a.txt to replace PLACEHOLDER with this exact token: "
                    + token
                    + "\n"
                    "After the tool succeeds, reply with exactly: ACCEPT_EDIT_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_edit = any(
                    getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Edit" for e in r.events
                )
                saw_question = any(getattr(e, "type", None) == "user.question" for e in r.events)
                text = p.read_text(encoding="utf-8", errors="replace")
                if saw_edit and (not saw_question) and token in text and (r.final_text or "").strip() == "ACCEPT_EDIT_OK":
                    return

            self.fail("acceptEdits did not allow Edit without prompting after 3 attempts")


if __name__ == "__main__":
    unittest.main()
