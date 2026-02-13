from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2ESessionResumeReadAfterWriteRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_resume_session_can_read_written_artifact(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"RESUME_TOKEN_{uuid.uuid4().hex}"
            p = root / "resume.txt"

            opts0 = make_options(root, allowed_tools=["Write", "Read"])

            r1 = None
            for attempt in range(3):
                if p.exists():
                    p.unlink()
                opts1 = replace(opts0, max_steps=10)
                prompt1 = (
                    "You are graded by whether ./resume.txt exists on disk with the correct content.\n"
                    "Do not reply with any text until after the Write tool succeeds.\n"
                    "Step 1: Call the Write tool exactly once with:\n"
                    "- file_path: ./resume.txt\n"
                    f"- content: {token}\n"
                    "- overwrite: true\n"
                    "Step 2: Reply with exactly: TURN1_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r1 = await openagentic_sdk.run(prompt=prompt1, options=opts1)
                if r1.session_id and p.exists() and token in p.read_text(encoding="utf-8", errors="replace"):
                    break
            self.assertIsNotNone(r1)
            self.assertTrue(r1.session_id)
            self.assertTrue(p.exists())

            opts2 = replace(opts0, resume=r1.session_id, max_steps=10)
            prompt2 = (
                "Call Read on ./resume.txt and then reply with exactly the file content.\n"
                "Do not guess."
            )
            r2 = await openagentic_sdk.run(prompt=prompt2, options=opts2)
            self.assertIn(token, r2.final_text or "")


if __name__ == "__main__":
    unittest.main()
