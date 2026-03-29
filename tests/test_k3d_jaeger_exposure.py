from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestK3dJaegerExposure(unittest.TestCase):
    def test_jaeger_query_service_is_loadbalancer(self) -> None:
        manifest = (REPO_ROOT / "deploy" / "k8s" / "v57" / "jaeger.yaml").read_text(encoding="utf-8")
        self.assertRegex(
            manifest,
            re.compile(
                r"kind:\s*Service.*?name:\s*jaeger-query.*?spec:\s*.*?type:\s*LoadBalancer",
                re.DOTALL,
            ),
        )

    def test_v58_overlay_keeps_user_facing_jaeger_service_as_loadbalancer(self) -> None:
        overlay = (REPO_ROOT / "deploy" / "k8s" / "v58" / "jaeger-ui-overlay.yaml").read_text(encoding="utf-8")
        self.assertRegex(
            overlay,
            re.compile(
                r"kind:\s*Service.*?name:\s*jaeger-query.*?spec:\s*.*?type:\s*LoadBalancer",
                re.DOTALL,
            ),
        )

    def test_k3d_cluster_config_exposes_fixed_jaeger_port_on_loadbalancer(self) -> None:
        config = (REPO_ROOT / "deploy" / "k3d" / "v56-cluster.yaml").read_text(encoding="utf-8")
        self.assertIn("ports:", config)
        self.assertIn("port: 16686:16686", config)
        self.assertRegex(
            config,
            re.compile(r"port:\s*16686:16686.*?nodeFilters:\s*.*?loadbalancer", re.DOTALL),
        )

    def test_harness_preloads_tracing_stack_images(self) -> None:
        from e2e_k3d_tests import _harness

        image_refs = {image_ref for image_ref, _expected_ref in _harness._PRELOAD_IMAGES}
        self.assertIn("jaegertracing/all-in-one:latest", image_refs)
        self.assertIn("otel/opentelemetry-collector-contrib:latest", image_refs)
        self.assertIn("openagentic/jaeger-ui-proxy:v58", image_refs)


if __name__ == "__main__":
    unittest.main()
