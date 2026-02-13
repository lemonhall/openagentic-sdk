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


class TestE2EFlowResumePromptPermissionDenyThenAllowWriteRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_resume_prompt_permission_denies_then_allows_write(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            token = f"RESUME_DENY_ALLOW_{uuid.uuid4().hex}"
            p = root / "a.txt"

            async def answer_no(q: Any) -> str:
                prompt = getattr(q, "prompt", "") or ""
                if isinstance(prompt, str) and prompt.startswith("Allow tool"):
                    return "no"
                return "no"

            async def answer_yes(q: Any) -> str:
                prompt = getattr(q, "prompt", "") or ""
                if isinstance(prompt, str) and prompt.startswith("Allow tool"):
                    return "yes"
                return "yes"

            opts0 = make_options(root, allowed_tools=["Write"])

            # Run 1: denied write, no side effects.
            gate1 = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=answer_no)
            for attempt in range(4):
                if p.exists():
                    p.unlink()
                opts1 = replace(opts0, resume=session_id, permission_gate=gate1, max_steps=10)
                prompt1 = (
                    "You MUST use tools.\n"
                    "Step 1: Call Write to write ./a.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "If Write is denied, do NOT retry. Reply with exactly: TURN1_DENIED\n"
                    f"(attempt={attempt + 1})\n"
                )
                r1 = await openagentic_sdk.run(prompt=prompt1, options=opts1)
                denied = any(
                    getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", None) == "PermissionDenied"
                    for e in r1.events
                )
                if denied and (r1.final_text or "").strip() == "TURN1_DENIED" and (not p.exists()):
                    break
            else:
                self.fail("run1 did not deny write and exit after 4 attempts")

            events_path = root / "sessions" / session_id / "events.jsonl"
            self.assertTrue(events_path.exists())
            before_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())

            # Run 2: allow write.
            gate2 = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=answer_yes)
            for attempt in range(4):
                opts2 = replace(opts0, resume=session_id, permission_gate=gate2, max_steps=12)
                prompt2 = (
                    "You MUST use tools.\n"
                    "Step 1: Call Write to write ./a.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "After the tool succeeds, reply with exactly: TURN2_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r2 = await openagentic_sdk.run(prompt=prompt2, options=opts2)
                ok = any(
                    getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", True) is False
                    for e in r2.events
                )
                text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                if ok and token in text and (r2.final_text or "").strip() == "TURN2_OK":
                    after_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines())
                    self.assertGreater(after_lines, before_lines)
                    return
            self.fail("run2 did not allow write after 4 attempts")


if __name__ == "__main__":
    unittest.main()

