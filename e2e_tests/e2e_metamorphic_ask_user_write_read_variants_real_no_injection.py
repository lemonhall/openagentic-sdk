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


class TestE2EMetamorphicAskUserWriteReadVariantsRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_variants_preserve_ask_user_write_read_evidence(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"MR_ASK_TOKEN_{uuid.uuid4().hex}"
            p = root / "asked.txt"

            async def answerer(_q: Any) -> str:
                return token

            variants = [
                (
                    "You are graded by disk state and tool evidence.\n"
                    "Do not guess.\n"
                    "Step 1: Call AskUserQuestion exactly once to ask the user for the secret token.\n"
                    "Step 2: Use the returned tool answer to Write it to ./asked.txt (overwrite=true).\n"
                    "Step 3: Read ./asked.txt.\n"
                ),
                (
                    "We are testing a human-in-the-loop pipeline.\n"
                    "First ask the user (AskUserQuestion) for the token, then persist it to disk, then read it back.\n"
                    "Use tools; do not fabricate content.\n"
                    "Write target: ./asked.txt\n"
                ),
            ]

            for idx, prompt in enumerate(variants, start=1):
                for attempt in range(5):
                    if p.exists():
                        p.unlink()

                    opts0 = make_options(root, allowed_tools=["AskUserQuestion", "Write", "Read"])
                    gate = PermissionGate(permission_mode="bypass", interactive=False, user_answerer=answerer)
                    opts = replace(opts0, permission_gate=gate, max_steps=25)

                    r = await openagentic_sdk.run(prompt=f"[variant={idx} attempt={attempt + 1}]\n{prompt}", options=opts)

                    saw_question = any(getattr(e, "type", None) == "user.question" for e in r.events)
                    ask_ids = [
                        getattr(e, "tool_use_id", None)
                        for e in r.events
                        if getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "AskUserQuestion"
                    ]
                    write_ids = [
                        getattr(e, "tool_use_id", None)
                        for e in r.events
                        if getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Write"
                    ]
                    read_ids = [
                        getattr(e, "tool_use_id", None)
                        for e in r.events
                        if getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Read"
                    ]

                    saw_ask_ok = any(
                        getattr(e, "type", None) == "tool.result"
                        and getattr(e, "tool_use_id", None) in ask_ids
                        and getattr(e, "is_error", True) is False
                        for e in r.events
                    )
                    saw_write_ok = any(
                        getattr(e, "type", None) == "tool.result"
                        and getattr(e, "tool_use_id", None) in write_ids
                        and getattr(e, "is_error", True) is False
                        for e in r.events
                    )
                    saw_read_ok = any(
                        getattr(e, "type", None) == "tool.result"
                        and getattr(e, "tool_use_id", None) in read_ids
                        and getattr(e, "is_error", True) is False
                        for e in r.events
                    )
                    text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""

                    # Metamorphic relation: prompt variants should preserve the same evidence.
                    if saw_question and saw_ask_ok and saw_write_ok and saw_read_ok and token in text:
                        break
                else:
                    self.fail(f"variant {idx} did not satisfy ask→write→read evidence after 5 attempts")


if __name__ == "__main__":
    unittest.main()
