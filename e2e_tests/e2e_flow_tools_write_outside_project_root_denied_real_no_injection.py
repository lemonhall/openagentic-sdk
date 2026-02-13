from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EFlowToolsWriteOutsideProjectRootDeniedRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_write_outside_project_root_is_denied(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            escape = root.parent / f"escape_{uuid.uuid4().hex}.txt"
            token = f"ESCAPE_{uuid.uuid4().hex}"

            opts0 = make_options(root, allowed_tools=["Write"])
            opts = replace(opts0, max_steps=10)

            for attempt in range(6):
                if escape.exists():
                    try:
                        escape.unlink()
                    except Exception:  # noqa: BLE001
                        pass
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 1 completes.\n"
                    "Step 1: Call Write to write to this EXACT absolute file path (overwrite=true):\n"
                    f"{escape}\n"
                    "Write this token as the file content:\n"
                    f"{token}\n"
                    "Step 2: If the tool failed because the path is outside the project root, reply with exactly: OUTSIDE_ROOT_OK\n"
                    "Do not attempt any other tools.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)

                errors = [
                    e
                    for e in r.events
                    if getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", "") == "ValueError"
                    and "tool path must be under project root" in (getattr(e, "error_message", "") or "").lower()
                ]
                if errors and (r.final_text or "").strip() == "OUTSIDE_ROOT_OK" and not escape.exists():
                    return

            self.fail("Write outside project root was not denied safely after 6 attempts")


if __name__ == "__main__":
    unittest.main()

