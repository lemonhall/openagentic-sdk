from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EToolsWriteRoundtripRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_model_writes_then_reads_file_on_disk(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"WRITE_TOKEN_{uuid.uuid4().hex}"
            p = root / "out.txt"

            for attempt in range(3):
                if p.exists():
                    p.unlink()
                opts0 = make_options(root, allowed_tools=["Write", "Read"])
                opts = replace(opts0, max_steps=12)
                prompt = (
                    "You are graded by whether the file exists on disk with the correct content.\n"
                    "Do not reply with any text until after Step 2 succeeds.\n"
                    "Step 1: Call the Write tool with:\n"
                    "- file_path: ./out.txt\n"
                    f"- content: {token}\n"
                    "- overwrite: true\n"
                    "Step 2: Call the Read tool on ./out.txt.\n"
                    "After receiving the tool result, reply with exactly: WRITE_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_write = any(
                    getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Write" for e in r.events
                )
                saw_read = any(
                    getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Read" for e in r.events
                )
                text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                if saw_write and saw_read and token in text and (r.final_text or "").strip() == "WRITE_OK":
                    return

            self.fail("model did not complete Write→Read roundtrip after 3 attempts")


if __name__ == "__main__":
    unittest.main()

