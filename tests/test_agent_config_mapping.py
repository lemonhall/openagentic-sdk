import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


class TestAgentConfigMapping(unittest.TestCase):
    def test_build_options_maps_local_and_k3s_agents(self) -> None:
        from openagentic_cli.config import build_options

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            (root / "opencode.jsonc").write_text(
                """
{
  "agent": {
    "local_worker": {
      "description": "Local worker",
      "prompt": "LOCAL PROMPT",
      "tools": ["Read", "Glob"],
      "executor": {
        "kind": "local"
      }
    },
    "worker_a": {
      "description": "Remote worker",
      "prompt": "REMOTE PROMPT",
      "tools": ["Read", "Grep"],
      "executor": {
        "kind": "k3s",
        "node_name": "node-a"
      },
      "workspace": {
        "mode": "readonly"
      },
      "worker": {
        "profile": "py311"
      }
    }
  }
}
""".strip(),
                encoding="utf-8",
            )

            env = {
                "RIGHTCODE_API_KEY": "x",
                "OPENCODE_TEST_HOME": str(root / "home"),
                "OPENAGENTIC_SDK_HOME": str(root / "home"),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                opts = build_options(
                    cwd=str(root),
                    project_dir=str(root),
                    permission_mode="prompt",
                )

        self.assertIn("local_worker", opts.agents)
        self.assertEqual(opts.agents["local_worker"].executor.kind, "local")
        self.assertEqual(tuple(opts.agents["local_worker"].tools), ("Read", "Glob"))

        self.assertIn("worker_a", opts.agents)
        remote = opts.agents["worker_a"]
        self.assertEqual(remote.executor.kind, "k3s")
        self.assertEqual(remote.executor.node_name, "node-a")
        self.assertEqual(remote.workspace.mode, "readonly")
        self.assertEqual(remote.worker.profile, "py311")
        self.assertEqual(remote.worker.max_concurrent_tasks, 3)
        self.assertEqual(tuple(remote.tools), ("Read", "Grep"))

    def test_k3s_agent_requires_node_name(self) -> None:
        from openagentic_cli.config import build_options

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            (root / "opencode.json").write_text(
                """
{
  "agent": {
    "broken_worker": {
      "description": "Broken",
      "prompt": "PROMPT",
      "executor": {
        "kind": "k3s"
      },
      "workspace": {
        "mode": "readonly"
      }
    }
  }
}
""".strip(),
                encoding="utf-8",
            )

            env = {
                "RIGHTCODE_API_KEY": "x",
                "OPENCODE_TEST_HOME": str(root / "home"),
                "OPENAGENTIC_SDK_HOME": str(root / "home"),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                with self.assertRaises(SystemExit) as cm:
                    build_options(
                        cwd=str(root),
                        project_dir=str(root),
                        permission_mode="prompt",
                    )

        self.assertIn("broken_worker", str(cm.exception))
        self.assertIn("node_name", str(cm.exception))

    def test_k3s_agent_worker_max_concurrent_tasks_is_configurable(self) -> None:
        from openagentic_cli.config import build_options

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            (root / "opencode.jsonc").write_text(
                """
{
  "agent": {
    "research": {
      "description": "Research",
      "prompt": "RESEARCH PROMPT",
      "tools": ["Read", "WebSearch"],
      "executor": {
        "kind": "k3s",
        "node_name": "node-a"
      },
      "workspace": {
        "mode": "readonly"
      },
      "worker": {
        "profile": "py311",
        "max_concurrent_tasks": 5
      }
    }
  }
}
""".strip(),
                encoding="utf-8",
            )

            env = {
                "RIGHTCODE_API_KEY": "x",
                "OPENCODE_TEST_HOME": str(root / "home"),
                "OPENAGENTIC_SDK_HOME": str(root / "home"),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                opts = build_options(
                    cwd=str(root),
                    project_dir=str(root),
                    permission_mode="prompt",
                )

        self.assertEqual(opts.agents["research"].worker.max_concurrent_tasks, 5)


if __name__ == "__main__":
    unittest.main()
