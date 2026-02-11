from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
import uuid

from e2e_cli_tests._harness import repo_root, require_env, temp_project_dir
from e2e_cli_tests._pty import PtyProcess


def _list_session_ids(home_dir: Path) -> list[str]:
    sessions = home_dir / "sessions"
    if not sessions.exists():
        return []
    out: list[str] = []
    for p in sessions.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if len(name) == 32 and all(c in "0123456789abcdef" for c in name):
            out.append(name)
    return sorted(out)


def _wait_for_session_count(home_dir: Path, expected: int, *, timeout_s: float = 8.0) -> list[str]:
    deadline = time.time() + max(0.1, float(timeout_s))
    while time.time() < deadline:
        ids = _list_session_ids(home_dir)
        if len(ids) == expected:
            return ids
        time.sleep(0.05)
    return _list_session_ids(home_dir)


def _count_lines(p: Path) -> int:
    try:
        return len(p.read_text(encoding="utf-8", errors="replace").splitlines())
    except Exception:
        return 0


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


@unittest.skipIf(os.name == "nt", "CLI PTY e2e requires POSIX pty; run under WSL2/Linux/macOS.")
class TestCliReplNewSessionReal(unittest.TestCase):
    def test_new_command_starts_fresh_session(self) -> None:
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
                p.read_until("oa> ", timeout_s=20.0)

                # First turn -> first session.
                token1 = f"CLI_E2E_NEW1_{uuid.uuid4().hex}"
                p.send(f"只回复 {token1}（不要加引号，不要调用任何工具）\n")
                p.read_until(token1, timeout_s=90.0)
                p.read_until("oa> ", timeout_s=20.0)

                ids1 = _wait_for_session_count(home_dir, 1, timeout_s=8.0)
                self.assertEqual(len(ids1), 1)
                sid1 = ids1[0]
                events1 = home_dir / "sessions" / sid1 / "events.jsonl"
                c1 = _count_lines(events1)
                self.assertGreater(c1, 0)

                # /new should reset the session context.
                p.send("/new\n")
                p.read_until("started new session", timeout_s=20.0)
                p.read_until("oa> ", timeout_s=20.0)

                # Second turn -> second session directory created.
                token2 = f"CLI_E2E_NEW2_{uuid.uuid4().hex}"
                p.send(f"只回复 {token2}（不要加引号，不要调用任何工具）\n")
                p.read_until(token2, timeout_s=90.0)
                p.read_until("oa> ", timeout_s=20.0)

                ids2 = _wait_for_session_count(home_dir, 2, timeout_s=8.0)
                self.assertEqual(len(ids2), 2)
                sid2 = ids2[1] if ids2[0] == sid1 else ids2[0]
                self.assertNotEqual(sid1, sid2)

                # Ensure the second session has its own events.
                events2 = home_dir / "sessions" / sid2 / "events.jsonl"
                c2 = _count_lines(events2)
                self.assertGreater(c2, 0)
                # Deterministic isolation check: the second-turn token must only appear in the second session's events.
                self.assertNotIn(token2, _read_text(events1))
                self.assertIn(token2, _read_text(events2))

                p.send("/exit\n")
                res = p.close(timeout_s=10.0)
                self.assertEqual(res.exit_code, 0)
            finally:
                try:
                    p.close(timeout_s=2.0)
                except Exception:
                    pass
