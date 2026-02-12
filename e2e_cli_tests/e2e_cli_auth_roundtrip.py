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
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=120,
    )


class TestCliAuthRoundtrip(unittest.TestCase):
    def test_auth_set_list_remove_is_isolated(self) -> None:
        require_env("RIGHTCODE_API_KEY")

        root = repo_root()
        with temp_project_dir() as td:
            project_dir = td / "project"
            home_dir = td / "home"

            env = dict(os.environ)
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONPATH"] = str(root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            env["OPENAGENTIC_SDK_HOME"] = str(home_dir)
            env["OPENCODE_TEST_HOME"] = str(home_dir)
            env["XDG_CONFIG_HOME"] = str(home_dir)

            provider_id = "openai-compatible"
            fake_key = f"FAKE_KEY_{uuid.uuid4().hex}"

            p1 = _run_cli(["auth", "set", provider_id, "--key", fake_key], cwd=project_dir, env=env)
            self.assertEqual(p1.returncode, 0, p1.stderr)
            self.assertIn("Stored auth for", p1.stdout)

            auth_path = home_dir / "auth.json"
            self.assertTrue(auth_path.exists())

            p2 = _run_cli(["auth", "list"], cwd=project_dir, env=env)
            self.assertEqual(p2.returncode, 0, p2.stderr)
            self.assertIn(provider_id, p2.stdout.splitlines())

            p3 = _run_cli(["auth", "remove", provider_id], cwd=project_dir, env=env)
            self.assertEqual(p3.returncode, 0, p3.stderr)
            self.assertIn("Removed auth for", p3.stdout)

            p4 = _run_cli(["auth", "list"], cwd=project_dir, env=env)
            self.assertEqual(p4.returncode, 0, p4.stderr)
            self.assertNotIn(provider_id, p4.stdout.splitlines())


if __name__ == "__main__":
    unittest.main()
