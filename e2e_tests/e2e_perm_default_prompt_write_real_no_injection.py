from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import openagentic_sdk
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests._harness import make_options


class TestE2EPermDefaultPromptWriteRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_default_mode_prompts_for_write_then_allows(self) -> None:
        async def answer_yes(_q: Any) -> str:
            return "yes"

        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"PERM_WRITE_{uuid.uuid4().hex}"
            p = root / "w.txt"

            for attempt in range(3):
                if p.exists():
                    p.unlink()
                opts0 = make_options(root, allowed_tools=["Write"])
                gate = PermissionGate(permission_mode="default", interactive=False, user_answerer=answer_yes)
                opts = replace(opts0, permission_gate=gate, max_steps=10)
                prompt = (
                    "You are graded by whether the file exists on disk.\n"
                    "Step 1: Call Write with:\n"
                    "- file_path: ./w.txt\n"
                    f"- content: {token}\n"
                    "- overwrite: true\n"
                    "Step 2: Reply with exactly: PERM_WRITE_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_question = any(getattr(e, "type", None) == "user.question" for e in r.events)
                text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                if saw_question and token in text and (r.final_text or "").strip() == "PERM_WRITE_OK":
                    return

            self.fail("default permission mode did not prompt+allow Write after 3 attempts")


if __name__ == "__main__":
    unittest.main()

