from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EToolsGlobGrepEditRoundtripRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_model_uses_glob_grep_then_edits_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"GG_EDIT_{uuid.uuid4().hex}"

            # Make a small tree; only one file contains PLACEHOLDER.
            (root / "d").mkdir()
            (root / "d" / "x.txt").write_text("noise\n", encoding="utf-8")
            target = root / "d" / "target.txt"

            for attempt in range(3):
                target.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")
                opts0 = make_options(root, allowed_tools=["Glob", "Grep", "Read", "Edit"])
                opts = replace(opts0, max_steps=18)
                prompt = (
                    "You are graded by whether the correct file changes on disk.\n"
                    "Step 1: Use Glob to find *.txt under ./d.\n"
                    "Step 2: Use Grep to locate which file contains the literal string PLACEHOLDER.\n"
                    "Step 3: Use Edit to replace PLACEHOLDER with this exact token: "
                    + token
                    + "\n"
                    "Step 4: Use Read to verify.\n"
                    "After verification, reply with exactly: GG_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_edit = any(
                    getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Edit" for e in r.events
                )
                text = target.read_text(encoding="utf-8", errors="replace")
                if saw_edit and token in text and (r.final_text or "").strip() == "GG_OK":
                    return

            self.fail("model did not complete Glob/Grep→Edit workflow after 3 attempts")


if __name__ == "__main__":
    unittest.main()

