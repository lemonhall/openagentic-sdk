from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EFlowResumeWriteThenGrepRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_resume_across_runs_and_grep_finds_token(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            token = f"RESUME_GREP_{uuid.uuid4().hex}"

            opts0 = make_options(root, allowed_tools=["Write", "Grep", "Read"])
            opts1 = replace(opts0, resume=session_id, max_steps=14)
            prompt1 = (
                "You MUST use tools.\n"
                "Step 1: Write ./a.txt with content containing this token:\n"
                f"{token}\n"
                "Step 2: Reply with exactly: TURN1_OK\n"
            )
            r1 = await openagentic_sdk.run(prompt=prompt1, options=opts1)
            self.assertEqual((r1.final_text or "").strip(), "TURN1_OK")

            events_path = root / "sessions" / session_id / "events.jsonl"
            self.assertTrue(events_path.exists())
            before_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())

            for attempt in range(4):
                opts2 = replace(opts0, resume=session_id, max_steps=14)
                prompt2 = (
                    "You MUST use tools.\n"
                    "Step 1: Use Grep to search for the token in the project root (root='.', file_glob='*.txt', mode='content').\n"
                    "Step 2: Read ./a.txt.\n"
                    "Step 3: Reply with exactly the token you saw.\n"
                    "Do not add any other text.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r2 = await openagentic_sdk.run(prompt=prompt2, options=opts2)
                used_grep = any(getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Grep" for e in r2.events)
                if used_grep and token in (r2.final_text or ""):
                    after_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())
                    self.assertGreater(after_lines, before_lines)
                    return

            self.fail("model did not Grep+Read and return the token after resume")


if __name__ == "__main__":
    unittest.main()

