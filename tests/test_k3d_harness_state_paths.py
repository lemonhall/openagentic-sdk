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


class TestK3dHarnessStatePaths(unittest.TestCase):
    def test_default_state_root_uses_persistent_cache_dir(self) -> None:
        module = _load_harness_module()

        with mock.patch.dict(os.environ, {}, clear=False):
            state_root = module._k3d_state_root()

        self.assertEqual(state_root, Path.home() / ".cache" / "openagentic-k3d")

    def test_authoritative_mirror_path_is_stable_under_state_dir_override(self) -> None:
        module = _load_harness_module()

        with TemporaryDirectory() as td, mock.patch.dict(os.environ, {"OA_K3D_STATE_DIR": td}, clear=False):
            mirror = module._authoritative_mirror_root()
            cluster_head = module._cluster_head_path()

        state_root = Path(td)
        self.assertEqual(mirror, state_root / "mirrors" / "openagentic-v56-authoritative")
        self.assertEqual(cluster_head, state_root / "state" / "openagentic-v56-cluster-head.txt")

    def test_cluster_recreate_is_not_required_when_only_head_drifts(self) -> None:
        module = _load_harness_module()

        with mock.patch.object(module, "_cluster_exists", return_value=True), mock.patch.object(
            module, "_cluster_head", return_value="old-head"
        ), mock.patch.object(module, "_cluster_config_signature", return_value="same-signature"):
            self.assertFalse(
                module._cluster_needs_recreate(desired_head="new-head", desired_config_signature="same-signature")
            )

    def test_cluster_recreate_is_required_when_config_signature_drifts(self) -> None:
        module = _load_harness_module()

        with mock.patch.object(module, "_cluster_exists", return_value=True), mock.patch.object(
            module, "_cluster_head", return_value="same-head"
        ), mock.patch.object(module, "_cluster_config_signature", return_value="old-signature"):
            self.assertTrue(module._cluster_needs_recreate(desired_head="same-head", desired_config_signature="new-signature"))

    def test_cluster_recreate_is_not_required_when_head_and_signature_match(self) -> None:
        module = _load_harness_module()

        with mock.patch.object(module, "_cluster_exists", return_value=True), mock.patch.object(
            module, "_cluster_head", return_value="same-head"
        ), mock.patch.object(module, "_cluster_config_signature", return_value="same-signature"):
            self.assertFalse(
                module._cluster_needs_recreate(desired_head="same-head", desired_config_signature="same-signature")
            )


if __name__ == "__main__":
    unittest.main()
