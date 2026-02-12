from __future__ import annotations

import os
import sys
import time
import unittest

from e2e_cli_win_tests._conpty import ConPtyProcess, conpty_available
from e2e_cli_win_tests._harness import repo_root, require_env, temp_project_dir


@unittest.skipUnless(sys.platform == "win32", "Windows-only")
@unittest.skipUnless(conpty_available(), "ConPTY not available")
class TestWinReplHelpExit(unittest.TestCase):
    def _wait_for_prompt(self, p: ConPtyProcess, *, timeout_s: float) -> str:
        deadline = time.time() + max(0.1, float(timeout_s))
        last_exc: Exception | None = None
        while time.time() < deadline:
            p.send("\r\n")
            try:
                return p.read_until("oa> ", timeout_s=2.0)
            except TimeoutError as e:
                last_exc = e
                time.sleep(0.1)
        if last_exc:
            raise last_exc
        raise TimeoutError("timeout waiting for oa> prompt")

    def test_bypass_has_no_autoapprove_prompt_and_help_exit_work(self) -> None:
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
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"

            p = ConPtyProcess([sys.executable, "-m", "openagentic_cli", "chat"], cwd=str(project_dir), env=env)
            try:
                out0 = self._wait_for_prompt(p, timeout_s=30.0)
                self.assertNotIn("Auto-approve Write/Edit/Bash", out0)

                p.send("/help\r\n")
                out1 = p.read_until("Commands:", timeout_s=15.0)
                self.assertIn("/exit", out1)
                self.assertIn("/paste", out1)

                p.send("/exit\r\n")
                res = p.close(timeout_s=10.0)
                self.assertEqual(res.exit_code, 0)
            finally:
                try:
                    p.close(timeout_s=10.0)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
