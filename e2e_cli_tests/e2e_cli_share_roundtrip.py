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
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=240,
    )


class TestCliShareRoundtrip(unittest.TestCase):
    def test_share_shared_unshare_roundtrip(self) -> None:
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
            env["OA_PERMISSION_MODE"] = "bypass"

            token = f"CLI_E2E_SHARE_{uuid.uuid4().hex}_END"
            prompt = f"请严格只回复：{token}"

            runp = _run_cli(["run", "--json", prompt], cwd=project_dir, env=env)
            self.assertEqual(runp.returncode, 0, runp.stderr)
            obj = json.loads(runp.stdout)
            sid = obj.get("session_id")
            self.assertIsInstance(sid, str)

            sp = _run_cli(["share", sid], cwd=project_dir, env=env)
            self.assertEqual(sp.returncode, 0, sp.stderr)
            share_id = sp.stdout.strip()
            self.assertTrue(share_id)

            sh = _run_cli(["shared", share_id], cwd=project_dir, env=env)
            self.assertEqual(sh.returncode, 0, sh.stderr)
            self.assertTrue(sh.stdout.strip())

            un = _run_cli(["unshare", share_id], cwd=project_dir, env=env)
            self.assertEqual(un.returncode, 0, un.stderr)
            self.assertIn("ok", un.stdout.lower())

            sh2 = _run_cli(["shared", share_id], cwd=project_dir, env=env)
            self.assertNotEqual(sh2.returncode, 0, "expected `oa shared` to fail after unshare")


if __name__ == "__main__":
    unittest.main()
