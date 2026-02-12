from __future__ import annotations

import sys
import unittest

from e2e_cli_win_tests._harness import build_base_env, ensure_conpty_expect_on_syspath, repo_root, require_env, temp_project_dir


@unittest.skipUnless(sys.platform == "win32", "Windows-only")
class TestWinReplHelpExit(unittest.TestCase):
    def test_bypass_has_no_autoapprove_prompt_and_help_exit_work(self) -> None:
        require_env("RIGHTCODE_API_KEY")

        ensure_conpty_expect_on_syspath()
        from conpty_expect._win_conpty import conpty_available  # noqa: PLC0415
        from conpty_expect.spawn import EOF, TIMEOUT, spawn  # noqa: PLC0415

        if not conpty_available():
            raise unittest.SkipTest("ConPTY not available")

        root = repo_root()
        with temp_project_dir() as td:
            project_dir = td / "project"
            home_dir = td / "home"

            env = build_base_env(root=root, home_dir=home_dir)

            p = spawn(
                [sys.executable, "-m", "openagentic_cli", "chat"],
                cwd=str(project_dir),
                env=env,
                timeout=180.0,
                strip_ansi_codes=True,
            )
            try:
                self.assertEqual(p.expect(["oa> ", TIMEOUT, EOF], timeout=30.0), 0)
                self.assertNotIn("Auto-approve Write/Edit/Bash", p.before)

                p.sendline("/help")
                self.assertEqual(p.expect(["Commands:", TIMEOUT, EOF], timeout=15.0), 0)
                self.assertEqual(p.expect(["/exit", TIMEOUT, EOF], timeout=15.0), 0)
                self.assertEqual(p.expect(["/paste", TIMEOUT, EOF], timeout=15.0), 0)

                p.sendline("/exit")
                self.assertEqual(p.expect([EOF, TIMEOUT], timeout=30.0), 0)
            finally:
                rc = p.close(force=bool(p.isalive()))
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
