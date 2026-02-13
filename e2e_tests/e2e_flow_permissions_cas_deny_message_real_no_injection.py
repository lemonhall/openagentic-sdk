from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.permissions.cas import PermissionResultDeny
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests._harness import make_options


class TestE2EFlowPermissionsCasDenyMessageRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_cas_deny_produces_permission_denied_with_message(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"CAS_DENY_{uuid.uuid4().hex}"
            p = root / "deny.txt"
            deny_msg = "cas denied"

            async def can_use_tool(tool_name: str, _tool_input: dict[str, object], _ctx) -> object:  # noqa: ANN001
                if tool_name == "Write":
                    return PermissionResultDeny(message=deny_msg, interrupt=False)
                return PermissionResultDeny(message=deny_msg, interrupt=False)

            opts0 = make_options(root, allowed_tools=["Write"])
            gate = PermissionGate(permission_mode="bypass", can_use_tool=can_use_tool, interactive=False)
            opts = replace(opts0, permission_gate=gate, max_steps=10)

            for attempt in range(6):
                if p.exists():
                    p.unlink()
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 1 completes.\n"
                    "Step 1: Call Write to write ./deny.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "Step 2: If the tool was denied, reply with exactly: CAS_DENY_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)

                saw_question = any(getattr(e, "type", None) == "user.question" for e in r.events)
                denied = [
                    e
                    for e in r.events
                    if getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", "") == "PermissionDenied"
                    and deny_msg in (getattr(e, "error_message", "") or "")
                ]
                if not saw_question and denied and (r.final_text or "").strip() == "CAS_DENY_OK" and not p.exists():
                    return

            self.fail("CAS deny did not produce PermissionDenied with message after 6 attempts")


if __name__ == "__main__":
    unittest.main()

