from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class TestApplyV56RealCluster(unittest.TestCase):
    def test_rendered_chat_host_uses_service_dns_for_remote_workers(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as td:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(repo_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
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
                env=env,
            )

            rendered_host = (Path(td) / "chat-host-real.yaml").read_text(encoding="utf-8")
            rendered_workers = (Path(td) / "v56-workers-real.yaml").read_text(encoding="utf-8")

        self.assertEqual(proc.returncode, 0)
        self.assertIn(
            "--node-url k3d-v56-openagentic-agent-0=http://oa-remote-worker-agent-0.openagentic-v56-real.svc.cluster.local:8765",
            rendered_host,
        )
        self.assertIn(
            "--node-url k3d-v56-openagentic-agent-1=http://oa-remote-worker-agent-1.openagentic-v56-real.svc.cluster.local:8765",
            rendered_host,
        )
        self.assertIn(
            'value: "oa-cluster-chat-host-real"',
            rendered_host,
        )
        self.assertIn(
            'value: "http://otel-collector.openagentic-v56.svc.cluster.local:4318"',
            rendered_host,
        )
        self.assertIn(
            'opentelemetry-exporter-otlp-proto-http<2',
            rendered_host,
        )
        self.assertIn(
            'export OTEL_RESOURCE_ATTRIBUTES="oa.node.name=${OA_HOST_NODE_NAME},oa.role=host,oa.namespace=openagentic-v56-real"',
            rendered_host,
        )
        self.assertIn(
            'value: "oa-remote-worker-real"',
            rendered_workers,
        )
        self.assertIn(
            'export OTEL_RESOURCE_ATTRIBUTES="oa.node.name=${OA_REMOTE_NODE_NAME},oa.role=worker,oa.namespace=openagentic-v56-real"',
            rendered_workers,
        )


if __name__ == "__main__":
    unittest.main()
