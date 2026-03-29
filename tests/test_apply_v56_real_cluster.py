from __future__ import annotations

import os
import subprocess
import sys
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


def _load_script_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "apply_v56_real_cluster.py"
    spec = spec_from_file_location("apply_v56_real_cluster", script_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestApplyV56RealCluster(unittest.TestCase):
    def test_rewrites_host_k3d_internal_proxy_to_gateway_ip(self) -> None:
        module = _load_script_module()
        env_map = {
            "HTTP_PROXY": "http://host.k3d.internal:17897",
            "HTTPS_PROXY": "http://host.k3d.internal:17897",
            "NO_PROXY": "127.0.0.1,localhost,.svc,.cluster.local",
        }

        rewritten = module._rewrite_k3d_proxy_hosts(env_map, gateway_ip="172.18.0.1")

        self.assertEqual(rewritten["HTTP_PROXY"], "http://172.18.0.1:17897")
        self.assertEqual(rewritten["HTTPS_PROXY"], "http://172.18.0.1:17897")
        self.assertEqual(rewritten["NO_PROXY"], env_map["NO_PROXY"])

    def test_scopes_global_proxy_env_to_web_only_variables(self) -> None:
        module = _load_script_module()
        env_map = {
            "HTTP_PROXY": "http://172.18.0.1:17897",
            "HTTPS_PROXY": "http://172.18.0.1:17897",
            "NO_PROXY": "127.0.0.1,localhost,.svc,.cluster.local",
            "RIGHTCODE_API_KEY": "rk-123",
        }

        scoped = module._scope_web_proxy_env(env_map)

        self.assertNotIn("HTTP_PROXY", scoped)
        self.assertNotIn("HTTPS_PROXY", scoped)
        self.assertNotIn("NO_PROXY", scoped)
        self.assertEqual(scoped["OPENAGENTIC_WEB_HTTP_PROXY"], "http://172.18.0.1:17897")
        self.assertEqual(scoped["OPENAGENTIC_WEB_HTTPS_PROXY"], "http://172.18.0.1:17897")
        self.assertEqual(scoped["OPENAGENTIC_WEB_NO_PROXY"], "127.0.0.1,localhost,.svc,.cluster.local")
        self.assertEqual(scoped["RIGHTCODE_API_KEY"], "rk-123")

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
        self.assertNotIn(
            'name: HTTP_PROXY',
            rendered_host,
        )
        self.assertIn(
            '--no-index --find-links /workspace/repo/.openagentic-wheelhouse',
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
        self.assertNotIn(
            'name: HTTP_PROXY',
            rendered_workers,
        )
        self.assertIn(
            '--no-index --find-links /workspace/repo/.openagentic-wheelhouse',
            rendered_workers,
        )
        self.assertIn(
            'export OTEL_RESOURCE_ATTRIBUTES="oa.node.name=${OA_REMOTE_NODE_NAME},oa.role=worker,oa.namespace=openagentic-v56-real"',
            rendered_workers,
        )

    def test_ensure_runtime_wheelhouse_downloads_requirements_into_authoritative_mirror(self) -> None:
        module = _load_script_module()
        with TemporaryDirectory() as td:
            mirror_root = Path(td) / "mirror"
            mirror_root.mkdir(parents=True, exist_ok=True)
            calls: list[list[str]] = []

            def fake_run(argv: list[str], check: bool, env: dict[str, str] | None = None, **kwargs):
                _ = (check, env, kwargs)
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with mock.patch.object(module, "_authoritative_repo_root", return_value=mirror_root), mock.patch.object(
                module.subprocess,
                "run",
                side_effect=fake_run,
            ):
                wheelhouse = module._ensure_runtime_wheelhouse()
            self.assertEqual(wheelhouse, mirror_root / ".openagentic-wheelhouse")
            self.assertTrue((wheelhouse / ".requirements.txt").exists())
            self.assertEqual(calls[0][0:4], [sys.executable, "-m", "pip", "download"])
            self.assertIn(str(wheelhouse), calls[0])
            self.assertIn("protobuf<6", calls[0])
            self.assertIn("opentelemetry-exporter-otlp-proto-http<2", calls[0])


if __name__ == "__main__":
    unittest.main()
