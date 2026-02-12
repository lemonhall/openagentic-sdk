from __future__ import annotations

import os
import sys
import time
import unittest
import uuid

from e2e_cli_win_tests._conpty import ConPtyProcess, conpty_available
from e2e_cli_win_tests._harness import repo_root, require_env, temp_project_dir

_BP_START = "\x1b[200~"
_BP_END = "\x1b[201~"


@unittest.skipUnless(sys.platform == "win32", "Windows-only")
@unittest.skipUnless(conpty_available(), "ConPTY not available")
class TestWinReplPasteModes(unittest.TestCase):
    def _wait_for_prompt(self, p: ConPtyProcess, *, timeout_s: float) -> None:
        deadline = time.time() + max(0.1, float(timeout_s))
        last_exc: Exception | None = None
        while time.time() < deadline:
            p.send("\r\n")
            try:
                p.read_until("oa> ", timeout_s=2.0)
                return
            except TimeoutError as e:
                last_exc = e
                time.sleep(0.1)
        if last_exc:
            raise last_exc
        raise TimeoutError("timeout waiting for oa> prompt")

    def test_paste_and_bracketed_paste_do_not_trigger_repl_help(self) -> None:
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
                self._wait_for_prompt(p, timeout_s=30.0)

                # /paste mode: multi-line content should be treated as one prompt.
                token1 = f"WIN_PASTE_OK_{uuid.uuid4().hex}_END"
                p.send("/paste\r\n")
                p.read_until("paste mode: finish with /end", timeout_s=10.0)
                p.send(f"请严格只回复：{token1}\r\n第二行\r\n/end\r\n")
                out1 = p.read_until(token1, timeout_s=120.0)
                self.assertNotIn("Commands:", out1)
                p.read_until("oa> ", timeout_s=30.0)

                # Bracketed paste: pasted `/help` must not run help command.
                token2 = f"WIN_BP_OK_{uuid.uuid4().hex}_END"
                p.send(_BP_START + "/help\r\n")
                p.send(f"请严格只回复：{token2}\r\n")
                p.send(_BP_END + "\r\n")

                out2 = p.read_until(token2, timeout_s=120.0)
                self.assertNotIn("Commands:", out2)
                p.read_until("oa> ", timeout_s=30.0)

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
