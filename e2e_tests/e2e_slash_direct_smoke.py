from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2ESlashDirectSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_user_slash_command_is_expanded_before_model_call_blackbox(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            token = f"E2E_SLASH_DIRECT_OK_{uuid.uuid4().hex}"

            cmd_dir = root / ".opencode" / "commands"
            cmd_dir.mkdir(parents=True)
            (cmd_dir / "hello.md").write_text(f"Reply with exactly: {token}\n", encoding="utf-8")

            opts = make_options(root, allowed_tools=[])
            r = await openagentic_sdk.run(prompt="/hello world", options=opts)
            self.assertIn(token, r.final_text or "")


if __name__ == "__main__":
    unittest.main()

