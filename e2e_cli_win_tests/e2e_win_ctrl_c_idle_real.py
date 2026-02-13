from __future__ import annotations

import sys
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


@unittest.skipUnless(sys.platform == "win32", "Windows-only")
class TestWinCtrlCIdleReal(unittest.TestCase):
    def test_ctrl_c_at_prompt_does_not_create_user_turn(self) -> None:
        require_env("RIGHTCODE_API_KEY")
        ensure_conpty_expect_on_syspath()
        from conpty_expect._win_conpty import conpty_available  # noqa: PLC0415
        from conpty_expect.spawn import EOF, TIMEOUT, spawn  # noqa: PLC0415

        if not conpty_available():
            raise unittest.SkipTest("ConPTY not available")

        token = uuid.uuid4().hex
        turn1 = f"CTRL_C_IDLE({token}): Reply with exactly the word OK."

        root = repo_root()
        with temp_project_dir() as td:
            project_dir = td / "project"
            home_dir = td / "home"
            env = build_base_env(root=root, home_dir=home_dir)

            # Enable VT input so Ctrl+C is handled consistently across terminals.
            env["OA_BRACKETED_PASTE"] = "1"

            p = spawn(
                [sys.executable, "-m", "openagentic_cli", "chat"],
                cwd=str(project_dir),
                env=env,
                timeout=240.0,
                strip_ansi_codes=True,
            )
            try:
                self.assertEqual(p.expect(["oa>", TIMEOUT, EOF], timeout=30.0), 0)

                # Ctrl+C at idle should not become prompt text or a user.message.
                p.send("\x03")
                self.assertEqual(p.expect(["oa>", TIMEOUT, EOF], timeout=15.0), 0)

                p.sendline(turn1)
                self.assertEqual(p.expect(["• Done", TIMEOUT, EOF], timeout=180.0), 0)
                self.assertEqual(p.expect(["oa>", TIMEOUT, EOF], timeout=60.0), 0)

                p.sendline("/exit")
                self.assertEqual(p.expect([EOF, TIMEOUT], timeout=30.0), 0)
            finally:
                rc = p.close(force=bool(p.isalive()))
            self.assertEqual(rc, 0)

            session_id = wait_for_single_session_id(home_dir, timeout_s=5.0)
            events = read_events_jsonl(home_dir, session_id)
            self.assertEqual(count_event_type(events, "user.message"), 1)

            last_user = next((e.get("text", "") for e in reversed(events) if e.get("type") == "user.message"), "")
            self.assertEqual(str(last_user), turn1)


if __name__ == "__main__":
    unittest.main()
