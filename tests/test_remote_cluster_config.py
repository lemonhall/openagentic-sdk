from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class TestRemoteClusterConfig(unittest.TestCase):
    def test_load_remote_cluster_bootstrap_resolves_host_and_agent_provider_specs(self) -> None:
        from openagentic_sdk.remote_cluster_config import load_remote_cluster_bootstrap

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "openagentic.remote.json").write_text(
                json.dumps(
                    {
                        "providers": {
                            "rightcode": {
                                "kind": "openai_responses",
                                "base_url_env": "RIGHTCODE_BASE_URL",
                                "api_key_env": "RIGHTCODE_API_KEY",
                                "default_model": "gpt-5.4",
                            }
                        },
                        "host": {
                            "provider": "rightcode",
                            "model": "gpt-5.4",
                        },
                        "agents": {
                            "research": {
                                "description": "research worker",
                                "prompt": "You are a research worker.",
                                "tools": ["Read", "WebSearch"],
                                "provider": "rightcode",
                                "model": "gpt-5.4",
                                "executor": {"kind": "k3s", "node_name": "node-a"},
                                "workspace": {"mode": "readonly"},
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            bootstrap = load_remote_cluster_bootstrap(
                repo_root=root,
                env={
                    "RIGHTCODE_BASE_URL": "https://rightcode.example.test/v1",
                    "RIGHTCODE_API_KEY": "rc-secret",
                },
            )

        self.assertTrue(bootstrap.self_check.provider_ready)
        self.assertEqual(bootstrap.config_source, str(Path(td) / "openagentic.remote.json"))
        self.assertEqual(type(bootstrap.host_provider).__name__, "OpenAIResponsesProvider")
        self.assertEqual(bootstrap.host_provider_spec.provider_name, "rightcode")
        self.assertEqual(bootstrap.host_provider_spec.api_key, "rc-secret")
        self.assertEqual(bootstrap.host_model, "gpt-5.4")
        self.assertEqual(tuple(sorted(bootstrap.provider_profiles)), ("rightcode",))

        research = bootstrap.agents["research"]
        self.assertEqual(research.model, "gpt-5.4")
        self.assertEqual(research.executor.kind, "k3s")
        self.assertEqual(research.executor.node_name, "node-a")
        self.assertEqual(research.workspace.mode, "readonly")
        self.assertEqual(research.provider_spec.provider_name, "rightcode")
        self.assertEqual(research.provider_spec.kind, "openai_responses")
        self.assertEqual(research.provider_spec.base_url, "https://rightcode.example.test/v1")
        self.assertEqual(research.provider_spec.api_key, "rc-secret")

    def test_load_remote_cluster_bootstrap_marks_missing_provider_env_not_ready(self) -> None:
        from openagentic_sdk.remote_cluster_config import load_remote_cluster_bootstrap

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "openagentic.remote.json").write_text(
                json.dumps(
                    {
                        "providers": {
                            "rightcode": {
                                "kind": "openai_responses",
                                "base_url_env": "RIGHTCODE_BASE_URL",
                                "api_key_env": "RIGHTCODE_API_KEY",
                                "default_model": "gpt-5.4",
                            }
                        },
                        "host": {"provider": "rightcode"},
                        "agents": {},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            bootstrap = load_remote_cluster_bootstrap(
                repo_root=root,
                env={
                    "RIGHTCODE_BASE_URL": "https://rightcode.example.test/v1",
                },
            )

        self.assertFalse(bootstrap.self_check.provider_ready)
        self.assertTrue(bootstrap.self_check.errors)
        self.assertIn("RIGHTCODE_API_KEY", "\n".join(bootstrap.self_check.errors))

    def test_build_provider_from_spec_supports_openai_responses(self) -> None:
        from openagentic_sdk.remote_cluster_config import ResolvedRemoteProviderSpec, build_provider_from_spec

        spec = ResolvedRemoteProviderSpec(
            provider_name="rightcode",
            kind="openai_responses",
            base_url="https://rightcode.example.test/v1",
            api_key="rc-secret",
        )

        provider = build_provider_from_spec(spec)

        self.assertEqual(type(provider).__name__, "OpenAIResponsesProvider")
        self.assertEqual(getattr(provider, "name", None), "rightcode")
        self.assertEqual(getattr(provider, "base_url", None), "https://rightcode.example.test/v1")
        self.assertEqual(getattr(provider, "timeout_s", None), 180.0)
        self.assertEqual(getattr(provider, "max_retries", None), 2)
        self.assertEqual(getattr(provider, "retry_backoff_s", None), 0.5)


if __name__ == "__main__":
    unittest.main()
