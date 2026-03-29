import asyncio
import json
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
from openagentic_sdk.serialization import event_to_dict
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.subagents.actor_lifecycle import ActorDownEvent
from openagentic_sdk.subagents.actor_protocol import ActorEnvelope
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


class FlakyTransportRemoteDispatcher:
    def __init__(self) -> None:
        self.requests = []

    async def dispatch(self, request):
        self.requests.append(request)
        attempt = len(self.requests)

        async def _events():
            if attempt == 1:
                raise ConnectionResetError("socket reset by peer")
            yield Result(
                final_text="remote child done after retry",
                session_id="d" * 32,
                agent_name=request.agent_name,
                parent_tool_use_id=request.parent_tool_use_id,
            )

        return request.make_handle(
            child_session_id="d" * 32,
            target_node=request.definition.executor.node_name or "",
            git_revision=request.git_revision,
            worker_execution_id=f"exec-retry-{attempt}",
            events=_events(),
        )


class RemoteWorkerErrorDispatcher:
    def __init__(self) -> None:
        self.requests = []

    async def dispatch(self, request):
        self.requests.append(request)

        async def _events():
            from openagentic_sdk.subagents.actor_lifecycle import RemoteWorkerStreamError

            raise RemoteWorkerStreamError(error_type="ValueError", error_message="bad parse")
            yield  # pragma: no cover

        return request.make_handle(
            child_session_id="e" * 32,
            target_node=request.definition.executor.node_name or "",
            git_revision=request.git_revision,
            worker_execution_id="exec-worker-error",
            events=_events(),
        )


class DispatchFailRemoteDispatcher:
    def __init__(self) -> None:
        self.requests = []

    async def dispatch(self, request):
        self.requests.append(request)
        raise ConnectionResetError("socket reset during dispatch")


class AbortableRemoteDispatcher:
    def __init__(self) -> None:
        self.requests = []
        self.child_started = asyncio.Event()
        self._abort_requested = asyncio.Event()
        self.abort_calls = 0

    async def dispatch(self, request):
        self.requests.append(request)

        async def _envelopes():
            yield ActorEnvelope(
                protocol_version="v1",
                message_id="msg-remote-abort-1",
                execution_id="exec-remote-abort",
                sender_actor_id="worker_remote/exec-remote-abort",
                recipient_actor_id="host",
                mailbox="child_events",
                seq=1,
                kind="child_event",
                payload={
                    "event": event_to_dict(
                        AssistantMessage(
                            text="remote child waiting",
                            agent_name=request.agent_name,
                            parent_tool_use_id=request.parent_tool_use_id,
                        )
                    )
                },
                ts=1.0,
            )
            self.child_started.set()
            await self._abort_requested.wait()
            yield ActorEnvelope(
                protocol_version="v1",
                message_id="msg-remote-abort-2",
                execution_id="exec-remote-abort",
                sender_actor_id="worker_remote/exec-remote-abort",
                recipient_actor_id="host",
                mailbox="child_events",
                seq=2,
                kind="down",
                payload=ActorDownEvent(
                    execution_id="exec-remote-abort",
                    actor_id="worker_remote/exec-remote-abort",
                    reason_kind="aborted",
                    reason_detail="host_abort",
                    final_state="aborted",
                    dispatch_mode="k3s",
                    child_session_id="f" * 32,
                    target_node=request.definition.executor.node_name or "",
                    worker_execution_id="exec-remote-abort",
                ).to_payload(),
                ts=2.0,
            )

        async def _abort() -> None:
            self.abort_calls += 1
            self._abort_requested.set()

        return request.make_handle(
            child_session_id="f" * 32,
            target_node=request.definition.executor.node_name or "",
            git_revision=request.git_revision,
            worker_execution_id="exec-remote-abort",
            envelopes=_envelopes(),
            aborter=_abort,
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


class RemoteTaskAbortProvider:
    name = "fake-remote-abort"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = tools
        _ = api_key
        user_text = next((m.get("content") for m in messages if m.get("role") == "user"), "")

        if isinstance(user_text, str) and user_text.startswith("PARENT_REMOTE_ABORT:") and not any(
            m.get("role") == "tool" for m in messages
        ):
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
    async def test_k3s_agent_http_dispatcher_reconnects_same_remote_execution_without_redispatch(self) -> None:
        from openagentic_sdk.subagents.remote_http import HttpRemoteTaskDispatcher

        dispatch_bodies: list[dict[str, object]] = []
        replay_queries: list[dict[str, list[str]]] = []
        send_bodies: list[dict[str, object]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                if self.path == "/dispatch":
                    length = int(self.headers.get("Content-Length") or "0")
                    payload = json.loads((self.rfile.read(length) if length > 0 else b"{}").decode("utf-8"))
                    if isinstance(payload, dict):
                        dispatch_bodies.append(payload)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                    self.send_header("X-OA-Child-Session-ID", "b" * 32)
                    self.send_header("X-OA-Target-Node", "node-a")
                    self.send_header("X-OA-Git-Revision", "rev-http-reconnect")
                    self.send_header("X-OA-Worker-Execution-ID", "exec-http-reconnect")
                    self.send_header("X-OA-Execution-ID", "exec-http-reconnect")
                    self.end_headers()
                    first = _child_event_envelope(
                        execution_id="exec-http-reconnect",
                        seq=1,
                        actor_id="worker_remote/exec-http-reconnect",
                        parent_actor_id="host",
                        event=AssistantMessage(
                            text="remote child says hi",
                            agent_name="worker_remote",
                            parent_tool_use_id="call_task",
                        ),
                    )
                    self.wfile.write(json.dumps(first.to_dict(), ensure_ascii=False).encode("utf-8") + b"\n")
                    self.wfile.flush()
                    self.connection.shutdown(1)
                    return

                if self.path == "/send":
                    length = int(self.headers.get("Content-Length") or "0")
                    payload = json.loads((self.rfile.read(length) if length > 0 else b"{}").decode("utf-8"))
                    if isinstance(payload, dict):
                        send_bodies.append(payload)
                    self.send_response(202)
                    self.end_headers()
                    return

                self.send_response(404)
                self.end_headers()

            def do_GET(self):  # noqa: N802
                from urllib.parse import parse_qs, urlparse

                parsed = urlparse(self.path)
                if parsed.path != "/stream":
                    self.send_response(404)
                    self.end_headers()
                    return
                query = parse_qs(parsed.query)
                replay_queries.append(query)
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.end_headers()
                second = _child_event_envelope(
                    execution_id="exec-http-reconnect",
                    seq=2,
                    actor_id="worker_remote/exec-http-reconnect",
                    parent_actor_id="host",
                    event=Result(
                        final_text="remote child done after reconnect",
                        session_id="b" * 32,
                        agent_name="worker_remote",
                        parent_tool_use_id="call_task",
                    ),
                )
                down = _down_envelope(
                    execution_id="exec-http-reconnect",
                    seq=3,
                    actor_id="worker_remote/exec-http-reconnect",
                    parent_actor_id="host",
                    down=ActorDownEvent(
                        execution_id="exec-http-reconnect",
                        actor_id="worker_remote/exec-http-reconnect",
                        reason_kind="normal",
                        reason_detail="stop_reason=end",
                        final_state="exited",
                        dispatch_mode="k3s",
                        child_session_id="b" * 32,
                        target_node="node-a",
                        worker_execution_id="exec-http-reconnect",
                    ),
                )
                for envelope in (second, down):
                    self.wfile.write(json.dumps(envelope.to_dict(), ensure_ascii=False).encode("utf-8") + b"\n")
                    self.wfile.flush()

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                _ = (format, args)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as td:
                sandbox = Path(td)
                root = sandbox / "repo"
                root.mkdir()
                self._init_git_repo(root)
                store = FileSessionStore(root_dir=sandbox / "session_home")

                options = OpenAgenticOptions(
                    provider=RemoteTaskProvider(),
                    model="fake",
                    api_key="x",
                    cwd=str(root),
                    tools=ToolRegistry([]),
                    permission_gate=PermissionGate(permission_mode="bypass"),
                    session_store=store,
                    remote_task_dispatcher=HttpRemoteTaskDispatcher(
                        base_url=f"http://127.0.0.1:{httpd.server_address[1]}",
                    ),
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
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5.0)

        self.assertEqual(len(dispatch_bodies), 1)
        self.assertTrue(isinstance(dispatch_bodies[0].get("worker_execution_id"), str) and dispatch_bodies[0].get("worker_execution_id"))
        self.assertTrue(replay_queries)
        self.assertEqual(replay_queries[0].get("execution_id"), ["exec-http-reconnect"])
        self.assertEqual(replay_queries[0].get("after_seq"), ["1"])
        self.assertEqual(replay_queries[0].get("mailbox"), ["child_events"])
        self.assertTrue(send_bodies)
        self.assertEqual(send_bodies[0].get("kind"), "ack")
        task_result = next(
            event for event in events if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
        )
        self.assertFalse(task_result.is_error)
        self.assertEqual(task_result.output["execution_id"], "exec-http-reconnect")
        self.assertEqual(task_result.output["worker_execution_id"], "exec-http-reconnect")
        self.assertEqual(task_result.output["final_text"], "remote child done after reconnect")
        self.assertEqual(getattr(events[-1], "final_text", None), "parent remote ok")

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
        self.assertFalse(task_results[-1].is_error)
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
        self.assertEqual(task_result.output["down"]["reason_kind"], "child_exit_error")
        self.assertEqual(getattr(events[-1], "final_text", None), "parent remote saw task failure")

    async def test_k3s_agent_retries_once_on_transport_loss(self) -> None:
        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            dispatcher = FlakyTransportRemoteDispatcher()

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
                        worker=AgentWorkerDefinition(profile="py311", supervisor_policy="retry_once_on_transport_loss"),
                    )
                },
            )

            import openagentic_sdk

            events = []
            async for e in openagentic_sdk.query(prompt="PARENT_REMOTE: delegate", options=options):
                events.append(e)

        self.assertEqual(len(dispatcher.requests), 2)
        task_result = next(
            event for event in events if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
        )
        self.assertFalse(task_result.is_error)
        self.assertEqual(task_result.output["final_text"], "remote child done after retry")

    async def test_k3s_agent_does_not_retry_remote_worker_error_as_transport_loss(self) -> None:
        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            dispatcher = RemoteWorkerErrorDispatcher()

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
                        worker=AgentWorkerDefinition(profile="py311", supervisor_policy="retry_once_on_transport_loss"),
                    )
                },
            )

            import openagentic_sdk

            events = []
            async for e in openagentic_sdk.query(prompt="PARENT_REMOTE_NO_OUTPUT: delegate", options=options):
                events.append(e)

        self.assertEqual(len(dispatcher.requests), 1)
        task_result = next(
            event for event in events if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
        )
        self.assertTrue(task_result.is_error)
        self.assertEqual(task_result.output["down"]["reason_kind"], "remote_worker_error")

    async def test_k3s_dispatch_failure_surfaces_structured_down_and_supervisor(self) -> None:
        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            dispatcher = DispatchFailRemoteDispatcher()

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

        self.assertEqual(len(dispatcher.requests), 1)
        task_result = next(
            event for event in events if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
        )
        self.assertTrue(task_result.is_error)
        self.assertEqual(task_result.output["down"]["reason_kind"], "transport_lost")
        self.assertEqual(task_result.output["supervisor"]["action"], "fail_parent_tool_use")
        self.assertEqual(getattr(events[-1], "final_text", None), "parent remote saw task failure")

    async def test_k3s_agent_surfaces_structured_down_when_host_aborts_remote_child(self) -> None:
        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            dispatcher = AbortableRemoteDispatcher()
            abort_event = asyncio.Event()

            options = OpenAgenticOptions(
                provider=RemoteTaskAbortProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                remote_task_dispatcher=dispatcher,
                abort_event=abort_event,
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

            async def _run_query() -> None:
                async for e in openagentic_sdk.query(prompt="PARENT_REMOTE_ABORT: delegate", options=options):
                    events.append(e)

            task = asyncio.create_task(_run_query())
            await asyncio.wait_for(dispatcher.child_started.wait(), timeout=1.0)
            abort_event.set()
            await asyncio.wait_for(task, timeout=2.0)

        self.assertEqual(len(dispatcher.requests), 1)
        self.assertEqual(dispatcher.abort_calls, 1)
        task_result = next(
            event for event in events if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
        )
        self.assertTrue(task_result.is_error)
        self.assertEqual(task_result.output["down"]["reason_kind"], "aborted")
        self.assertEqual(getattr(events[-1], "final_text", None), "parent remote saw task failure")

    def _init_git_repo(self, root: Path) -> None:
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
        (root / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, text=True)


def _child_event_envelope(
    *,
    execution_id: str,
    seq: int,
    actor_id: str,
    parent_actor_id: str,
    event: AssistantMessage | Result,
) -> ActorEnvelope:
    return ActorEnvelope(
        protocol_version="v1",
        message_id=f"msg-{seq}",
        execution_id=execution_id,
        sender_actor_id=actor_id,
        recipient_actor_id=parent_actor_id,
        mailbox="child_events",
        seq=seq,
        kind="child_event",
        payload={"event": event_to_dict(event)},
        ts=float(seq),
    )


def _down_envelope(
    *,
    execution_id: str,
    seq: int,
    actor_id: str,
    parent_actor_id: str,
    down: ActorDownEvent,
) -> ActorEnvelope:
    return ActorEnvelope(
        protocol_version="v1",
        message_id=f"msg-{seq}",
        execution_id=execution_id,
        sender_actor_id=actor_id,
        recipient_actor_id=parent_actor_id,
        mailbox="child_events",
        seq=seq,
        kind="down",
        payload=down.to_payload(),
        ts=float(seq),
    )


if __name__ == "__main__":
    unittest.main()
