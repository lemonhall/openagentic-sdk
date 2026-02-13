from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
import time

from e2e_cli_tests._harness import repo_root, require_env, temp_project_dir
from e2e_cli_tests._pty import PtyProcess, strip_ansi


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


@unittest.skipIf(os.name == "nt", "CLI PTY e2e requires POSIX pty; run under WSL2/Linux/macOS.")
class TestCliResumeAndLogsReal(unittest.TestCase):
    def test_resume_and_logs(self) -> None:
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

            # Create a session.
            p1 = PtyProcess([sys.executable, "-m", "openagentic_cli", "chat"], cwd=str(project_dir), env=env)
            try:
                p1.read_until("oa>", timeout_s=20.0)
                p1.send("只回复 CLI_E2E_SESS（不要加引号）\n")
                p1.read_until("CLI_E2E_SESS", timeout_s=90.0)
                p1.read_until("oa>", timeout_s=20.0)
                sid = _wait_for_single_session_id(home_dir, timeout_s=5.0)
                self.assertTrue(sid, "expected exactly one session dir under OPENAGENTIC_SDK_HOME")
                events_path = home_dir / "sessions" / sid / "events.jsonl"
                before_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines()) if events_path.exists() else 0
                self.assertGreater(before_lines, 0)
                p1.read_until("oa>", timeout_s=20.0)
                p1.send("/exit\n")
                _ = p1.close(timeout_s=10.0)
            finally:
                try:
                    p1.close(timeout_s=2.0)
                except Exception:
                    pass

            # Logs command (still run under PTY so stdout is a tty).
            p2 = PtyProcess([sys.executable, "-m", "openagentic_cli", "logs", sid], cwd=str(project_dir), env=env)
            try:
                res2 = p2.close(timeout_s=30.0)
                out2 = strip_ansi(res2.output).strip()
                self.assertNotEqual(out2, "")
            finally:
                try:
                    p2.close(timeout_s=2.0)
                except Exception:
                    pass

            # Resume the session.
            p3 = PtyProcess([sys.executable, "-m", "openagentic_cli", "resume", sid], cwd=str(project_dir), env=env)
            try:
                p3.read_until("oa>", timeout_s=20.0)
                p3.send("只回复 CLI_E2E_RESUME（不要加引号）\n")
                p3.read_until("CLI_E2E_RESUME", timeout_s=90.0)
                p3.read_until("oa>", timeout_s=20.0)
                self.assertEqual(_find_single_session_id(home_dir), sid)
                after_lines = len(events_path.read_text(encoding="utf-8", errors="replace").splitlines()) if events_path.exists() else 0
                self.assertGreater(after_lines, before_lines)
                p3.read_until("oa>", timeout_s=20.0)
                p3.send("/exit\n")
                _ = p3.close(timeout_s=10.0)
            finally:
                try:
                    p3.close(timeout_s=2.0)
                except Exception:
                    pass
