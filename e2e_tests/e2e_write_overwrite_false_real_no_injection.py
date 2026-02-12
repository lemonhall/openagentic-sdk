from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EWriteOverwriteFalseRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_write_overwrite_false_errors_and_keeps_original(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            p = root / "a.txt"
            original = f"ORIG_{uuid.uuid4().hex}"
            token = f"NEW_{uuid.uuid4().hex}"

            for attempt in range(3):
                p.write_text(original, encoding="utf-8")
                opts0 = make_options(root, allowed_tools=["Write", "Read"])
                opts = replace(opts0, max_steps=10)
                prompt = (
                    "You are graded by tool behavior and disk state.\n"
                    "Step 1: Call Write on ./a.txt with overwrite=false and content set to the NEW token.\n"
                    f"NEW token: {token}\n"
                    "This MUST error because the file already exists.\n"
                    "Step 2: Call Read on ./a.txt and confirm it still contains the ORIGINAL content.\n"
                    "Step 3: Reply with exactly: OVERWRITE_FALSE_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_write_error = any(
                    getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and str(getattr(e, "error_message", "") or "").startswith("Write:")
                    for e in r.events
                )
                text = p.read_text(encoding="utf-8", errors="replace")
                if saw_write_error and text == original and (r.final_text or "").strip() == "OVERWRITE_FALSE_OK":
                    return

            self.fail("model did not exercise overwrite=false error and keep file unchanged after 3 attempts")


if __name__ == "__main__":
    unittest.main()

