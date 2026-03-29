from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from e2e_k3d_tests._harness import (
    AGENT_A_NODE,
    authoritative_repo_root,
    build_dispatcher,
    current_git_head,
    ensure_cluster_ready,
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


class _ParentProvider:
    name = "k3d-actor-parent"

    def __init__(self, *, agent_name: str, child_prompt: str) -> None:
        self._agent_name = agent_name
        self._child_prompt = child_prompt
        self._calls = 0

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = (model, messages, tools, api_key)
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


class TestRemoteActorBasic(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_cluster_ready()

    async def test_remote_task_result_exposes_actor_identity_and_down_summary(self) -> None:
        workspace_root = authoritative_repo_root()
        with TemporaryDirectory() as td:
            store = FileSessionStore(root_dir=Path(td) / "sessions")
            options = OpenAgenticOptions(
                provider=_ParentProvider(agent_name="worker_actor", child_prompt="REPORT_NODE"),
                model="fake",
                api_key="x",
                cwd=str(workspace_root),
                project_dir=str(workspace_root),
                tools=default_tool_registry(),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                remote_task_dispatcher=build_dispatcher(),
                agents={
                    "worker_actor": AgentDefinition(
                        description="k3d actor worker",
                        prompt="REMOTE_K3D_DEF",
                        tools=("Read",),
                        executor=AgentExecutorDefinition(kind="k3s", node_name=AGENT_A_NODE),
                        workspace=AgentWorkspaceDefinition(mode="readonly"),
                    )
                },
            )

            events = []
            async for event in openagentic_sdk.query(prompt="dispatch remote actor task", options=options):
                events.append(event)

        task_result = next(
            event
            for event in events
            if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
        )
        output = task_result.output
        self.assertEqual(output["dispatch_mode"], "k3s")
        self.assertEqual(output["target_node"], AGENT_A_NODE)
        self.assertEqual(output["git_revision"], current_git_head())
        self.assertTrue(isinstance(output.get("execution_id"), str) and output["execution_id"])
        self.assertEqual(output["execution_id"], output["worker_execution_id"])
        self.assertEqual(output["down"]["reason_kind"], "normal")
        self.assertEqual(output["supervisor"]["action"], "accept_result")
        self.assertTrue(
            any(
                getattr(event, "type", None) == "result"
                and getattr(event, "agent_name", None) == "worker_actor"
                and AGENT_A_NODE in getattr(event, "final_text", "")
                for event in events
            )
        )


if __name__ == "__main__":
    unittest.main()
