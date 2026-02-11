from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EToolsGlobGrepEditSingleTargetRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_workflow_changes_only_matched_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"SINGLE_TARGET_{uuid.uuid4().hex}"
            d = root / "d"
            d.mkdir()
            target = d / "target.txt"
            other = d / "other.txt"

            for attempt in range(3):
                target.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")
                other.write_text("BEGIN\nPLACEHOLDERX\nEND\n", encoding="utf-8")

                opts0 = make_options(root, allowed_tools=["Glob", "Grep", "Read", "Edit"])
                opts = replace(opts0, max_steps=18)
                prompt = (
                    "You are graded by whether exactly one file changes on disk.\n"
                    "Step 1: Glob for *.txt under ./d\n"
                    "Step 2: Grep for the literal string PLACEHOLDER (not PLACEHOLDERX)\n"
                    "Step 3: Edit the matching file to replace PLACEHOLDER with this token: "
                    + token
                    + "\n"
                    "Step 4: Read to verify\n"
                    "Reply with exactly: SINGLE_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_edit = any(
                    getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Edit" for e in r.events
                )
                t_text = target.read_text(encoding="utf-8", errors="replace")
                o_text = other.read_text(encoding="utf-8", errors="replace")
                if (
                    saw_edit
                    and token in t_text
                    and token not in o_text
                    and "PLACEHOLDERX" in o_text
                    and (r.final_text or "").strip() == "SINGLE_OK"
                ):
                    return

            self.fail("model did not complete single-target edit workflow after 3 attempts")


if __name__ == "__main__":
    unittest.main()

