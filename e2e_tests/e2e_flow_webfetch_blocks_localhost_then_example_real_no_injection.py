from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EFlowWebFetchBlocksLocalhostThenExampleRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_webfetch_blocks_localhost_then_allows_example(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            for attempt in range(4):
                opts0 = make_options(root, allowed_tools=["WebFetch"])
                opts = replace(opts0, max_steps=18)
                prompt = (
                    "You are graded by security behavior.\n"
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 2 succeeds.\n"
                    "Step 1: Call WebFetch on http://localhost/ (this MUST error / be blocked).\n"
                    "Step 2: Call WebFetch on https://example.com/ (this MUST succeed).\n"
                    "After tools finish, reply with exactly: WEBFETCH_BLOCK_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_block = any(
                    getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", None) == "ValueError"
                    and "blocked" in str(getattr(e, "error_message", "") or "").lower()
                    for e in r.events
                )
                saw_example = any(
                    getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is False
                    and isinstance(getattr(e, "output", None), dict)
                    and "Example Domain" in str(getattr(e, "output", {}).get("text") or "")
                    for e in r.events
                )
                if saw_block and saw_example and (r.final_text or "").strip() == "WEBFETCH_BLOCK_OK":
                    return

            self.fail("model did not demonstrate WebFetch blocked localhost then fetched example.com after 4 attempts")


if __name__ == "__main__":
    unittest.main()

