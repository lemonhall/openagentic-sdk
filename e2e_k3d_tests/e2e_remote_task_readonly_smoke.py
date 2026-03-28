from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from e2e_k3d_tests._harness import (
    AGENT_A_NODE,
    build_dispatcher,
    current_git_head,
    ensure_cluster_ready,
    read_repo_text,
    repo_root,
)
from openagentic_sdk.options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkspaceDefinition,
    OpenAgenticOptions,
)
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.tools.defaults import default_tool_registry


class ParentTaskProvider:
    name = "k3d-smoke-parent"

    def __init__(self, *, agent_name: str, child_prompt: str) -> None:
        self._agent_name = agent_name
        self._child_prompt = child_prompt
        self._calls = 0

    async def complete(self, *, model, messages, tools=(), api_key=None):
        self._calls += 1
        if self._calls == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="call_task",
                        name="Task",
                        arguments={"agent": self._agent_name, "prompt": self._child_prompt},
                    )
                ],
                usage=None,
                raw=None,
            )
        return ModelOutput(assistant_text="parent ok", tool_calls=[], usage=None, raw=None)


class TestK3dRemoteTaskReadonlySmoke(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_cluster_ready()

    async def test_remote_worker_blocks_write_and_leaves_repo_unchanged(self) -> None:
        before = read_repo_text("README.md")

        with TemporaryDirectory() as td:
            store = FileSessionStore(root_dir=Path(td) / "sessions")
            agent_name = "worker_readonly"
            options = OpenAgenticOptions(
                provider=ParentTaskProvider(agent_name=agent_name, child_prompt="TRY_WRITE README.md"),
                model="fake",
                api_key="x",
                cwd=str(repo_root()),
                project_dir=str(repo_root()),
                tools=default_tool_registry(),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                remote_task_dispatcher=build_dispatcher(),
                agents={
                    agent_name: AgentDefinition(
                        description="k3d smoke readonly worker",
                        prompt="REMOTE_K3D_DEF",
                        tools=("Read", "Write"),
                        executor=AgentExecutorDefinition(kind="k3s", node_name=AGENT_A_NODE),
                        workspace=AgentWorkspaceDefinition(mode="readonly"),
                    )
                },
            )

            events = []
            async for event in openagentic_sdk.query(prompt="dispatch readonly task", options=options):
                events.append(event)

        after = read_repo_text("README.md")

        task_results = [e for e in events if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", None) == "call_task"]
        self.assertTrue(task_results)
        out = task_results[-1].output
        self.assertEqual(out["dispatch_mode"], "k3s")
        self.assertEqual(out["target_node"], AGENT_A_NODE)
        self.assertEqual(out["git_revision"], current_git_head())

        denied = [
            event
            for event in events
            if getattr(event, "type", None) == "tool.result"
            and getattr(event, "tool_use_id", None) == "write_1"
            and getattr(event, "agent_name", None) == agent_name
        ]
        self.assertTrue(denied)
        self.assertTrue(denied[-1].is_error)
        self.assertEqual(denied[-1].error_type, "ToolNotAllowed")

        child_results = [e for e in events if getattr(e, "type", None) == "result" and getattr(e, "agent_name", None) == agent_name]
        self.assertTrue(child_results)
        self.assertIn("WRITE_BLOCKED", child_results[-1].final_text)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
