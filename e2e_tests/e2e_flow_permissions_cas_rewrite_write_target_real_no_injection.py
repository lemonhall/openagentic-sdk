from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.permissions.cas import PermissionResultAllow
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests._harness import make_options


class TestE2EFlowPermissionsCasRewriteWriteTargetRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_cas_can_rewrite_write_target_via_updated_input(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"CAS_REWRITE_{uuid.uuid4().hex}"
            a = root / "a.txt"
            b = root / "b.txt"

            async def can_use_tool(tool_name: str, tool_input: dict[str, object], _ctx) -> object:  # noqa: ANN001
                if tool_name != "Write":
                    return PermissionResultAllow()
                inp = dict(tool_input)
                inp["file_path"] = "./b.txt"
                inp["filePath"] = "./b.txt"
                return PermissionResultAllow(updated_input=inp)

            opts0 = make_options(root, allowed_tools=["Write"])
            gate = PermissionGate(permission_mode="bypass", can_use_tool=can_use_tool)
            opts = replace(opts0, permission_gate=gate, max_steps=12)

            for attempt in range(6):
                if a.exists():
                    a.unlink()
                if b.exists():
                    b.unlink()
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 1 completes.\n"
                    "Step 1: Call Write to write ./a.txt with this token (overwrite=true):\n"
                    f"{token}\n"
                    "Step 2: Call Read on ./b.txt.\n"
                    "After tools succeed, reply with exactly: CAS_REWRITE_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                opts2 = replace(opts, allowed_tools=["Write", "Read"])
                r = await openagentic_sdk.run(prompt=prompt, options=opts2)

                if (r.final_text or "").strip() != "CAS_REWRITE_OK":
                    continue
                if a.exists():
                    continue
                if not b.exists():
                    continue
                if token not in b.read_text(encoding="utf-8", errors="replace"):
                    continue
                return

            self.fail("CAS updated_input rewrite did not redirect Write target after 6 attempts")


if __name__ == "__main__":
    unittest.main()

