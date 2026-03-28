from __future__ import annotations

import subprocess
import threading
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_cli.repl import run_chat
from openagentic_cli.style import StyleConfig
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


class _BridgeProvider:
    name = "bridge-provider"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = tools
        _ = api_key
        user_messages = [m.get("content") for m in messages if m.get("role") == "user"]
        user_text = user_messages[-1] if user_messages else ""
        has_tool_output = any(m.get("role") == "tool" for m in messages)
        if isinstance(user_text, str) and user_text.startswith("delegate") and not has_tool_output:
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
        if has_tool_output:
            return ModelOutput(assistant_text="host delegated", tool_calls=[], usage=None, raw=None)
        return ModelOutput(assistant_text="host ok", tool_calls=[], usage=None, raw=None)


class _BridgeOnlyProvider:
    name = "bridge-only"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = messages
        _ = tools
        _ = api_key
        raise AssertionError("local bridge provider should never be called in remote chat mode")


class _RecordingRemoteDispatcher:
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


class TestRemoteChatBridge(unittest.IsolatedAsyncioTestCase):
    async def test_cluster_chat_client_streams_events_and_preserves_resume(self) -> None:
        from openagentic_sdk.server.cluster_chat_client import ClusterChatClient
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            dispatcher = _RecordingRemoteDispatcher()
            options = OpenAgenticOptions(
                provider=_BridgeProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                project_dir=str(root),
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
            httpd = ClusterChatHostServer(base_options=options, session_store=store).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                client = ClusterChatClient(base_url=f"http://127.0.0.1:{httpd.server_address[1]}", timeout_s=1.0)

                first_events = [e async for e in client.query(prompt="hello")]
                self.assertTrue(first_events)
                self.assertEqual(getattr(first_events[-1], "type", None), "result")
                first_session_id = self._session_id_from(first_events)
                self.assertIsInstance(first_session_id, str)

                second_events = [e async for e in client.query(prompt="delegate now", session_id=first_session_id)]
                self.assertEqual(self._session_id_from(second_events), first_session_id)
                child_events = [e for e in second_events if getattr(e, "agent_name", None) == "worker_remote"]
                self.assertTrue(child_events, "expected child Task events to flow back through remote chat bridge")

                task_results = [
                    e
                    for e in second_events
                    if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", None) == "call_task"
                ]
                self.assertTrue(task_results)
                out = task_results[-1].output
                self.assertEqual(out["dispatch_mode"], "k3s")
                self.assertEqual(out["target_node"], "node-a")
                self.assertEqual(out["worker_execution_id"], "exec-123")
            finally:
                httpd.shutdown()
                httpd.server_close()

    async def test_run_chat_uses_remote_bridge_when_base_url_is_configured(self) -> None:
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            dispatcher = _RecordingRemoteDispatcher()
            host_options = OpenAgenticOptions(
                provider=_BridgeProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                project_dir=str(root),
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
            httpd = ClusterChatHostServer(base_options=host_options, session_store=store).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                client_options = OpenAgenticOptions(
                    provider=_BridgeOnlyProvider(),
                    model="bridge",
                    cwd=str(root),
                    project_dir=str(root),
                    permission_gate=PermissionGate(permission_mode="bypass"),
                    remote_chat_base_url=f"http://127.0.0.1:{httpd.server_address[1]}",
                    remote_chat_timeout_s=1.0,
                )
                stdin = StringIO("delegate now\n/exit\n")
                stdout = StringIO()
                rc = await run_chat(
                    client_options,
                    color_config=StyleConfig(color="never"),
                    debug=False,
                    stdin=stdin,
                    stdout=stdout,
                )
                rendered = stdout.getvalue()
                self.assertEqual(rc, 0)
                self.assertIn("remote child says hi", rendered)
                self.assertIn("host delegated", rendered)
            finally:
                httpd.shutdown()
                httpd.server_close()

    async def test_cluster_chat_client_fails_fast_when_host_is_unreachable(self) -> None:
        from openagentic_sdk.server.cluster_chat_client import ClusterChatClient

        client = ClusterChatClient(base_url="http://127.0.0.1:9", timeout_s=0.2)
        with self.assertRaises(RuntimeError):
            async for _ in client.query(prompt="hello"):
                pass

    def _init_git_repo(self, root: Path) -> None:
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
        (root / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, text=True)

    def _session_id_from(self, events: list[object]) -> str:
        for event in events:
            if getattr(event, "type", None) == "system.init":
                session_id = getattr(event, "session_id", None)
                if isinstance(session_id, str) and session_id:
                    return session_id
        raise AssertionError("system.init missing from remote chat events")


if __name__ == "__main__":
    unittest.main()
