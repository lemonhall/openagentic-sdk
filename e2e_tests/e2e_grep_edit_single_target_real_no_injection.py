from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EGrepEditSingleTargetRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_grep_then_edit_only_matched_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"GREP_EDIT_{uuid.uuid4().hex}"
            (root / "d").mkdir()
            target = root / "d" / "target.txt"
            other = root / "d" / "other.txt"

            for attempt in range(3):
                target.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")
                other.write_text("BEGIN\nNO_MATCH\nEND\n", encoding="utf-8")
                opts0 = make_options(root, allowed_tools=["Grep", "Edit", "Read"])
                opts = replace(opts0, max_steps=16)
                prompt = (
                    "You are graded by whether only the matched file changes on disk.\n"
                    "Step 1: Use Grep to locate which file under ./d contains the literal string PLACEHOLDER.\n"
                    "Step 2: Use Edit to replace PLACEHOLDER with this exact token: "
                    + token
                    + "\n"
                    "Step 3: Use Read to verify the token is present in that file.\n"
                    "After verification, reply with exactly: GREP_EDIT_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                t_text = target.read_text(encoding="utf-8", errors="replace")
                o_text = other.read_text(encoding="utf-8", errors="replace")
                if token in t_text and token not in o_text and (r.final_text or "").strip() == "GREP_EDIT_OK":
                    return

            self.fail("model did not complete Grep→Edit single-target workflow after 3 attempts")


if __name__ == "__main__":
    unittest.main()

