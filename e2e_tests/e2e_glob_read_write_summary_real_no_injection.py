from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EGlobReadWriteSummaryRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_glob_read_then_write_summary_persists_basenames(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            d = root / "d"
            d.mkdir()
            (d / "b.txt").write_text(f"B_{uuid.uuid4().hex}\n", encoding="utf-8")
            (d / "a.txt").write_text(f"A_{uuid.uuid4().hex}\n", encoding="utf-8")
            (d / "c.txt").write_text(f"C_{uuid.uuid4().hex}\n", encoding="utf-8")
            summary = root / "summary.txt"

            for attempt in range(3):
                if summary.exists():
                    summary.unlink()
                opts0 = make_options(root, allowed_tools=["Glob", "Read", "Write"])
                opts = replace(opts0, max_steps=18)
                prompt = (
                    "You are graded by the summary file on disk.\n"
                    "Step 1: Use Glob to list ./d/*.txt\n"
                    "Step 2: Read each matched file.\n"
                    "Step 3: Write ./summary.txt with EXACTLY these basenames, one per line, sorted lexicographically:\n"
                    "a.txt\nb.txt\nc.txt\n"
                    "Step 4: Read ./summary.txt to verify.\n"
                    "After verification, reply with exactly: SUMMARY_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                text = summary.read_text(encoding="utf-8", errors="replace") if summary.exists() else ""
                if text.strip() == "a.txt\nb.txt\nc.txt".strip() and (r.final_text or "").strip() == "SUMMARY_OK":
                    return

            self.fail("model did not complete Glob→Read→Write(summary) after 3 attempts")


if __name__ == "__main__":
    unittest.main()

