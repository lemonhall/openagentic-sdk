from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EFlowToolsEditOldMismatchRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_edit_old_mismatch_returns_valueerror_and_does_not_modify_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"EDIT_TOKEN_{uuid.uuid4().hex}"
            p = root / "a.txt"
            p.write_text(token, encoding="utf-8")

            opts0 = make_options(root, allowed_tools=["Edit"])
            opts = replace(opts0, max_steps=10)

            for attempt in range(6):
                p.write_text(token, encoding="utf-8")
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 1 completes.\n"
                    "Step 1: Call Edit on ./a.txt with old=NOT_PRESENT and new=SHOULD_NOT_APPLY.\n"
                    "Step 2: If the tool failed because old was not found, reply with exactly: EDIT_MISMATCH_OK\n"
                    "Do not attempt any other tools.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)

                errors = [
                    e
                    for e in r.events
                    if getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", "") == "ValueError"
                    and "old" in (getattr(e, "error_message", "") or "").lower()
                    and "not found" in (getattr(e, "error_message", "") or "").lower()
                ]
                still_token = p.read_text(encoding="utf-8", errors="replace") == token
                if errors and still_token and (r.final_text or "").strip() == "EDIT_MISMATCH_OK":
                    return

            self.fail("Edit old mismatch did not fail as expected after 6 attempts")


if __name__ == "__main__":
    unittest.main()

