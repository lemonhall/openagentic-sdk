from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EReadInvalidOffsetRecoverRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_read_invalid_offset_errors_then_recovery_read_succeeds(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"READ_OK_{uuid.uuid4().hex}"
            p = root / "a.txt"
            p.write_text(token + "\n", encoding="utf-8")

            for attempt in range(3):
                opts0 = make_options(root, allowed_tools=["Read"])
                opts = replace(opts0, max_steps=12)
                prompt = (
                    "You are graded by tool behavior and correctness.\n"
                    "Do not guess.\n"
                    "Step 1: Call Read on ./a.txt with offset=-1 and limit=1. This MUST fail.\n"
                    "Step 2: Call Read on ./a.txt with offset=1 and limit=1. This MUST succeed.\n"
                    "Step 3: Reply with exactly the token you saw.\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_error = any(
                    getattr(e, "type", None) == "tool.result" and getattr(e, "is_error", False) is True for e in r.events
                )
                saw_ok = any(
                    getattr(e, "type", None) == "tool.result" and getattr(e, "is_error", True) is False for e in r.events
                )
                if saw_error and saw_ok and token in (r.final_text or ""):
                    return

            self.fail("model did not produce an invalid-offset Read error then recover with a valid Read after 3 attempts")


if __name__ == "__main__":
    unittest.main()

