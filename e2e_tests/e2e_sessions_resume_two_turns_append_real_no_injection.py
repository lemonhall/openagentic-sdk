from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2ESessionsResumeTwoTurnsAppendRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_same_resume_session_appends_events_across_runs(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            token = f"APPEND_TOKEN_{uuid.uuid4().hex}"
            p = root / "a.txt"

            opts0 = make_options(root, allowed_tools=["Write", "Read"])
            opts = replace(opts0, resume=session_id, max_steps=10)
            prompt1 = (
                "Do not reply until after the Write tool succeeds.\n"
                "Step 1: Write ./a.txt with content: " + token + "\n"
                "Step 2: Reply with exactly: TURN1_OK\n"
            )
            r1 = await openagentic_sdk.run(prompt=prompt1, options=opts)
            self.assertEqual((r1.final_text or "").strip(), "TURN1_OK")
            self.assertTrue(p.exists())

            events_path = root / "sessions" / session_id / "events.jsonl"
            self.assertTrue(events_path.exists())
            before_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())

            prompt2 = (
                "Step 1: Read ./a.txt.\n"
                "Step 2: Reply with exactly the token you saw.\n"
                "Do not guess.\n"
            )
            r2 = await openagentic_sdk.run(prompt=prompt2, options=opts)
            self.assertIn(token, (r2.final_text or ""))

            after_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())
            self.assertGreater(after_lines, before_lines)


if __name__ == "__main__":
    unittest.main()

