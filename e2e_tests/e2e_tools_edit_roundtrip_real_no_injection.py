from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EToolsEditRoundtripRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_model_uses_edit_to_change_file_content(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"EDIT_TOKEN_{uuid.uuid4().hex}"
            p = root / "a.txt"

            # Real-network tests can be flaky when relying on the model to choose tools.
            # Best-effort: allow a few attempts before failing.
            for attempt in range(3):
                p.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")
                opts = make_options(root, allowed_tools=["Read", "Edit"])
                prompt = (
                    "You are graded by whether the file content actually changes on disk.\n"
                    "Do not reply with any text until after you have finished Step 2.\n"
                    "Step 1: Call the Read tool on ./a.txt.\n"
                    "Step 2: Call the Edit tool exactly once with:\n"
                    "- file_path: ./a.txt\n"
                    "- old: PLACEHOLDER\n"
                    f"- new: {token}\n"
                    "- count: 1\n"
                    "After the tool succeeds, reply with exactly: EDIT_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                events: list[object] = []
                async for ev in openagentic_sdk.query(prompt=prompt, options=opts):
                    events.append(ev)

                saw_edit = any(
                    getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Edit" for e in events
                )
                text = p.read_text(encoding="utf-8", errors="replace")
                if saw_edit and token in text:
                    return

            self.fail("model did not apply Edit after 3 attempts")


if __name__ == "__main__":
    unittest.main()
