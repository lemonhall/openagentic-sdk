from __future__ import annotations

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


class TestCliRunNoStreamReal(unittest.TestCase):
    def test_run_no_stream_emits_final_text(self) -> None:
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

            token = f"CLI_E2E_RUN_NOSTREAM_{uuid.uuid4().hex}_END"
            prompt = f"请严格只回复：{token}"

            p = _run_cli(["run", "--no-stream", prompt], cwd=project_dir, env=env)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn(token, p.stdout)

            sessions = home_dir / "sessions"
            self.assertTrue(sessions.exists())
            ids = [d.name for d in sessions.iterdir() if d.is_dir() and len(d.name) == 32]
            self.assertEqual(len(ids), 1)
            events = sessions / ids[0] / "events.jsonl"
            self.assertTrue(events.exists())
            self.assertIn(token, events.read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()

