from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestK3dRealRuntimeImage(unittest.TestCase):
    def test_runtime_dockerfile_exists_and_pins_required_packages(self) -> None:
        dockerfile = REPO_ROOT / "deploy" / "k8s" / "v61" / "openagentic-python-runtime.Dockerfile"
        text = dockerfile.read_text(encoding="utf-8")

        self.assertIn("FROM python:3.12-slim", text)
        self.assertIn("protobuf<6", text)
        self.assertIn("opentelemetry-api<2", text)
        self.assertIn("opentelemetry-sdk<2", text)
        self.assertIn("opentelemetry-exporter-otlp-proto-http<2", text)
        self.assertNotIn(".openagentic-wheelhouse", text)

    def test_real_manifests_use_prebaked_runtime_image_and_do_not_install_at_startup(self) -> None:
        host_manifest = (REPO_ROOT / "deploy" / "k8s" / "v56" / "chat-host-real.template.yaml").read_text(
            encoding="utf-8"
        )
        worker_manifest = (REPO_ROOT / "deploy" / "k3d" / "v56-workers-real.template.yaml").read_text(
            encoding="utf-8"
        )

        for text in (host_manifest, worker_manifest):
            self.assertIn("openagentic/python-runtime:v61", text)
            self.assertNotIn("python -m pip install", text)
            self.assertNotIn(".openagentic-wheelhouse", text)


if __name__ == "__main__":
    unittest.main()
