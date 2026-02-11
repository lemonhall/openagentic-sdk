from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

from e2e_cli_tests._harness import repo_root, require_env, temp_project_dir


def _run_cli(argv: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "openagentic_cli", *argv],
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        timeout=240,
    )


class TestCliRunJsonReal(unittest.TestCase):
    def test_run_json_emits_machine_readable_and_persists_session(self) -> None:
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

            token = f"CLI_E2E_RUN_JSON_{uuid.uuid4().hex}_END"
            prompt = f"请严格只回复：{token}"

            p = _run_cli(["run", "--json", prompt], cwd=project_dir, env=env)
            self.assertEqual(p.returncode, 0, p.stderr)

            try:
                obj = json.loads(p.stdout)
            except json.JSONDecodeError as e:
                self.fail(f"stdout is not JSON: {e}\n--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}")

            self.assertIsInstance(obj, dict)
            for k in ("final_text", "session_id", "stop_reason"):
                self.assertIn(k, obj)
            final_text = obj.get("final_text")
            session_id = obj.get("session_id")
            self.assertIsInstance(final_text, str)
            self.assertIn(token, final_text)
            self.assertIsInstance(session_id, str)
            self.assertEqual(len(session_id), 32)

            events = home_dir / "sessions" / session_id / "events.jsonl"
            self.assertTrue(events.exists(), f"missing events.jsonl: {events}")
            text = events.read_text(encoding="utf-8", errors="replace")
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()

