from __future__ import annotations

import json
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import openagentic_sdk
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests._harness import make_options


class TestE2ESessionsResumePermissionPromptWriteThenReadRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_resume_appends_events_and_can_read_after_permission_gated_write(self) -> None:
        async def answer_yes(_q: Any) -> str:
            return "yes"

        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            token = f"RESUME_PERM_{uuid.uuid4().hex}"
            p = root / "w.txt"

            # Run 1: permission prompt + Write.
            for attempt in range(3):
                if p.exists():
                    p.unlink()

                opts0 = make_options(root, allowed_tools=["Write"])
                gate = PermissionGate(permission_mode="default", interactive=False, user_answerer=answer_yes)
                opts1 = replace(opts0, permission_gate=gate, resume=session_id, max_steps=12)
                prompt1 = (
                    "You are graded by whether events persist to disk and resume works.\n"
                    "Step 1: Call Write with:\n"
                    "- file_path: ./w.txt\n"
                    f"- content: {token}\n"
                    "- overwrite: true\n"
                    "Step 2: Reply with exactly: TURN1_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r1 = await openagentic_sdk.run(prompt=prompt1, options=opts1)
                saw_question = any(getattr(e, "type", None) == "user.question" for e in r1.events)
                text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                if saw_question and token in text and (r1.final_text or "").strip() == "TURN1_OK":
                    break
            else:
                self.fail("permission-gated Write did not prompt+allow after 3 attempts")

            events_path = root / "sessions" / session_id / "events.jsonl"
            self.assertTrue(events_path.exists(), f"events.jsonl not found at: {events_path}")

            before_lines = [ln for ln in events_path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
            types: list[str] = []
            for raw in before_lines:
                try:
                    obj = json.loads(raw)
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(obj, dict) and isinstance(obj.get("type"), str):
                    types.append(obj["type"])

            self.assertIn("user.question", types, "permission prompt event not persisted to events.jsonl")

            # Run 2: resume same session and Read back the token.
            opts2_0 = make_options(root, allowed_tools=["Read"])
            opts2 = replace(opts2_0, resume=session_id, max_steps=8)
            prompt2 = (
                "Step 1: Call Read on ./w.txt.\n"
                "Step 2: Reply with exactly the content you saw.\n"
                "Do not guess.\n"
            )
            r2 = await openagentic_sdk.run(prompt=prompt2, options=opts2)
            self.assertIn(token, (r2.final_text or ""))

            after_lines = [ln for ln in events_path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
            self.assertGreater(len(after_lines), len(before_lines))


if __name__ == "__main__":
    unittest.main()

