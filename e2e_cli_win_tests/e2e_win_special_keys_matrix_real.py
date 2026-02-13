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
class TestWinSpecialKeysMatrixReal(unittest.TestCase):
    def test_special_key_sequences_are_stripped_from_non_paste_turn(self) -> None:
        require_env("RIGHTCODE_API_KEY")
        ensure_conpty_expect_on_syspath()
        from conpty_expect._win_conpty import conpty_available  # noqa: PLC0415
        from conpty_expect.spawn import EOF, TIMEOUT, spawn  # noqa: PLC0415

        if not conpty_available():
            raise unittest.SkipTest("ConPTY not available")

        token = uuid.uuid4().hex
        base = f"SKMAT({token}) hello"
        expected = f"{base}X"

        # CSI sequences (common special keys)
        seqs = [
            "\x1b[A",  # up
            "\x1b[B",  # down
            "\x1b[C",  # right
            "\x1b[D",  # left
            "\x1b[H",  # home
            "\x1b[F",  # end
            "\x1b[2~",  # insert
            "\x1b[3~",  # delete
            "\x1b[5~",  # page up
            "\x1b[6~",  # page down
            "\x1b[15~",  # f5
        ]
        # SS3 sequences (F1-F4)
        seqs += [
            "\x1bOP",
            "\x1bOQ",
            "\x1bOR",
            "\x1bOS",
        ]

        root = repo_root()
        with temp_project_dir() as td:
            project_dir = td / "project"
            home_dir = td / "home"
            env = build_base_env(root=root, home_dir=home_dir)
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
                for s in seqs:
                    p.send(s)
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
