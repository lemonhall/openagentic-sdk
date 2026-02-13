from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EMetamorphicEditVariantsRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_variants_preserve_edit_evidence(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"MR_EDIT_TOKEN_{uuid.uuid4().hex}"
            p = root / "a.txt"

            variants = [
                (
                    "You are graded by tool evidence and disk state.\n"
                    "Do not reply with any text until after the Edit tool succeeds.\n"
                    "Step 1: Read ./a.txt\n"
                    "Step 2: Edit ./a.txt to replace PLACEHOLDER with this exact token: "
                    + token
                    + "\n"
                ),
                (
                    "Change the file on disk using tools.\n"
                    "Replace the literal string PLACEHOLDER in ./a.txt with: "
                    + token
                    + "\n"
                    "Use Edit (count=1). You may Read first if needed.\n"
                ),
            ]

            for idx, prompt in enumerate(variants, start=1):
                for attempt in range(3):
                    p.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")
                    opts0 = make_options(root, allowed_tools=["Read", "Edit"])
                    opts = replace(opts0, max_steps=16)

                    r = await openagentic_sdk.run(prompt=f"[variant={idx} attempt={attempt + 1}]\n{prompt}", options=opts)

                    edit_uses = [
                        e for e in r.events if getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Edit"
                    ]
                    edit_id = getattr(edit_uses[-1], "tool_use_id", None) if edit_uses else None
                    saw_edit_ok = bool(
                        edit_id
                        and any(
                            getattr(e, "type", None) == "tool.result"
                            and getattr(e, "tool_use_id", None) == edit_id
                            and getattr(e, "is_error", True) is False
                            for e in r.events
                        )
                    )
                    text = p.read_text(encoding="utf-8", errors="replace")

                    # Metamorphic relation: variants preserve the same hard evidence.
                    if saw_edit_ok and token in text:
                        break
                else:
                    self.fail(f"variant {idx} did not satisfy edit evidence after 3 attempts")


if __name__ == "__main__":
    unittest.main()

