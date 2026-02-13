from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EFlowToolsReadMissingFileRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_read_missing_file_returns_filenotfounderror(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            missing = root / "missing.txt"

            opts0 = make_options(root, allowed_tools=["Read"])
            opts = replace(opts0, max_steps=10)

            for attempt in range(6):
                if missing.exists():
                    missing.unlink()
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 1 completes.\n"
                    "Step 1: Call Read on ./missing.txt.\n"
                    "Step 2: If the tool failed because the file does not exist, reply with exactly: READ_MISSING_OK\n"
                    "Do not attempt any other tools.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)

                errors = [
                    e
                    for e in r.events
                    if getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", "") == "FileNotFoundError"
                ]
                if errors and (r.final_text or "").strip() == "READ_MISSING_OK" and not missing.exists():
                    return

            self.fail("Read missing file did not produce FileNotFoundError after 6 attempts")


if __name__ == "__main__":
    unittest.main()

