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


class TestE2EFlowResumeAcceptEditsEditThenReadRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_resume_accept_edits_allows_edit_without_prompt(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            token = f"ACCEPT_EDITS_{uuid.uuid4().hex}"
            p = root / "a.txt"
            p.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")

            async def answerer_should_not_be_called(_q: Any) -> str:
                raise AssertionError("acceptEdits should not prompt for Edit/Write/NotebookEdit")

            gate = PermissionGate(permission_mode="acceptEdits", interactive=False, user_answerer=answerer_should_not_be_called)
            opts0 = make_options(root, allowed_tools=["Edit"])

            # Run 1: Edit only (acceptEdits would prompt for Read).
            for attempt in range(4):
                p.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")
                opts1 = replace(opts0, resume=session_id, permission_gate=gate, max_steps=18)
                prompt1 = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 1 succeeds.\n"
                    "Step 1: Call Edit on ./a.txt to replace PLACEHOLDER with this token (count=1):\n"
                    f"{token}\n"
                    "After the tool succeeds, reply with exactly: TURN1_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r1 = await openagentic_sdk.run(prompt=prompt1, options=opts1)
                if any(getattr(e, "type", None) == "user.question" for e in r1.events):
                    self.fail("unexpected user.question in acceptEdits flow")
                text = p.read_text(encoding="utf-8", errors="replace")
                if token in text and (r1.final_text or "").strip() == "TURN1_OK":
                    break
            else:
                self.fail("run1 did not edit file under acceptEdits after 4 attempts")

            events_path = root / "sessions" / session_id / "events.jsonl"
            before_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())

            # Run 2: Read under default (safe tool, should not prompt).
            async def answerer_should_not_be_called_default(_q: Any) -> str:
                raise AssertionError("default permission must not prompt for Read")

            gate2 = PermissionGate(
                permission_mode="default", interactive=False, user_answerer=answerer_should_not_be_called_default
            )
            opts0b = make_options(root, allowed_tools=["Read"])
            for attempt in range(4):
                opts2 = replace(opts0b, resume=session_id, permission_gate=gate2, max_steps=10)
                prompt2 = (
                    "You MUST use tools.\n"
                    "Step 1: Call Read on ./a.txt.\n"
                    "Step 2: Reply with exactly the token you saw.\n"
                    "Do not add any other text.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r2 = await openagentic_sdk.run(prompt=prompt2, options=opts2)
                if token in (r2.final_text or ""):
                    after_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())
                    self.assertGreater(after_lines, before_lines)
                    return
            self.fail("run2 did not read and return token after 4 attempts")


if __name__ == "__main__":
    unittest.main()
