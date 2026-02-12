from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EFlowWebFetchExampleDomainRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_webfetch_example_domain_contains_expected_text(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            for attempt in range(4):
                opts0 = make_options(root, allowed_tools=["WebFetch"])
                opts = replace(opts0, max_steps=12)
                prompt = (
                    "You are graded by tool output.\n"
                    "You MUST use tools.\n"
                    "Step 1: Call WebFetch on https://example.com/\n"
                    "Step 2: Reply with exactly: EXAMPLE_DOMAIN_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                results = [e for e in r.events if getattr(e, "type", None) == "tool.result" and getattr(e, "is_error", False) is False]
                ok_text = False
                for e in results:
                    out = getattr(e, "output", None)
                    if isinstance(out, dict) and "text" in out and isinstance(out["text"], str) and "Example Domain" in out["text"]:
                        ok_text = True
                        break
                if ok_text and (r.final_text or "").strip() == "EXAMPLE_DOMAIN_OK":
                    return

            self.fail("model did not WebFetch example.com successfully after 4 attempts")


if __name__ == "__main__":
    unittest.main()

