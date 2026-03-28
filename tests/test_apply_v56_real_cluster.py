from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class TestApplyV56RealCluster(unittest.TestCase):
    def test_rendered_chat_host_uses_service_dns_for_remote_workers(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as td:
            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/apply_v56_real_cluster.py",
                    "--repo-root",
                    str(repo_root),
                    "--remote-config",
                    "openagentic.remote.example.json",
                    "--env-file",
                    ".openagentic.remote.env.example",
                    "--output-dir",
                    td,
                ],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )

            rendered = (Path(td) / "chat-host-real.yaml").read_text(encoding="utf-8")

        self.assertEqual(proc.returncode, 0)
        self.assertIn(
            "--node-url k3d-v56-openagentic-agent-0=http://oa-remote-worker-agent-0.openagentic-v56-real.svc.cluster.local:8765",
            rendered,
        )
        self.assertIn(
            "--node-url k3d-v56-openagentic-agent-1=http://oa-remote-worker-agent-1.openagentic-v56-real.svc.cluster.local:8765",
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
