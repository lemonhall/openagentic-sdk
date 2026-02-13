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


class TestE2EPermCallbackDenyEscapeWriteRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_callback_denies_escape_write_allows_in_project(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"CB_OK_{uuid.uuid4().hex}"
            escape = root.parent / "escape.txt"
            ok_p = root / "ok.txt"

            async def approver(tool_name: str, tool_input: Mapping[str, Any], _context: Mapping[str, Any]) -> bool:
                if tool_name != "Write":
                    return True
                fp = tool_input.get("file_path") or tool_input.get("filePath") or ""
                s = str(fp).strip().replace("\\", "/")
                # Deny any parent-dir traversal attempt regardless of slash flavor.
                return ".." not in [seg for seg in s.split("/") if seg]

            for attempt in range(5):
                if escape.exists():
                    escape.unlink()
                if ok_p.exists():
                    ok_p.unlink()
                opts0 = make_options(root, allowed_tools=["Write"])
                gate = PermissionGate(permission_mode="callback", approver=approver)
                opts = replace(opts0, permission_gate=gate, max_steps=18)
                prompt = (
                    "You are graded by permission behavior and disk state.\n"
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 2 succeeds.\n"
                    "Step 1: Call Write with EXACTLY this input (this MUST be denied with PermissionDenied):\n"
                    "{\n"
                    '  \"file_path\": \"../escape.txt\",\n'
                    '  \"content\": \"ESCAPE\",\n'
                    '  \"overwrite\": true\n'
                    "}\n"
                    "Step 2: Call Write with EXACTLY this input (this MUST succeed):\n"
                    "{\n"
                    '  \"file_path\": \"./ok.txt\",\n'
                    f'  \"content\": \"{token}\",\n'
                    '  \"overwrite\": true\n'
                    "}\n"
                    "After Step 2 succeeds, reply with exactly: CB_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_escape_use = any(
                    getattr(e, "type", None) == "tool.use"
                    and getattr(e, "name", None) == "Write"
                    and isinstance(getattr(e, "input", None), dict)
                    and "../escape.txt" in str(getattr(e, "input", {}).get("file_path") or getattr(e, "input", {}).get("filePath") or "")
                    for e in r.events
                )
                denied = any(
                    getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", None) == "PermissionDenied"
                    for e in r.events
                )
                ok_text = ok_p.read_text(encoding="utf-8", errors="replace") if ok_p.exists() else ""
                if saw_escape_use and denied and (not escape.exists()) and token in ok_text and (r.final_text or "").strip() == "CB_OK":
                    return

            self.fail("callback permission gate did not deny escape Write and allow in-project Write after 5 attempts")


if __name__ == "__main__":
    unittest.main()
