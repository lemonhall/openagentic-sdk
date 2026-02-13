from __future__ import annotations

import os
import sys
import unittest

from e2e_cli_tests._harness import repo_root, require_env, temp_project_dir
from e2e_cli_tests._pty import PtyProcess


@unittest.skipIf(os.name == "nt", "CLI PTY e2e requires POSIX pty; run under WSL2/Linux/macOS.")
class TestCliReplHelpExitTty(unittest.TestCase):
    def test_help_and_exit(self) -> None:
        require_env("RIGHTCODE_API_KEY")

        root = repo_root()
        with temp_project_dir() as td:
            project_dir = td / "project"
            home_dir = td / "home"

            env = dict(os.environ)
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONPATH"] = str(root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            env["OPENAGENTIC_SDK_HOME"] = str(home_dir)
            env["OPENCODE_TEST_HOME"] = str(home_dir)
            env["XDG_CONFIG_HOME"] = str(home_dir)
            env["OA_PERMISSION_MODE"] = "bypass"
            env["OA_SHOW_THINKING"] = "0"

            p = PtyProcess([sys.executable, "-m", "openagentic_cli", "chat"], cwd=str(project_dir), env=env)
            try:
                p.read_until("Type /help for commands.", timeout_s=20.0)
                p.read_until("oa>", timeout_s=20.0)

                p.send("/help\n")
                out = p.read_until("Commands:", timeout_s=20.0)
                self.assertIn("/exit", out)
                self.assertIn("/paste", out)

                p.send("/exit\n")
                # The REPL should exit cleanly.
                res = p.close(timeout_s=10.0)
                self.assertEqual(res.exit_code, 0)
            finally:
                try:
                    p.close(timeout_s=2.0)
                except Exception:
                    pass
