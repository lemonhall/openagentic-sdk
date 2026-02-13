from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import openagentic_sdk
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests._harness import make_options


class TestE2EFlowPermissionsCallbackApproverRaisesDeniesRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_callback_approver_raises_denies_safely(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"CALLBACK_RAISE_{uuid.uuid4().hex}"
            p = root / "callback_raise.txt"

            async def approver_raises(_tool_name: str, _tool_input: Mapping[str, Any], _context: Mapping[str, Any]) -> bool:
                raise RuntimeError("approver exploded")

            opts0 = make_options(root, allowed_tools=["Write"])
            gate = PermissionGate(permission_mode="callback", approver=approver_raises, interactive=False)
            opts = replace(opts0, permission_gate=gate, max_steps=12)

            for attempt in range(6):
                if p.exists():
                    p.unlink()
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 1 completes.\n"
                    "Step 1: Call Write to write ./callback_raise.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "Step 2: If the permission callback errored and the write was denied, reply with exactly: CALLBACK_DENY_OK\n"
                    "Do not attempt any other tools.\n"
                    f"(attempt={attempt + 1})\n"
                )

                # This run should not throw; it should convert callback failure into a clean denial.
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                denied = [
                    e
                    for e in r.events
                    if getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", "") == "PermissionDenied"
                ]
                if denied and (r.final_text or "").strip() == "CALLBACK_DENY_OK" and not p.exists():
                    return

            self.fail("callback approver exception did not result in safe PermissionDenied after 6 attempts")


if __name__ == "__main__":
    unittest.main()

