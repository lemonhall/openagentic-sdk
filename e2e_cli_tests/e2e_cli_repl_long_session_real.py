from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
import time

from e2e_cli_tests._harness import repo_root, require_env, temp_project_dir
from e2e_cli_tests._pty import PtyProcess


def _find_single_session_id(home_dir: Path) -> str:
    sessions = home_dir / "sessions"
    if not sessions.exists():
        return ""
    ids = [p.name for p in sessions.iterdir() if p.is_dir() and len(p.name) == 32 and all(c in "0123456789abcdef" for c in p.name)]
    if len(ids) != 1:
        return ""
    return ids[0]

def _wait_for_single_session_id(home_dir: Path, *, timeout_s: float = 5.0) -> str:
    deadline = time.time() + max(0.1, float(timeout_s))
    while time.time() < deadline:
        sid = _find_single_session_id(home_dir)
        if sid:
            return sid
        time.sleep(0.05)
    return _find_single_session_id(home_dir)


def _count_lines(p: Path) -> int:
    try:
        return len(p.read_text(encoding="utf-8", errors="replace").splitlines())
    except Exception:
        return 0


@unittest.skipIf(os.name == "nt", "CLI PTY e2e requires POSIX pty; run under WSL2/Linux/macOS.")
class TestCliReplLongSessionReal(unittest.TestCase):
    def test_three_turns_same_session_id(self) -> None:
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
                p.read_until("oa> ", timeout_s=20.0)

                p.send("只回复 CLI_E2E_OK（不要加引号，不要调用任何工具）\n")
                p.read_until("CLI_E2E_OK", timeout_s=90.0)
                p.read_until("oa> ", timeout_s=20.0)

                sid = _wait_for_single_session_id(home_dir, timeout_s=5.0)
                self.assertTrue(sid, "expected exactly one session dir under OPENAGENTIC_SDK_HOME")
                events_path = home_dir / "sessions" / sid / "events.jsonl"
                c1 = _count_lines(events_path)
                self.assertGreater(c1, 0, "expected events.jsonl to be non-empty after first turn")

                p.send("只回复 CLI_E2E_OK2（不要加引号，不要调用任何工具）\n")
                p.read_until("CLI_E2E_OK2", timeout_s=90.0)
                p.read_until("oa> ", timeout_s=20.0)
                self.assertEqual(_find_single_session_id(home_dir), sid)
                c2 = _count_lines(events_path)
                self.assertGreater(c2, c1)

                p.send("只回复 CLI_E2E_OK3（不要加引号，不要调用任何工具）\n")
                p.read_until("CLI_E2E_OK3", timeout_s=90.0)
                p.read_until("oa> ", timeout_s=20.0)
                self.assertEqual(_find_single_session_id(home_dir), sid)
                c3 = _count_lines(events_path)
                self.assertGreater(c3, c2)

                p.send("/exit\n")
                _ = p.close(timeout_s=10.0)
            finally:
                try:
                    p.close(timeout_s=2.0)
                except Exception:
                    pass
