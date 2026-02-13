from __future__ import annotations

import os
import sys
import time
import unittest
import uuid

from e2e_cli_win_tests._conpty import ConPtyProcess, conpty_available


@unittest.skipUnless(sys.platform == "win32", "Windows-only")
@unittest.skipUnless(conpty_available(), "ConPTY not available")
class TestWinConptySmokeEcho(unittest.TestCase):
    def test_conpty_captures_cmd_output(self) -> None:
        token = f"CONPTY_ECHO_OK_{uuid.uuid4().hex}"

        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        p = ConPtyProcess(["cmd.exe", "/c", "echo", token], cwd=os.getcwd(), env=env)
        try:
            out = p.read_until(token, timeout_s=10.0)
            self.assertIn(token, out)
            # Give the reader a moment to drain before closing (helps avoid flaky "exit before match" races).
            time.sleep(0.1)
            res = p.close(timeout_s=10.0)
            self.assertEqual(res.exit_code, 0)
        finally:
            try:
                p.close(timeout_s=1.0)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()

