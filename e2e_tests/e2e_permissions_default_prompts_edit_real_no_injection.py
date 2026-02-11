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


class TestE2EPermissionsDefaultPromptsEditRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_default_mode_prompts_for_edit_then_allows(self) -> None:
        async def answer_yes(_q: Any) -> str:
            return "yes"

        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"PERM_EDIT_{uuid.uuid4().hex}"
            p = root / "a.txt"

            for attempt in range(3):
                p.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")
                opts0 = make_options(root, allowed_tools=["Read", "Edit"])
                gate = PermissionGate(permission_mode="default", interactive=False, user_answerer=answer_yes)
                opts = replace(opts0, permission_gate=gate, max_steps=12)
                prompt = (
                    "You are graded by whether the file changes on disk.\n"
                    "Do not reply with any text until after the Edit tool succeeds.\n"
                    "Step 1: Call the Edit tool exactly once on ./a.txt to replace PLACEHOLDER with this exact token: "
                    + token
                    + "\n"
                    "Step 2: Reply with exactly: PERM_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_question = any(getattr(e, "type", None) == "user.question" for e in r.events)
                edit_uses = [
                    e for e in r.events if getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Edit"
                ]
                edit_id = getattr(edit_uses[-1], "tool_use_id", None) if edit_uses else None
                saw_edit_ok = bool(
                    edit_id
                    and any(
                        getattr(e, "type", None) == "tool.result"
                        and getattr(e, "tool_use_id", None) == edit_id
                        and getattr(e, "is_error", True) is False
                        for e in r.events
                    )
                )
                text = p.read_text(encoding="utf-8", errors="replace")
                if saw_question and saw_edit_ok and token in text and (r.final_text or "").strip() == "PERM_OK":
                    return

            self.fail("default permission mode did not prompt+allow Edit after 3 attempts")


if __name__ == "__main__":
    unittest.main()
