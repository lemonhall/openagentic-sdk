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


class TestE2EFlowAskUserWithPermissionPromptWriteRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_ask_user_then_prompt_allow_write_then_read(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"ASK_PROMPT_{uuid.uuid4().hex}"
            p = root / "asked.txt"

            async def answerer(q: Any) -> str:
                prompt = getattr(q, "prompt", "") or ""
                if isinstance(prompt, str) and prompt.startswith("Allow tool"):
                    return "yes"
                return token

            for attempt in range(5):
                if p.exists():
                    p.unlink()
                opts0 = make_options(root, allowed_tools=["AskUserQuestion", "Write", "Read"])
                gate = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=answerer)
                opts = replace(opts0, permission_gate=gate, max_steps=25)
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 3 succeeds.\n"
                    "Step 1: Call AskUserQuestion exactly once to ask the user for the secret token.\n"
                    "Step 2: Call Write to write the returned token to ./asked.txt (overwrite=true).\n"
                    "Step 3: Call Read on ./asked.txt.\n"
                    "After tools succeed, reply with exactly: ASK_PROMPT_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_questions = [e for e in r.events if getattr(e, "type", None) == "user.question"]
                text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                if len(saw_questions) >= 2 and token in text and (r.final_text or "").strip() == "ASK_PROMPT_OK":
                    return

            self.fail("AskUserQuestion+prompt permission Write flow did not complete after 5 attempts")


if __name__ == "__main__":
    unittest.main()

