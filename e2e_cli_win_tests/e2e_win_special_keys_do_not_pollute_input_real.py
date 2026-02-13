from __future__ import annotations

import sys
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
class TestWinSpecialKeysDoNotPolluteInputReal(unittest.TestCase):
    def test_arrow_key_sequences_do_not_end_up_in_events_jsonl(self) -> None:
        require_env("RIGHTCODE_API_KEY")
        ensure_conpty_expect_on_syspath()
        from conpty_expect._win_conpty import conpty_available  # noqa: PLC0415
        from conpty_expect.spawn import EOF, TIMEOUT, spawn  # noqa: PLC0415

        if not conpty_available():
            raise unittest.SkipTest("ConPTY not available")

        token = uuid.uuid4().hex
        base = f"SPECIALKEY({token}) abc"
        expected = f"{base}X"

        root = repo_root()
        with temp_project_dir() as td:
            project_dir = td / "project"
            home_dir = td / "home"
            env = build_base_env(root=root, home_dir=home_dir)

            # We want VT input enabled so CSI sequences like ESC[D/ESC[C are treated as keys,
            # not literal text.
            env["OA_BRACKETED_PASTE"] = "1"
            env.pop("NO_COLOR", None)

            p = spawn(
                [sys.executable, "-m", "openagentic_cli", "chat"],
                cwd=str(project_dir),
                env=env,
                timeout=240.0,
                strip_ansi_codes=True,
            )
            try:
                self.assertEqual(p.expect(["oa>", TIMEOUT, EOF], timeout=30.0), 0)

                p.send(base)
                # Left then right arrow: should be a no-op for the final input line.
                p.send("\x1b[D")
                p.send("\x1b[C")
                p.send("X")
                p.send("\r\n")

                self.assertEqual(p.expect(["• Done", TIMEOUT, EOF], timeout=180.0), 0)
                self.assertEqual(p.expect(["oa>", TIMEOUT, EOF], timeout=60.0), 0)

                p.sendline("/exit")
                self.assertEqual(p.expect([EOF, TIMEOUT], timeout=30.0), 0)
            finally:
                rc = p.close(force=bool(p.isalive()))
            self.assertEqual(rc, 0)

            session_id = wait_for_single_session_id(home_dir, timeout_s=5.0)
            events = read_events_jsonl(home_dir, session_id)
            texts = [str(e.get("text", "")) for e in events if e.get("type") == "user.message"]

            self.assertIn(expected, texts)
            self.assertFalse(any("\x1b" in t for t in texts), "unexpected ESC sequence leaked into user.message")


if __name__ == "__main__":
    unittest.main()
