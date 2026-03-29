from __future__ import annotations

import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest import mock


def _load_harness_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "e2e_k3d_tests" / "_harness.py"
    spec = spec_from_file_location("e2e_k3d_tests__harness", module_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestK3dTracingOverlayRestore(unittest.TestCase):
    def test_ensure_tracing_ready_applies_v58_jaeger_ui_overlay_manifests(self) -> None:
        module = _load_harness_module()
        run_calls: list[list[str]] = []

        def fake_run(cmd: list[str], *, check: bool = True, env=None):
            _ = (check, env)
            run_calls.append(cmd)
            return mock.Mock(stdout="", returncode=0)

        with mock.patch.object(module, "ensure_cluster_ready"), mock.patch.object(
            module, "_patch_tracing_deployment"
        ), mock.patch.object(module, "_run", side_effect=fake_run):
            module._TRACING_READY = False
            module.ensure_tracing_ready()

        apply_targets = [str(cmd[-1]).replace("\\", "/") for cmd in run_calls if len(cmd) >= 4 and cmd[:3] == ["kubectl", "apply", "-f"]]
        self.assertTrue(any(target.endswith("deploy/k8s/v57/jaeger.yaml") for target in apply_targets))
        self.assertTrue(any(target.endswith("deploy/k8s/v57/otel-collector.yaml") for target in apply_targets))
        self.assertTrue(any(target.endswith("deploy/k8s/v58/jaeger-ui-proxy.yaml") for target in apply_targets))
        self.assertTrue(any(target.endswith("deploy/k8s/v58/jaeger-ui-overlay.yaml") for target in apply_targets))


if __name__ == "__main__":
    unittest.main()
