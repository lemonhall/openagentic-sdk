from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path

from e2e_cli_tests._harness import repo_root, require_env, temp_project_dir
from e2e_cli_tests._pty import PtyProcess

_BP_START = "\x1b[200~"
_BP_END = "\x1b[201~"


def _find_single_session_id(home_dir: Path) -> str:
    sessions = home_dir / "sessions"
    if not sessions.exists():
        return ""
    ids = [p.name for p in sessions.iterdir() if p.is_dir() and len(p.name) == 32 and all(c in "0123456789abcdef" for c in p.name)]
    if len(ids) != 1:
        return ""
    return ids[0]


def _wait_for_single_session_id(home_dir: Path, *, timeout_s: float = 8.0) -> str:
    deadline = time.time() + max(0.1, float(timeout_s))
    while time.time() < deadline:
        sid = _find_single_session_id(home_dir)
        if sid:
            return sid
        time.sleep(0.05)
    return _find_single_session_id(home_dir)


def _user_messages(events_path: Path) -> list[str]:
    out: list[str] = []
    for raw in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("type") == "user.message" and isinstance(obj.get("text"), str):
            out.append(str(obj["text"]))
    return out


@unittest.skipIf(os.name == "nt", "CLI PTY e2e requires POSIX pty; run under WSL2/Linux/macOS.")
class TestCliReplPasteModesReal(unittest.TestCase):
    def test_paste_command_and_bracketed_paste_not_interpreted_as_repl_command(self) -> None:
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

                # Ensure a session exists and we have an events file to inspect.
                p.send("只回复 CLI_E2E_PASTE_BOOT（不要加引号，不要调用任何工具）\n")
                p.read_until("CLI_E2E_PASTE_BOOT", timeout_s=90.0)
                p.read_until("oa> ", timeout_s=20.0)

                sid = _wait_for_single_session_id(home_dir, timeout_s=8.0)
                self.assertTrue(sid)
                events = home_dir / "sessions" / sid / "events.jsonl"
                before_msgs = _user_messages(events)

                # 1) Manual paste mode: /paste ... /end should become one user turn (one user.message with a newline).
                p.send("/paste\n")
                p.read_until("paste mode: finish with /end", timeout_s=20.0)

                line1 = "只回复 CLI_E2E_PASTE_OK（不要加引号，不要调用任何工具）"
                line2 = "第二行用于测试换行"
                p.send(line1 + "\n" + line2 + "\n/end\n")

                p.read_until("CLI_E2E_PASTE_OK", timeout_s=90.0)
                p.read_until("oa> ", timeout_s=20.0)

                after_msgs = _user_messages(events)
                self.assertEqual(len(after_msgs), len(before_msgs) + 1)
                self.assertTrue(any(m == f"{line1}\n{line2}" for m in after_msgs), "expected one multiline user.message from /paste mode")

                # 2) Bracketed paste: content starting with `/help` must NOT run the REPL help command.
                # We assert deterministically by checking that the user message is persisted (help command would not persist a user.message).
                bp1 = "/help"
                bp2 = "只回复 CLI_E2E_BP_OK（不要加引号，不要调用任何工具）"
                p.send(_BP_START + bp1 + "\n")
                p.send(bp2 + "\n")
                p.send(_BP_END + "\n")

                p.read_until("CLI_E2E_BP_OK", timeout_s=90.0)
                p.read_until("oa> ", timeout_s=20.0)

                final_msgs = _user_messages(events)
                self.assertEqual(len(final_msgs), len(after_msgs) + 1)
                self.assertTrue(any(m == f"{bp1}\n{bp2}" for m in final_msgs), "expected bracketed-paste content to persist as user.message")

                p.send("/exit\n")
                res = p.close(timeout_s=10.0)
                self.assertEqual(res.exit_code, 0)
            finally:
                try:
                    p.close(timeout_s=2.0)
                except Exception:
                    pass

