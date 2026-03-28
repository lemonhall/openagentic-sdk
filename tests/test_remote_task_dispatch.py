import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.events import AssistantMessage, Result
from openagentic_sdk.options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkerDefinition,
    AgentWorkspaceDefinition,
    OpenAgenticOptions,
)
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.tools.registry import ToolRegistry


class RemoteTaskProvider:
    name = "fake"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        user_text = next((m.get("content") for m in messages if m.get("role") == "user"), "")

        if isinstance(user_text, str) and user_text.startswith("PARENT_REMOTE:") and not any(m.get("role") == "tool" for m in messages):
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="call_task",
                        name="Task",
                        arguments={"agent": "worker_remote", "prompt": "Do remote child work"},
                    )
                ],
                usage=None,
                raw=None,
            )

        if any(m.get("role") == "tool" for m in messages):
            return ModelOutput(assistant_text="parent remote ok", tool_calls=[], usage=None, raw=None)

        return ModelOutput(assistant_text="unexpected", tool_calls=[], usage=None, raw=None)


class RecordingRemoteDispatcher:
    def __init__(self) -> None:
        self.requests = []

    async def dispatch(self, request):
        self.requests.append(request)

        async def _events():
            yield AssistantMessage(
                text="remote child says hi",
                agent_name=request.agent_name,
                parent_tool_use_id=request.parent_tool_use_id,
            )
            yield Result(
                final_text="remote child done",
                session_id="b" * 32,
                agent_name=request.agent_name,
                parent_tool_use_id=request.parent_tool_use_id,
            )

        return request.make_handle(
            child_session_id="b" * 32,
            target_node=request.definition.executor.node_name or "",
            git_revision=request.git_revision,
            worker_execution_id="exec-123",
            events=_events(),
        )


class NoOutputRemoteDispatcher:
    def __init__(self) -> None:
        self.requests = []

    async def dispatch(self, request):
        self.requests.append(request)

        async def _events():
            yield Result(
                final_text="",
                session_id="c" * 32,
                stop_reason="no_output",
                agent_name=request.agent_name,
                parent_tool_use_id=request.parent_tool_use_id,
            )

        return request.make_handle(
            child_session_id="c" * 32,
            target_node=request.definition.executor.node_name or "",
            git_revision=request.git_revision,
            worker_execution_id="exec-no-output",
            events=_events(),
        )


class RemoteTaskNoOutputProvider:
    name = "fake-no-output"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = tools
        _ = api_key
        user_text = next((m.get("content") for m in messages if m.get("role") == "user"), "")

        if isinstance(user_text, str) and user_text.startswith("PARENT_REMOTE_NO_OUTPUT:") and not any(m.get("role") == "tool" for m in messages):
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="call_task",
                        name="Task",
                        arguments={"agent": "worker_remote", "prompt": "Do remote child work"},
                    )
                ],
                usage=None,
                raw=None,
            )

        if any(m.get("role") == "tool" for m in messages):
            tool_payload = next((m.get("content") for m in reversed(messages) if m.get("role") == "tool"), "")
            tool_obj = json.loads(tool_payload) if isinstance(tool_payload, str) and tool_payload else {}
            if isinstance(tool_obj, dict) and tool_obj.get("is_error") is True:
                return ModelOutput(assistant_text="parent remote saw task failure", tool_calls=[], usage=None, raw=None)
            return ModelOutput(assistant_text="parent remote unexpectedly saw success", tool_calls=[], usage=None, raw=None)

        return ModelOutput(assistant_text="unexpected", tool_calls=[], usage=None, raw=None)


class TestRemoteTaskDispatch(unittest.IsolatedAsyncioTestCase):
    async def test_k3s_agent_uses_remote_dispatcher_and_streams_child_events(self) -> None:
        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            dispatcher = RecordingRemoteDispatcher()

            options = OpenAgenticOptions(
                provider=RemoteTaskProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                remote_task_dispatcher=dispatcher,
                agents={
                    "worker_remote": AgentDefinition(
                        description="remote child",
                        prompt="REMOTE_CHILD_DEF",
                        tools=("Read", "Grep"),
                        executor=AgentExecutorDefinition(kind="k3s", node_name="node-a"),
                        workspace=AgentWorkspaceDefinition(mode="readonly"),
                        worker=AgentWorkerDefinition(profile="py311"),
                    )
                },
            )

            import openagentic_sdk

            events = []
            async for e in openagentic_sdk.query(prompt="PARENT_REMOTE: delegate", options=options):
                events.append(e)

        self.assertEqual(len(dispatcher.requests), 1)
        request = dispatcher.requests[0]
        self.assertEqual(request.agent_name, "worker_remote")
        self.assertEqual(request.parent_tool_use_id, "call_task")
        self.assertEqual(request.definition.executor.kind, "k3s")
        self.assertEqual(request.definition.executor.node_name, "node-a")
        self.assertTrue(isinstance(request.git_revision, str) and len(request.git_revision) >= 7)

        child_events = [e for e in events if getattr(e, "agent_name", None) == "worker_remote"]
        self.assertTrue(child_events, "expected remote child events in parent stream")
        self.assertTrue(all(getattr(e, "parent_tool_use_id", None) == "call_task" for e in child_events))

        task_results = [e for e in events if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", None) == "call_task"]
        self.assertTrue(task_results)
        out = task_results[-1].output
        self.assertEqual(out["dispatch_mode"], "k3s")
        self.assertEqual(out["target_node"], "node-a")
        self.assertEqual(out["child_session_id"], "b" * 32)
        self.assertEqual(out["final_text"], "remote child done")
        self.assertEqual(out["git_revision"], request.git_revision)
        self.assertEqual(out["worker_execution_id"], "exec-123")

    async def test_k3s_agent_surfaces_child_no_output_as_error(self) -> None:
        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            dispatcher = NoOutputRemoteDispatcher()

            options = OpenAgenticOptions(
                provider=RemoteTaskNoOutputProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                remote_task_dispatcher=dispatcher,
                agents={
                    "worker_remote": AgentDefinition(
                        description="remote child",
                        prompt="REMOTE_CHILD_DEF",
                        tools=("Read", "Grep"),
                        executor=AgentExecutorDefinition(kind="k3s", node_name="node-a"),
                        workspace=AgentWorkspaceDefinition(mode="readonly"),
                        worker=AgentWorkerDefinition(profile="py311"),
                    )
                },
            )

            import openagentic_sdk

            events = []
            async for e in openagentic_sdk.query(prompt="PARENT_REMOTE_NO_OUTPUT: delegate", options=options):
                events.append(e)

        task_results = [e for e in events if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", None) == "call_task"]
        self.assertTrue(task_results)
        task_result = task_results[-1]
        self.assertTrue(task_result.is_error)
        self.assertEqual(task_result.error_type, "SubagentNoOutput")
        self.assertEqual(task_result.output["dispatch_mode"], "k3s")
        self.assertEqual(task_result.output["target_node"], "node-a")
        self.assertEqual(task_result.output["child_stop_reason"], "no_output")
        self.assertEqual(getattr(events[-1], "final_text", None), "parent remote saw task failure")

    def _init_git_repo(self, root: Path) -> None:
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
        (root / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
