from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EToolLoopRecoverEditOldNotFoundRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_edit_old_not_found_then_retry_edit_succeeds(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"EDIT_RECOVER_{uuid.uuid4().hex}"
            p = root / "a.txt"

            for attempt in range(3):
                p.write_text("BEGIN\nHELLO\nEND\n", encoding="utf-8")
                opts0 = make_options(root, allowed_tools=["Edit", "Read"])
                opts = replace(opts0, max_steps=14)
                prompt = (
                    "You are graded by tool behavior and disk state.\n"
                    "Do not reply with any text until after Step 3 succeeds.\n"
                    "Step 1: Call Edit on ./a.txt with:\n"
                    "- old: MISSING_OLD\n"
                    f"- new: {token}\n"
                    "- count: 1\n"
                    "This MUST fail because old text is not in the file.\n"
                    "Step 2: Call Read on ./a.txt.\n"
                    "Step 3: Call Edit on ./a.txt to replace HELLO with the token.\n"
                    "After verification, reply with exactly: EDIT_RECOVER_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_edit_error = any(
                    getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and str(getattr(e, "error_message", "") or "").startswith("Edit:")
                    for e in r.events
                )
                text = p.read_text(encoding="utf-8", errors="replace")
                if saw_edit_error and token in text and (r.final_text or "").strip() == "EDIT_RECOVER_OK":
                    return

            self.fail("model did not recover from Edit old-not-found and apply a successful Edit after 3 attempts")


if __name__ == "__main__":
    unittest.main()

