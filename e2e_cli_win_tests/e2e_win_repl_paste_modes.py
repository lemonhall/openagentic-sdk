from __future__ import annotations

import sys
import time
import unittest
import uuid

from e2e_cli_win_tests._harness import (
    build_base_env,
    count_event_type,
    ensure_conpty_expect_on_syspath,
    read_events_jsonl,
    repo_root,
    require_env,
    temp_project_dir,
    wait_for_single_session_id,
)

_BP_START = "\x1b[200~"
_BP_END = "\x1b[201~"


@unittest.skipUnless(sys.platform == "win32", "Windows-only")
class TestWinReplPasteModes(unittest.TestCase):
    def test_paste_and_bracketed_paste_do_not_trigger_repl_help(self) -> None:
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
            env["OA_BRACKETED_PASTE"] = "1"

            p = spawn(
                [sys.executable, "-m", "openagentic_cli", "chat"],
                cwd=str(project_dir),
                env=env,
                timeout=180.0,
                strip_ansi_codes=True,
            )
            try:
                self.assertEqual(p.expect(["oa>", TIMEOUT, EOF], timeout=30.0), 0)

                # /paste mode: multi-line content should be treated as one prompt.
                token1 = f"WIN_PASTE_OK_{uuid.uuid4().hex}_END"
                p.sendline("/paste")
                self.assertEqual(p.expect(["paste mode: finish with /end", TIMEOUT, EOF], timeout=10.0), 0)
                p.send(f"请严格只回复：{token1}\r\n第一行\r\n\r\n/this_is_not_a_command\r\n/end\r\n")
                self.assertEqual(p.expect(["• Done", TIMEOUT, EOF], timeout=180.0), 0)
                self.assertNotIn("Commands:", p.before)
                self.assertEqual(p.expect(["oa>", TIMEOUT, EOF], timeout=60.0), 0)

                session_id = wait_for_single_session_id(home_dir, timeout_s=5.0)
                events1 = read_events_jsonl(home_dir, session_id)
                self.assertGreaterEqual(count_event_type(events1, "user.message"), 1)
                last_user_text = next(
                    (e.get("text", "") for e in reversed(events1) if e.get("type") == "user.message"),
                    "",
                )
                self.assertIn(token1, str(last_user_text))
                self.assertIn("第一行", str(last_user_text))
                # Blank line is preserved.
                self.assertIn("\n\n/this_is_not_a_command", str(last_user_text))

                # Bracketed paste: pasted `/help` must not run help command.
                token2 = f"WIN_BP_OK_{uuid.uuid4().hex}_END"
                p.send(_BP_START + "\r\n")
                p.send("/help\r\n")
                p.send(f"请严格只回复：{token2}\r\n")
                p.send(_BP_END + "\r\n")

                self.assertEqual(p.expect(["• Done", TIMEOUT, EOF], timeout=180.0), 0)
                self.assertNotIn("Commands:", p.before)
                self.assertEqual(p.expect(["oa>", TIMEOUT, EOF], timeout=60.0), 0)

                deadline = time.time() + 5.0
                events2 = read_events_jsonl(home_dir, session_id)
                while len(events2) <= len(events1) and time.time() < deadline:
                    time.sleep(0.05)
                    events2 = read_events_jsonl(home_dir, session_id)
                self.assertGreater(len(events2), len(events1))
                last_user_text2 = next(
                    (e.get("text", "") for e in reversed(events2) if e.get("type") == "user.message"),
                    "",
                )
                self.assertIn("/help", str(last_user_text2))
                self.assertIn(token2, str(last_user_text2))

                p.sendline("/exit")
                self.assertEqual(p.expect([EOF, TIMEOUT], timeout=30.0), 0)
            finally:
                rc = p.close(force=bool(p.isalive()))
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
