from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EFlowListThenReadRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_list_then_read_specific_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"LIST_READ_{uuid.uuid4().hex}"
            (root / "docs").mkdir(parents=True, exist_ok=True)
            (root / "docs" / "note.txt").write_text(token + "\n", encoding="utf-8")

            for attempt in range(4):
                opts0 = make_options(root, allowed_tools=["List", "Read"])
                opts = replace(opts0, max_steps=18)
                prompt = (
                    "You are graded by tool evidence.\n"
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 2 succeeds.\n"
                    "Step 1: Call List on path='.'.\n"
                    "Step 2: Call Read on ./docs/note.txt.\n"
                    "After the Read tool result, reply with exactly the token you saw in the file.\n"
                    "Do not add any other text.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                used_list = any(getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "List" for e in r.events)
                if used_list and token in (r.final_text or ""):
                    return

            self.fail("model did not complete List→Read flow after 4 attempts")


if __name__ == "__main__":
    unittest.main()

