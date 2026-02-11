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


class TestE2EAskUserWriteReadPipelineRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_ask_user_then_write_then_read(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"ASK_TOKEN_{uuid.uuid4().hex}"
            p = root / "asked.txt"

            async def answerer(_q: Any) -> str:
                return token

            for attempt in range(3):
                if p.exists():
                    p.unlink()
                opts0 = make_options(root, allowed_tools=["AskUserQuestion", "Write", "Read"])
                gate = PermissionGate(permission_mode="bypass", interactive=False, user_answerer=answerer)
                opts = replace(opts0, permission_gate=gate, max_steps=18)
                prompt = (
                    "You are graded by whether the token is written to disk.\n"
                    "Step 1: Call AskUserQuestion to ask the user for the secret token.\n"
                    "Step 2: Call Write to write the exact token to ./asked.txt (overwrite=true).\n"
                    "Step 3: Call Read on ./asked.txt.\n"
                    "After tool success, reply with exactly: ASK_PIPE_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_question = any(getattr(e, "type", None) == "user.question" for e in r.events)
                text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                if saw_question and token in text and (r.final_text or "").strip() == "ASK_PIPE_OK":
                    return

            self.fail("model did not complete AskUserQuestion→Write→Read pipeline after 3 attempts")


if __name__ == "__main__":
    unittest.main()

