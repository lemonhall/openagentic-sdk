from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EFlowReadOffsetLimitNumberedRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_read_offset_limit_returns_numbered_lines(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            p = root / "lines.txt"
            p.write_text("L1\nL2\nL3\nL4\n", encoding="utf-8")

            for attempt in range(4):
                opts0 = make_options(root, allowed_tools=["Read"])
                opts = replace(opts0, max_steps=10)
                prompt = (
                    "You MUST use tools.\n"
                    "Step 1: Call Read on ./lines.txt with offset=2 and limit=2.\n"
                    "Step 2: Reply with exactly the content returned by Read (the 'content' field), unchanged.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                # Expect line-numbered output including '2: L2' and '3: L3'
                if "2: L2" in (r.final_text or "") and "3: L3" in (r.final_text or ""):
                    return

            self.fail("Read offset/limit numbered content was not returned after 4 attempts")


if __name__ == "__main__":
    unittest.main()

