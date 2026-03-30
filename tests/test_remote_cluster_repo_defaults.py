from __future__ import annotations

import json
import unittest
from pathlib import Path


class TestRemoteClusterRepoDefaults(unittest.TestCase):
    def test_repo_remote_config_defaults_to_gpt_5_4(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        payload = json.loads((repo_root / "openagentic.remote.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["providers"]["rightcode"]["default_model"], "gpt-5.4")
        self.assertEqual(payload["host"]["model"], "gpt-5.4")
        self.assertEqual(payload["agents"]["research"]["model"], "gpt-5.4")
        self.assertEqual(payload["agents"]["writer"]["model"], "gpt-5.4")

    def test_repo_remote_example_config_defaults_to_gpt_5_4(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        payload = json.loads((repo_root / "openagentic.remote.example.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["providers"]["rightcode"]["default_model"], "gpt-5.4")
        self.assertEqual(payload["host"]["model"], "gpt-5.4")
        self.assertEqual(payload["agents"]["research"]["model"], "gpt-5.4")
        self.assertEqual(payload["agents"]["writer"]["model"], "gpt-5.4")


if __name__ == "__main__":
    unittest.main()
