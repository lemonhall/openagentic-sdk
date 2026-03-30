from __future__ import annotations

import unittest
from pathlib import Path


class TestV57OtelCollectorStartupOrder(unittest.TestCase):
    def test_otel_collector_waits_for_jaeger_otlp_before_start(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        manifest = (repo_root / "deploy" / "k8s" / "v57" / "otel-collector.yaml").read_text(encoding="utf-8")

        self.assertIn("initContainers:", manifest)
        self.assertIn("name: wait-for-jaeger-otlp", manifest)
        self.assertIn("image: jaegertracing/all-in-one:latest", manifest)
        self.assertIn("until nc -z jaeger-query.openagentic-v56.svc.cluster.local 4317", manifest)


if __name__ == "__main__":
    unittest.main()
