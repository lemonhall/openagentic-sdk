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


class TestE2EFlowPermissionPromptAllowWriteRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_permission_allows_write_and_emits_question(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"PROMPT_OK_{uuid.uuid4().hex}"
            p = root / "a.txt"

            async def answer_yes(_q: Any) -> str:
                return "yes"

            for attempt in range(4):
                if p.exists():
                    p.unlink()
                opts0 = make_options(root, allowed_tools=["Write", "Read"])
                gate = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=answer_yes)
                opts = replace(opts0, permission_gate=gate, max_steps=16)
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 2 succeeds.\n"
                    "Step 1: Call Write to write ./a.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "Step 2: Call Read on ./a.txt.\n"
                    "After tools succeed, reply with exactly: PERM_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                questions = [e for e in r.events if getattr(e, "type", None) == "user.question"]
                text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                if len(questions) >= 1 and token in text and (r.final_text or "").strip() == "PERM_OK":
                    return

            self.fail("prompt permission did not allow Write and complete flow after 4 attempts")


if __name__ == "__main__":
    unittest.main()

