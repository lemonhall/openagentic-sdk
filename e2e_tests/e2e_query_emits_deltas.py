from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EQueryEmitsDeltas(unittest.IsolatedAsyncioTestCase):
    async def test_query_emits_assistant_delta_events_when_enabled(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"E2E_QUERY_DELTA_OK_{uuid.uuid4().hex}"
            opts0 = make_options(root, allowed_tools=[])
            opts = replace(opts0, include_partial_messages=True, max_steps=10)

            saw_delta = False
            final_text = ""
            async for ev in openagentic_sdk.query(prompt=f"Reply with exactly: {token}", options=opts):
                if getattr(ev, "type", None) == "assistant.delta" and getattr(ev, "text_delta", ""):
                    saw_delta = True
                if getattr(ev, "type", None) == "result":
                    final_text = getattr(ev, "final_text", "") or ""

            self.assertTrue(saw_delta)
            self.assertIn(token, final_text)


if __name__ == "__main__":
    unittest.main()

