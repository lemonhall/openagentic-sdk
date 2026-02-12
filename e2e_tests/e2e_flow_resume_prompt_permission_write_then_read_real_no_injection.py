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


class TestE2EFlowResumePromptPermissionWriteThenReadRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_resume_prompt_permission_write_then_read(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            token = f"RESUME_PROMPT_OK_{uuid.uuid4().hex}"
            p = root / "a.txt"

            async def answer_yes(q: Any) -> str:
                prompt = getattr(q, "prompt", "") or ""
                if isinstance(prompt, str) and prompt.startswith("Allow tool"):
                    return "yes"
                return "yes"

            gate = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=answer_yes)
            opts0 = make_options(root, allowed_tools=["Write", "Read"])

            # Run 1: Write then Read under prompt permission.
            for attempt in range(4):
                if p.exists():
                    p.unlink()
                opts1 = replace(opts0, resume=session_id, permission_gate=gate, max_steps=18)
                prompt1 = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 2 succeeds.\n"
                    "Step 1: Call Write to write ./a.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "Step 2: Call Read on ./a.txt.\n"
                    "After tools succeed, reply with exactly: TURN1_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r1 = await openagentic_sdk.run(prompt=prompt1, options=opts1)
                questions = [e for e in r1.events if getattr(e, "type", None) == "user.question"]
                text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                if len(questions) >= 2 and token in text and (r1.final_text or "").strip() == "TURN1_OK":
                    break
            else:
                self.fail("run1 did not complete under prompt permission after 4 attempts")

            events_path = root / "sessions" / session_id / "events.jsonl"
            self.assertTrue(events_path.exists())
            before_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())

            # Run 2: Read and return token.
            for attempt in range(4):
                opts2 = replace(opts0, resume=session_id, permission_gate=gate, max_steps=12)
                prompt2 = (
                    "You MUST use tools.\n"
                    "Step 1: Call Read on ./a.txt.\n"
                    "Step 2: Reply with exactly the token you saw.\n"
                    "Do not add any other text.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r2 = await openagentic_sdk.run(prompt=prompt2, options=opts2)
                if token in (r2.final_text or ""):
                    after_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())
                    self.assertGreater(after_lines, before_lines)
                    text2 = events_path.read_text(encoding="utf-8", errors="replace")
                    self.assertIn('"type":"user.question"', text2)
                    return

            self.fail("run2 did not read and return token after 4 attempts")


if __name__ == "__main__":
    unittest.main()

