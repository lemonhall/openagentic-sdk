from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EFlowGlobGrepEditReadRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_glob_grep_then_edit_then_read(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            d = root / "d"
            d.mkdir(parents=True, exist_ok=True)
            token = f"FLOW_GG_{uuid.uuid4().hex}"
            (d / "a.txt").write_text("nothing\n", encoding="utf-8")
            (d / "target.txt").write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")
            (d / "b.md").write_text("PLACEHOLDER\n", encoding="utf-8")

            target = d / "target.txt"

            for attempt in range(4):
                target.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")
                opts0 = make_options(root, allowed_tools=["Glob", "Grep", "Edit", "Read"])
                opts = replace(opts0, max_steps=25)
                prompt = (
                    "You are graded by tool evidence and disk state.\n"
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 4 succeeds.\n"
                    "Step 1: Call Glob with pattern='*.txt' and root='./d'.\n"
                    "Step 2: Call Grep with root='./d', file_glob='*.txt', query='PLACEHOLDER', mode='content'.\n"
                    "Step 3: Call Edit exactly once on ./d/target.txt to replace PLACEHOLDER with this token:\n"
                    f"{token}\n"
                    "Step 4: Call Read on ./d/target.txt.\n"
                    "After the tools succeed, reply with exactly: FLOW_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                used_glob = any(getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Glob" for e in r.events)
                used_grep = any(getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Grep" for e in r.events)
                used_edit = any(getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Edit" for e in r.events)
                text = target.read_text(encoding="utf-8", errors="replace")
                if used_glob and used_grep and used_edit and token in text and (r.final_text or "").strip() == "FLOW_OK":
                    return

            self.fail("model did not complete Glob→Grep→Edit→Read flow after 4 attempts")


if __name__ == "__main__":
    unittest.main()

