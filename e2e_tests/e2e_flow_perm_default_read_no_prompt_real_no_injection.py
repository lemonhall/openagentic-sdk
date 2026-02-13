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


class TestE2EFlowPermDefaultReadNoPromptRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_default_permission_read_does_not_prompt(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"SAFE_READ_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token + "\n", encoding="utf-8")

            async def answerer_should_not_be_called(_q: Any) -> str:
                raise AssertionError("default permission must not prompt for Read")

            gate = PermissionGate(permission_mode="default", interactive=False, user_answerer=answerer_should_not_be_called)
            opts0 = make_options(root, allowed_tools=["Read"])
            opts = replace(opts0, permission_gate=gate, max_steps=10)

            for attempt in range(4):
                prompt = (
                    "You MUST use tools.\n"
                    "Step 1: Call Read on ./a.txt.\n"
                    "Step 2: Reply with exactly the token you saw.\n"
                    "Do not add any other text.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                if any(getattr(e, "type", None) == "user.question" for e in r.events):
                    self.fail("unexpected user.question in default safe Read flow")
                if token in (r.final_text or ""):
                    return
            self.fail("default safe Read flow did not return token after 4 attempts")


if __name__ == "__main__":
    unittest.main()

