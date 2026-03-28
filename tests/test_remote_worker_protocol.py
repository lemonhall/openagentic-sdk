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
from openagentic_sdk.providers.base import ModelOutput
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.subagents.remote_types import RemoteTaskRequest
from openagentic_sdk.tools.registry import ToolRegistry


class RemoteWorkerChildProvider:
    name = "fake-child"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        user_text = next((m.get("content") for m in messages if m.get("role") == "user"), "")
        if isinstance(user_text, str) and user_text.startswith("REMOTE_CHILD_DEF:"):
            return ModelOutput(assistant_text="remote worker ok", tool_calls=[], usage=None, raw=None)
        return ModelOutput(assistant_text="unexpected", tool_calls=[], usage=None, raw=None)


class TestRemoteWorkerProtocol(unittest.IsolatedAsyncioTestCase):
    async def test_inprocess_remote_worker_runs_child_runtime_and_sets_metadata(self) -> None:
        from openagentic_sdk.subagents.remote_worker import InProcessRemoteTaskWorker

        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root / "session_home")
            definition = AgentDefinition(
                description="remote child",
                prompt="REMOTE_CHILD_DEF: follow instructions",
                tools=("Read",),
                executor=AgentExecutorDefinition(kind="k3s", node_name="node-a"),
                workspace=AgentWorkspaceDefinition(mode="readonly"),
            )
            base_options = OpenAgenticOptions(
                provider=RemoteWorkerChildProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={"worker_remote": definition},
            )
            worker = InProcessRemoteTaskWorker(base_options=base_options, session_store=store)
            request = RemoteTaskRequest(
                parent_session_id="a" * 32,
                parent_tool_use_id="call_task",
                agent_name="worker_remote",
                prompt="Do remote child work",
                definition=definition,
                cwd=str(root),
                project_dir=str(root),
                git_revision="abc1234",
            )

            handle = await worker.dispatch(request)
            child_events = []
            async for event in handle.events:
                child_events.append(event)
            self.assertEqual(handle.target_node, "node-a")
            self.assertEqual(handle.git_revision, "abc1234")
            self.assertEqual(handle.child_session_id, worker.last_child_session_id)
            self.assertTrue(child_events)
            self.assertTrue(all(getattr(event, "agent_name", None) == "worker_remote" for event in child_events))
            self.assertTrue(all(getattr(event, "parent_tool_use_id", None) == "call_task" for event in child_events))
            self.assertEqual(getattr(child_events[-1], "final_text", None), "remote worker ok")

            meta = store.read_meta_record(handle.child_session_id)
            self.assertEqual(meta["metadata"]["parent_session_id"], "a" * 32)
            self.assertEqual(meta["metadata"]["parent_tool_use_id"], "call_task")
            self.assertEqual(meta["metadata"]["agent_name"], "worker_remote")
            self.assertEqual(meta["metadata"]["dispatch_mode"], "k3s")
            self.assertEqual(meta["metadata"]["target_node"], "node-a")
            self.assertEqual(meta["metadata"]["git_revision"], "abc1234")


if __name__ == "__main__":
    unittest.main()
