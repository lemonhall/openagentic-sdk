from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests._harness import make_options


class TestE2EPermAcceptEditsWriteRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_accept_edits_allows_write_without_prompt(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"ACCEPT_WRITE_{uuid.uuid4().hex}"
            p = root / "w.txt"

            for attempt in range(3):
                if p.exists():
                    p.unlink()
                opts0 = make_options(root, allowed_tools=["Write"])
                gate = PermissionGate(permission_mode="acceptEdits", interactive=False)
                opts = replace(opts0, permission_gate=gate, max_steps=12)
                prompt = (
                    "You are graded by whether the file exists on disk and no prompt is shown.\n"
                    "You MUST call the Write tool exactly once.\n"
                    "Do not reply with any text until after the Write tool succeeds.\n"
                    "Write tool input:\n"
                    "- file_path: ./w.txt\n"
                    f"- content: {token}\n"
                    "- overwrite: true\n"
                    "After the tool succeeds, reply with exactly: ACCEPT_WRITE_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_write = any(
                    getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Write" for e in r.events
                )
                saw_question = any(getattr(e, "type", None) == "user.question" for e in r.events)
                text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                if saw_write and (not saw_question) and token in text and (r.final_text or "").strip() == "ACCEPT_WRITE_OK":
                    return

            self.fail("acceptEdits did not allow Write without prompting after 3 attempts")


if __name__ == "__main__":
    unittest.main()
