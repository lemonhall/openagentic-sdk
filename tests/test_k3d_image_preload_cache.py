from __future__ import annotations

import os
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


def _load_harness_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "e2e_k3d_tests" / "_harness.py"
    spec = spec_from_file_location("e2e_k3d_tests__harness", module_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestK3dImagePreloadCache(unittest.TestCase):
    def test_cached_image_archive_is_reused_when_fingerprint_matches(self) -> None:
        module = _load_harness_module()

        with TemporaryDirectory() as td, mock.patch.dict(os.environ, {"OA_K3D_STATE_DIR": td}, clear=False):
            tar_path = module._image_archive_path("python:3.12-slim")
            metadata_path = module._image_archive_metadata_path("python:3.12-slim")
            tar_path.parent.mkdir(parents=True, exist_ok=True)
            tar_path.write_text("cached", encoding="utf-8")
            metadata_path.write_text("sha256:abc", encoding="utf-8")

            with mock.patch.object(module, "_ensure_image_present") as ensure_present, mock.patch.object(
                module, "_local_image_fingerprint", return_value="sha256:abc"
            ), mock.patch.object(module, "_run") as run:
                result = module._ensure_image_archive("python:3.12-slim")

        self.assertEqual(result, tar_path)
        ensure_present.assert_called_once_with("python:3.12-slim")
        run.assert_not_called()

    def test_import_image_skips_copy_when_node_already_has_expected_ref(self) -> None:
        module = _load_harness_module()

        with mock.patch.object(module, "_node_has_image", return_value=True), mock.patch.object(module, "_run") as run:
            module._import_image(
                node_name="k3d-v56-openagentic-server-0",
                tar_path=Path("ignored.tar"),
                remote_tar_path="/tmp/ignored.tar",
                expected_ref="docker.io/library/python:3.12-slim",
            )

        run.assert_not_called()

    def test_docker_pull_env_falls_back_to_default_proxy_hint(self) -> None:
        module = _load_harness_module()

        with mock.patch.dict(os.environ, {}, clear=True):
            env = module._docker_pull_env()

        self.assertEqual(env["HTTP_PROXY"], "http://192.168.50.149:7897")
        self.assertEqual(env["HTTPS_PROXY"], "http://192.168.50.149:7897")


if __name__ == "__main__":
    unittest.main()
