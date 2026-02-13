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


class TestE2EPermPromptDenyThenAllowWriteRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_mode_denies_first_write_allows_second_write(self) -> None:
        answers = iter(["no", "yes"])

        async def answer_mixed(_q: Any) -> str:
            try:
                return next(answers)
            except StopIteration:
                return "no"

        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"ALLOW_WRITE_{uuid.uuid4().hex}"
            p = root / "a.txt"

            for attempt in range(3):
                if p.exists():
                    p.unlink()
                opts0 = make_options(root, allowed_tools=["Write"])
                gate = PermissionGate(permission_mode="prompt", interactive=False, user_answerer=answer_mixed)
                opts = replace(opts0, permission_gate=gate, max_steps=12)
                prompt = (
                    "You are graded by permission behavior and disk state.\n"
                    "You MUST attempt the Write tool twice:\n"
                    "1) First attempt should be denied (answer will be 'no').\n"
                    "2) Second attempt should be allowed (answer will be 'yes').\n"
                    "Write input:\n"
                    "- file_path: ./a.txt\n"
                    f"- content: {token}\n"
                    "- overwrite: true\n"
                    "After the second attempt succeeds, reply with exactly: DENY_ALLOW_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                questions = [e for e in r.events if getattr(e, "type", None) == "user.question"]
                denied = any(
                    getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", None) == "PermissionDenied"
                    for e in r.events
                )
                allowed = any(
                    getattr(e, "type", None) == "tool.result" and getattr(e, "is_error", True) is False for e in r.events
                )
                text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                if len(questions) >= 2 and denied and allowed and token in text and (r.final_text or "").strip() == "DENY_ALLOW_OK":
                    return

            self.fail("prompt permission mode did not deny then allow Write after 3 attempts")


if __name__ == "__main__":
    unittest.main()

