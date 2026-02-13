from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EToolLoopRecoverReadMissingRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_read_missing_then_write_then_read_succeeds(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"RECOVER_TOKEN_{uuid.uuid4().hex}"
            p = root / "missing.txt"

            for attempt in range(3):
                if p.exists():
                    p.unlink()
                opts0 = make_options(root, allowed_tools=["Read", "Write"])
                opts = replace(opts0, max_steps=14)
                prompt = (
                    "You are graded by tool behavior and disk state.\n"
                    "Do not reply with any text until after Step 3 succeeds.\n"
                    "Step 1: Call Read on ./missing.txt (it does not exist). You MUST observe the error.\n"
                    "Step 2: Call Write with:\n"
                    "- file_path: ./missing.txt\n"
                    f"- content: {token}\n"
                    "- overwrite: true\n"
                    "Step 3: Call Read on ./missing.txt.\n"
                    "After receiving tool results, reply with exactly: RECOVER_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_write = any(
                    getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Write" for e in r.events
                )
                saw_read_error = any(
                    getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", None) != "PermissionDenied"
                    for e in r.events
                )
                text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                if saw_write and saw_read_error and token in text and (r.final_text or "").strip() == "RECOVER_OK":
                    return

            self.fail("model did not recover from missing Read and complete Write→Read after 3 attempts")


if __name__ == "__main__":
    unittest.main()

