import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkspaceDefinition,
    OpenAgenticOptions,
)
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.subagents.remote_types import RemoteTaskRequest
from openagentic_sdk.tools.defaults import default_tool_registry


class WriteAttemptProvider:
    name = "fake-write"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, model, messages, tools=(), api_key=None):
        self.calls += 1
        if self.calls == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="write_1",
                        name="Write",
                        arguments={"file_path": "x.txt", "content": "boom"},
                    )
                ],
                usage=None,
                raw=None,
            )
        return ModelOutput(assistant_text="done", tool_calls=[], usage=None, raw=None)


class TestRemoteReadonlyGuard(unittest.IsolatedAsyncioTestCase):
    async def test_remote_tool_allowlist_strips_write_edit_and_bash(self) -> None:
        from openagentic_sdk.subagents.readonly_policy import build_remote_allowed_tools

        definition = AgentDefinition(
            description="remote child",
            prompt="PROMPT",
            tools=("Read", "Write", "Edit", "Bash", "NotebookEdit", "Grep"),
            executor=AgentExecutorDefinition(kind="k3s", node_name="node-a"),
            workspace=AgentWorkspaceDefinition(mode="readonly"),
        )

        allowed = build_remote_allowed_tools(definition)

        self.assertEqual(tuple(allowed), ("Read", "Grep"))

    async def test_remote_worker_denies_write_tool_even_if_agent_declares_it(self) -> None:
        from openagentic_sdk.subagents.remote_worker import InProcessRemoteTaskWorker

        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root / "session_home")
            definition = AgentDefinition(
                description="remote child",
                prompt="PROMPT",
                tools=("Read", "Write"),
                executor=AgentExecutorDefinition(kind="k3s", node_name="node-a"),
                workspace=AgentWorkspaceDefinition(mode="readonly"),
            )
            base_options = OpenAgenticOptions(
                provider=WriteAttemptProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                tools=default_tool_registry(),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={"worker_remote": definition},
            )
            worker = InProcessRemoteTaskWorker(base_options=base_options, session_store=store)
            request = RemoteTaskRequest(
                parent_session_id="a" * 32,
                parent_tool_use_id="call_task",
                agent_name="worker_remote",
                prompt="Attempt write",
                definition=definition,
                cwd=str(root),
                project_dir=str(root),
                git_revision="abc1234",
            )

            handle = await worker.dispatch(request)
            child_events = []
            async for event in handle.events:
                child_events.append(event)

        denied = [
            event
            for event in child_events
            if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "write_1"
        ]
        self.assertTrue(denied)
        self.assertTrue(denied[-1].is_error)
        self.assertEqual(denied[-1].error_type, "ToolNotAllowed")


if __name__ == "__main__":
    unittest.main()
