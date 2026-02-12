from __future__ import annotations

import sys
import time
import unittest
import uuid

from e2e_cli_win_tests._harness import (
    build_base_env,
    ensure_conpty_expect_on_syspath,
    read_events_jsonl,
    repo_root,
    require_env,
    temp_project_dir,
    wait_for_single_session_id,
)


@unittest.skipUnless(sys.platform == "win32", "Windows-only")
class TestWinTypeaheadWithoutEnterReal(unittest.TestCase):
    def test_typeahead_without_enter_is_not_dropped(self) -> None:
        require_env("RIGHTCODE_API_KEY")
        ensure_conpty_expect_on_syspath()
        from conpty_expect._win_conpty import conpty_available  # noqa: PLC0415
        from conpty_expect.spawn import EOF, TIMEOUT, spawn  # noqa: PLC0415

        if not conpty_available():
            raise unittest.SkipTest("ConPTY not available")

        token = uuid.uuid4().hex
        turn1 = (
            f"Turn1 ({token}): Reply with a long answer (at least 1200 characters), "
            "but do not use code blocks."
        )
        # The key point: we will type this line WITHOUT pressing Enter until after Turn1 completes.
        typed = f"Turn2_TYPED_NO_ENTER ({token}): Reply with exactly the word OK."

        root = repo_root()
        with temp_project_dir() as td:
            project_dir = td / "project"
            home_dir = td / "home"
            env = build_base_env(root=root, home_dir=home_dir)

            # Try to reproduce real user conditions:
            # - allow color prompt (prompt redraw uses carriage return)
            env.pop("NO_COLOR", None)

            p = spawn(
                [sys.executable, "-m", "openagentic_cli", "chat"],
                cwd=str(project_dir),
                env=env,
                timeout=240.0,
                strip_ansi_codes=True,
            )
            try:
                self.assertEqual(p.expect(["oa> ", TIMEOUT, EOF], timeout=30.0), 0)

                p.sendline(turn1)

                # While the assistant is still streaming output, type the next line (no Enter).
                time.sleep(0.15)
                p.send(typed)

                # Wait for Turn1 to finish.
                self.assertEqual(p.expect(["• Done", TIMEOUT, EOF], timeout=180.0), 0)
                self.assertEqual(p.expect(["oa> ", TIMEOUT, EOF], timeout=60.0), 0)

                # Now press Enter only. If the typed line was preserved in the input buffer,
                # it should become the next user.message turn.
                p.send("\r\n")

                self.assertEqual(p.expect(["• Done", TIMEOUT, EOF], timeout=180.0), 0)
                self.assertEqual(p.expect(["oa> ", TIMEOUT, EOF], timeout=60.0), 0)

                p.sendline("/exit")
                self.assertEqual(p.expect([EOF, TIMEOUT], timeout=30.0), 0)
            finally:
                rc = p.close(force=bool(p.isalive()))
            self.assertEqual(rc, 0)

            session_id = wait_for_single_session_id(home_dir, timeout_s=5.0)
            events = read_events_jsonl(home_dir, session_id)
            texts = [str(e.get("text", "")) for e in events if e.get("type") == "user.message"]

            self.assertIn(turn1, texts)
            self.assertIn(typed, texts)


if __name__ == "__main__":
    unittest.main()

