from __future__ import annotations

import asyncio
import json
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from urllib import request as urllib_request

from openagentic_sdk.events import AssistantMessage, Result
from openagentic_sdk.options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkspaceDefinition,
    OpenAgenticOptions,
)
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput
from openagentic_sdk.remote_cluster_config import ResolvedRemoteProviderSpec
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.subagents.actor_lifecycle import ActorDownEvent
from openagentic_sdk.subagents.actor_protocol import ActorEnvelope
from openagentic_sdk.subagents.remote_types import RemoteTaskRequest
from openagentic_sdk.tools.registry import ToolRegistry


class HttpWorkerChildProvider:
    name = "http-child"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        user_text = next((m.get("content") for m in messages if m.get("role") == "user"), "")
        if isinstance(user_text, str) and user_text.startswith("REMOTE_HTTP_DEF:"):
            return ModelOutput(assistant_text="remote http ok", tool_calls=[], usage=None, raw=None)
        return ModelOutput(assistant_text="unexpected", tool_calls=[], usage=None, raw=None)


class BlockingHttpWorkerChildProvider:
    name = "http-child-blocking"

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = tools
        _ = api_key
        user_text = next((m.get("content") for m in messages if m.get("role") == "user"), "")
        if not isinstance(user_text, str) or not user_text.startswith("REMOTE_HTTP_DEF:"):
            return ModelOutput(assistant_text="unexpected", tool_calls=[], usage=None, raw=None)
        with self._lock:
            self.active += 1
            if self.active > self.max_active:
                self.max_active = self.active
            self.started.set()
        await asyncio.to_thread(self.release.wait)
        with self._lock:
            self.active -= 1
        return ModelOutput(assistant_text="remote http ok", tool_calls=[], usage=None, raw=None)


class FailingBaseProvider:
    name = "failing-base-provider"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = (model, messages, tools, api_key)
        raise AssertionError("worker fell back to base_options.provider instead of request.provider_spec")


class TestRemoteHttpTransport(unittest.IsolatedAsyncioTestCase):
    async def test_http_remote_worker_server_forwards_close_to_child_handle(self) -> None:
        from openagentic_sdk.subagents.remote_http import HttpRemoteActorTransport, RemoteTaskHttpWorkerServer

        close_event = threading.Event()

        class ClosableRemoteTaskWorker:
            def __init__(self, *, base_options, session_store) -> None:
                _ = (base_options, session_store)

            async def dispatch(self, request):
                async def _envelopes():
                    yield ActorEnvelope(
                        protocol_version="v1",
                        message_id="msg-close-down",
                        execution_id="exec-close-1",
                        sender_actor_id="worker_remote/exec-close-1",
                        recipient_actor_id="host",
                        mailbox="child_events",
                        seq=1,
                        kind="down",
                        payload=ActorDownEvent(
                            execution_id="exec-close-1",
                            actor_id="worker_remote/exec-close-1",
                            reason_kind="normal",
                            reason_detail="stop_reason=end",
                            final_state="exited",
                            dispatch_mode="k3s",
                            child_session_id="d" * 32,
                            target_node=request.definition.executor.node_name or "",
                            worker_execution_id="exec-close-1",
                        ).to_payload(),
                        ts=1.0,
                    )

                async def _close() -> None:
                    close_event.set()

                return request.make_handle(
                    child_session_id="d" * 32,
                    target_node=request.definition.executor.node_name or "",
                    git_revision=request.git_revision,
                    worker_execution_id="exec-close-1",
                    envelopes=_envelopes(),
                    closer=_close,
                )

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            repo_root = sandbox / "repo"
            repo_root.mkdir()
            self._init_git_repo(repo_root)
            git_revision = self._git_head(repo_root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            definition = AgentDefinition(
                description="remote child",
                prompt="REMOTE_HTTP_DEF: follow instructions",
                tools=("Read",),
                executor=AgentExecutorDefinition(kind="k3s", node_name="node-http"),
                workspace=AgentWorkspaceDefinition(mode="readonly"),
            )
            base_options = OpenAgenticOptions(
                provider=HttpWorkerChildProvider(),
                model="fake",
                api_key="x",
                cwd=str(repo_root),
                project_dir=str(repo_root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={"worker_remote": definition},
            )
            with mock.patch("openagentic_sdk.subagents.remote_http.InProcessRemoteTaskWorker", ClosableRemoteTaskWorker):
                worker_server = RemoteTaskHttpWorkerServer(
                    base_options=base_options,
                    session_store=store,
                    repo_root=str(repo_root),
                    node_name="node-http",
                    host="127.0.0.1",
                    port=0,
                )
                httpd = worker_server.make_server()
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                try:
                    transport = HttpRemoteActorTransport(base_url=f"http://127.0.0.1:{httpd.server_address[1]}")
                    request = RemoteTaskRequest(
                        parent_session_id="d" * 32,
                        parent_tool_use_id="call_task",
                        agent_name="worker_remote",
                        prompt="Do remote child work",
                        definition=definition,
                        cwd=str(repo_root),
                        project_dir=str(repo_root),
                        git_revision=git_revision,
                    )

                    handle = await transport.spawn(request)
                    _ = [event async for event in handle.events]
                    await asyncio.wait_for(handle.down_future, timeout=1.0)
                    await transport.close(handle)
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(timeout=5.0)

        self.assertTrue(close_event.wait(timeout=1.0))

    async def test_http_remote_worker_stream_defaults_to_child_events_when_mailbox_is_omitted(self) -> None:
        from openagentic_sdk.subagents.remote_http import RemoteTaskHttpWorkerServer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            repo_root = sandbox / "repo"
            repo_root.mkdir()
            self._init_git_repo(repo_root)
            git_revision = self._git_head(repo_root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            definition = AgentDefinition(
                description="remote child",
                prompt="REMOTE_HTTP_DEF: follow instructions",
                tools=("Read",),
                executor=AgentExecutorDefinition(kind="k3s", node_name="node-http"),
                workspace=AgentWorkspaceDefinition(mode="readonly"),
            )
            base_options = OpenAgenticOptions(
                provider=HttpWorkerChildProvider(),
                model="fake",
                api_key="x",
                cwd=str(repo_root),
                project_dir=str(repo_root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={"worker_remote": definition},
            )
            worker_server = RemoteTaskHttpWorkerServer(
                base_options=base_options,
                session_store=store,
                repo_root=str(repo_root),
                node_name="node-http",
                host="127.0.0.1",
                port=0,
            )
            httpd = worker_server.make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                dispatch_request = urllib_request.Request(
                    url=f"http://127.0.0.1:{httpd.server_address[1]}/dispatch",
                    data=json.dumps(
                        {
                            "parent_session_id": "a" * 32,
                            "parent_tool_use_id": "call_task",
                            "agent_name": "worker_remote",
                            "prompt": "Do remote child work",
                            "definition": {
                                "description": definition.description,
                                "prompt": definition.prompt,
                                "tools": list(definition.tools),
                                "provider_spec": None,
                                "model": definition.model,
                                "executor": {
                                    "kind": definition.executor.kind,
                                    "node_name": definition.executor.node_name,
                                },
                                "workspace": {"mode": definition.workspace.mode},
                                "worker": {
                                    "profile": definition.worker.profile,
                                    "image": definition.worker.image,
                                    "max_concurrent_tasks": definition.worker.max_concurrent_tasks,
                                    "supervisor_policy": definition.worker.supervisor_policy,
                                },
                            },
                            "cwd": str(repo_root),
                            "project_dir": str(repo_root),
                            "git_revision": git_revision,
                            "worker_execution_id": "exec-default-mailbox",
                        },
                        ensure_ascii=False,
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                dispatch_response = urllib_request.urlopen(dispatch_request, timeout=10.0)
                try:
                    execution_id = dispatch_response.headers.get("X-OA-Execution-ID") or ""
                    self.assertTrue(execution_id)
                    first = self._read_envelope_line(dispatch_response)
                finally:
                    dispatch_response.close()

                replay_response = urllib_request.urlopen(
                    urllib_request.Request(
                        url=f"http://127.0.0.1:{httpd.server_address[1]}/stream?execution_id={execution_id}&after_seq={first.seq}",
                        method="GET",
                    ),
                    timeout=10.0,
                )
                try:
                    replayed = self._read_all_envelopes(replay_response)
                finally:
                    replay_response.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5.0)

        self.assertTrue(replayed)
        self.assertTrue(all(envelope.seq > first.seq for envelope in replayed))
        self.assertEqual(replayed[-1].kind, "down")

    async def test_http_remote_worker_server_forwards_control_envelope_to_child_handle(self) -> None:
        from openagentic_sdk.subagents.remote_http import HttpRemoteActorTransport, RemoteTaskHttpWorkerServer

        sent_event = threading.Event()
        sent_envelopes: list[ActorEnvelope] = []

        class ControllableRemoteTaskWorker:
            def __init__(self, *, base_options, session_store) -> None:
                _ = (base_options, session_store)

            async def dispatch(self, request):
                async def _envelopes():
                    await asyncio.to_thread(sent_event.wait)
                    yield ActorEnvelope(
                        protocol_version="v1",
                        message_id="msg-down",
                        execution_id="exec-control-1",
                        sender_actor_id="worker_remote/exec-control-1",
                        recipient_actor_id="host",
                        mailbox="child_events",
                        seq=1,
                        kind="down",
                        payload=ActorDownEvent(
                            execution_id="exec-control-1",
                            actor_id="worker_remote/exec-control-1",
                            reason_kind="normal",
                            reason_detail="stop_reason=end",
                            final_state="exited",
                            dispatch_mode="k3s",
                            child_session_id="f" * 32,
                            target_node=request.definition.executor.node_name or "",
                            worker_execution_id="exec-control-1",
                        ).to_payload(),
                        ts=1.0,
                    )

                async def _send(envelope: ActorEnvelope) -> None:
                    sent_envelopes.append(envelope)
                    sent_event.set()

                return request.make_handle(
                    child_session_id="f" * 32,
                    target_node=request.definition.executor.node_name or "",
                    git_revision=request.git_revision,
                    worker_execution_id="exec-control-1",
                    envelopes=_envelopes(),
                    sender=_send,
                )

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            repo_root = sandbox / "repo"
            repo_root.mkdir()
            self._init_git_repo(repo_root)
            git_revision = self._git_head(repo_root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            definition = AgentDefinition(
                description="remote child",
                prompt="REMOTE_HTTP_DEF: follow instructions",
                tools=("Read",),
                executor=AgentExecutorDefinition(kind="k3s", node_name="node-http"),
                workspace=AgentWorkspaceDefinition(mode="readonly"),
            )
            base_options = OpenAgenticOptions(
                provider=HttpWorkerChildProvider(),
                model="fake",
                api_key="x",
                cwd=str(repo_root),
                project_dir=str(repo_root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={"worker_remote": definition},
            )
            with mock.patch("openagentic_sdk.subagents.remote_http.InProcessRemoteTaskWorker", ControllableRemoteTaskWorker):
                worker_server = RemoteTaskHttpWorkerServer(
                    base_options=base_options,
                    session_store=store,
                    repo_root=str(repo_root),
                    node_name="node-http",
                    host="127.0.0.1",
                    port=0,
                )
                httpd = worker_server.make_server()
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                try:
                    transport = HttpRemoteActorTransport(base_url=f"http://127.0.0.1:{httpd.server_address[1]}")
                    request = RemoteTaskRequest(
                        parent_session_id="f" * 32,
                        parent_tool_use_id="call_task",
                        agent_name="worker_remote",
                        prompt="Do remote child work",
                        definition=definition,
                        cwd=str(repo_root),
                        project_dir=str(repo_root),
                        git_revision=git_revision,
                    )

                    handle = await transport.spawn(request)
                    control = ActorEnvelope(
                        protocol_version="v1",
                        message_id="msg-control",
                        execution_id="exec-control-1",
                        sender_actor_id="host",
                        recipient_actor_id="worker_remote/exec-control-1",
                        mailbox="control",
                        seq=1,
                        kind="control",
                        payload={"op": "ping"},
                        ts=1.0,
                    )
                    await transport.send(handle, control)
                    child_events = [event async for event in handle.events]
                    down = await asyncio.wait_for(handle.down_future, timeout=1.0)
                    await transport.close(handle)
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(timeout=5.0)

        self.assertTrue(sent_event.wait(timeout=1.0))
        self.assertEqual(len(sent_envelopes), 1)
        self.assertEqual(child_events, [])
        self.assertEqual(sent_envelopes[0].kind, "control")
        self.assertEqual(sent_envelopes[0].payload, {"op": "ping"})
        self.assertEqual(down.reason_kind, "normal")

    async def test_http_remote_worker_dispatcher_surfaces_child_stream_failure_without_json_corruption(self) -> None:
        from openagentic_sdk.subagents.remote_http import HttpRemoteTaskDispatcher, RemoteTaskHttpWorkerServer

        class FailingStreamRemoteTaskWorker:
            def __init__(self, *, base_options, session_store) -> None:
                _ = (base_options, session_store)

            async def dispatch(self, request):
                async def _events():
                    yield AssistantMessage(
                        text="remote child started",
                        agent_name=request.agent_name,
                        parent_tool_use_id=request.parent_tool_use_id,
                    )
                    raise ValueError("boom from child stream")

                return request.make_handle(
                    child_session_id="c" * 32,
                    target_node=request.definition.executor.node_name or "",
                    git_revision=request.git_revision,
                    worker_execution_id="exec-failing-stream",
                    events=_events(),
                )

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            repo_root = sandbox / "repo"
            repo_root.mkdir()
            self._init_git_repo(repo_root)
            git_revision = self._git_head(repo_root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            definition = AgentDefinition(
                description="remote child",
                prompt="REMOTE_HTTP_DEF: follow instructions",
                tools=("Read",),
                executor=AgentExecutorDefinition(kind="k3s", node_name="node-http"),
                workspace=AgentWorkspaceDefinition(mode="readonly"),
            )
            base_options = OpenAgenticOptions(
                provider=HttpWorkerChildProvider(),
                model="fake",
                api_key="x",
                cwd=str(repo_root),
                project_dir=str(repo_root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={"worker_remote": definition},
            )
            with mock.patch("openagentic_sdk.subagents.remote_http.InProcessRemoteTaskWorker", FailingStreamRemoteTaskWorker):
                worker_server = RemoteTaskHttpWorkerServer(
                    base_options=base_options,
                    session_store=store,
                    repo_root=str(repo_root),
                    node_name="node-http",
                    host="127.0.0.1",
                    port=0,
                )
                httpd = worker_server.make_server()
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                try:
                    dispatcher = HttpRemoteTaskDispatcher(base_url=f"http://127.0.0.1:{httpd.server_address[1]}")
                    request = RemoteTaskRequest(
                        parent_session_id="e" * 32,
                        parent_tool_use_id="call_task",
                        agent_name="worker_remote",
                        prompt="Do remote child work",
                        definition=definition,
                        cwd=str(repo_root),
                        project_dir=str(repo_root),
                        git_revision=git_revision,
                    )

                    handle = await dispatcher.dispatch(request)
                    child_events = [event async for event in handle.events]
                    down = await asyncio.wait_for(handle.down_future, timeout=1.0)
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(timeout=5.0)

        self.assertEqual(len(child_events), 1)
        self.assertEqual(getattr(child_events[0], "text", None), "remote child started")
        self.assertEqual(down.reason_kind, "remote_worker_error")

    async def test_http_remote_worker_dispatcher_survives_idle_gaps_after_headers(self) -> None:
        from openagentic_sdk.subagents.remote_http import HttpRemoteTaskDispatcher, RemoteTaskHttpWorkerServer

        class IdleGapRemoteTaskWorker:
            def __init__(self, *, base_options, session_store) -> None:
                _ = (base_options, session_store)

            async def dispatch(self, request):
                async def _events():
                    yield AssistantMessage(
                        text="remote child started",
                        agent_name=request.agent_name,
                        parent_tool_use_id=request.parent_tool_use_id,
                    )
                    await asyncio.sleep(0.25)
                    yield Result(
                        final_text="remote child finished after idle gap",
                        session_id="b" * 32,
                        agent_name=request.agent_name,
                        parent_tool_use_id=request.parent_tool_use_id,
                    )

                return request.make_handle(
                    child_session_id="b" * 32,
                    target_node=request.definition.executor.node_name or "",
                    git_revision=request.git_revision,
                    worker_execution_id="exec-idle-gap",
                    events=_events(),
                )

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            repo_root = sandbox / "repo"
            repo_root.mkdir()
            self._init_git_repo(repo_root)
            git_revision = self._git_head(repo_root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            definition = AgentDefinition(
                description="remote child",
                prompt="REMOTE_HTTP_DEF: follow instructions",
                tools=("Read",),
                executor=AgentExecutorDefinition(kind="k3s", node_name="node-http"),
                workspace=AgentWorkspaceDefinition(mode="readonly"),
            )
            base_options = OpenAgenticOptions(
                provider=HttpWorkerChildProvider(),
                model="fake",
                api_key="x",
                cwd=str(repo_root),
                project_dir=str(repo_root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={"worker_remote": definition},
            )
            with mock.patch("openagentic_sdk.subagents.remote_http.InProcessRemoteTaskWorker", IdleGapRemoteTaskWorker):
                worker_server = RemoteTaskHttpWorkerServer(
                    base_options=base_options,
                    session_store=store,
                    repo_root=str(repo_root),
                    node_name="node-http",
                    host="127.0.0.1",
                    port=0,
                )
                httpd = worker_server.make_server()
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                try:
                    dispatcher = HttpRemoteTaskDispatcher(
                        base_url=f"http://127.0.0.1:{httpd.server_address[1]}",
                        timeout_s=0.1,
                    )
                    request = RemoteTaskRequest(
                        parent_session_id="d" * 32,
                        parent_tool_use_id="call_task",
                        agent_name="worker_remote",
                        prompt="Do remote child work",
                        definition=definition,
                        cwd=str(repo_root),
                        project_dir=str(repo_root),
                        git_revision=git_revision,
                    )

                    handle = await dispatcher.dispatch(request)
                    child_events = [event async for event in handle.events]
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(timeout=5.0)

        self.assertTrue(child_events)
        self.assertEqual(getattr(child_events[-1], "final_text", None), "remote child finished after idle gap")

    async def test_http_remote_worker_roundtrips_child_events_and_metadata(self) -> None:
        from openagentic_sdk.subagents.remote_http import HttpRemoteTaskDispatcher, RemoteTaskHttpWorkerServer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            repo_root = sandbox / "repo"
            repo_root.mkdir()
            self._init_git_repo(repo_root)
            git_revision = self._git_head(repo_root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            definition = AgentDefinition(
                description="remote child",
                prompt="REMOTE_HTTP_DEF: follow instructions",
                tools=("Read",),
                executor=AgentExecutorDefinition(kind="k3s", node_name="node-http"),
                workspace=AgentWorkspaceDefinition(mode="readonly"),
            )
            base_options = OpenAgenticOptions(
                provider=HttpWorkerChildProvider(),
                model="fake",
                api_key="x",
                cwd=str(repo_root),
                project_dir=str(repo_root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={"worker_remote": definition},
            )
            worker_server = RemoteTaskHttpWorkerServer(
                base_options=base_options,
                session_store=store,
                repo_root=str(repo_root),
                node_name="node-http",
                host="127.0.0.1",
                port=0,
            )
            httpd = worker_server.make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                dispatcher = HttpRemoteTaskDispatcher(base_url=f"http://127.0.0.1:{httpd.server_address[1]}")
                request = RemoteTaskRequest(
                    parent_session_id="a" * 32,
                    parent_tool_use_id="call_task",
                    agent_name="worker_remote",
                    prompt="Do remote child work",
                    definition=definition,
                    cwd=str(repo_root),
                    project_dir=str(repo_root),
                    git_revision=git_revision,
                )

                handle = await dispatcher.dispatch(request)
                child_events = []
                async for event in handle.events:
                    child_events.append(event)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5.0)

        self.assertEqual(handle.target_node, "node-http")
        self.assertEqual(handle.git_revision, git_revision)
        self.assertTrue(handle.child_session_id)
        self.assertTrue(handle.worker_execution_id)
        self.assertTrue(child_events)
        self.assertTrue(all(getattr(event, "agent_name", None) == "worker_remote" for event in child_events))
        self.assertTrue(all(getattr(event, "parent_tool_use_id", None) == "call_task" for event in child_events))
        self.assertEqual(getattr(child_events[-1], "final_text", None), "remote http ok")

    async def test_http_remote_worker_limits_concurrency_and_queues_excess_requests(self) -> None:
        from openagentic_sdk.subagents.remote_http import HttpRemoteTaskDispatcher, RemoteTaskHttpWorkerServer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            repo_root = sandbox / "repo"
            repo_root.mkdir()
            self._init_git_repo(repo_root)
            git_revision = self._git_head(repo_root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            provider = BlockingHttpWorkerChildProvider()
            definition = AgentDefinition(
                description="remote child",
                prompt="REMOTE_HTTP_DEF: follow instructions",
                tools=("Read",),
                executor=AgentExecutorDefinition(kind="k3s", node_name="node-http"),
                workspace=AgentWorkspaceDefinition(mode="readonly"),
            )
            base_options = OpenAgenticOptions(
                provider=provider,
                model="fake",
                api_key="x",
                cwd=str(repo_root),
                project_dir=str(repo_root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={"worker_remote": definition},
            )
            worker_server = RemoteTaskHttpWorkerServer(
                base_options=base_options,
                session_store=store,
                repo_root=str(repo_root),
                node_name="node-http",
                host="127.0.0.1",
                port=0,
            )
            httpd = worker_server.make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                dispatcher = HttpRemoteTaskDispatcher(base_url=f"http://127.0.0.1:{httpd.server_address[1]}")

                async def _dispatch_one(i: int):
                    request = RemoteTaskRequest(
                        parent_session_id=f"{i:032d}"[-32:],
                        parent_tool_use_id=f"call_task_{i}",
                        agent_name="worker_remote",
                        prompt=f"Do remote child work {i}",
                        definition=definition,
                        cwd=str(repo_root),
                        project_dir=str(repo_root),
                        git_revision=git_revision,
                    )
                    handle = await dispatcher.dispatch(request)
                    return [event async for event in handle.events]

                tasks = [asyncio.create_task(_dispatch_one(i)) for i in range(4)]
                await asyncio.sleep(1.0)
                self.assertEqual(provider.max_active, 3)
                self.assertFalse(all(task.done() for task in tasks))
                provider.release.set()
                results = await asyncio.gather(*tasks)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5.0)

        self.assertEqual(provider.max_active, 3)
        self.assertEqual(len(results), 4)
        for child_events in results:
            self.assertEqual(getattr(child_events[-1], "final_text", None), "remote http ok")

    async def test_http_remote_worker_uses_provider_spec_from_request_definition(self) -> None:
        from openagentic_sdk.subagents.remote_http import HttpRemoteTaskDispatcher, RemoteTaskHttpWorkerServer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            repo_root = sandbox / "repo"
            repo_root.mkdir()
            self._init_git_repo(repo_root)
            git_revision = self._git_head(repo_root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            provider_httpd = self._make_responses_stub_server(
                assistant_text="provider spec ok",
                expected_auth_header="Bearer rc-secret",
            )
            provider_thread = threading.Thread(target=provider_httpd.serve_forever, daemon=True)
            provider_thread.start()
            try:
                provider_spec = ResolvedRemoteProviderSpec(
                    provider_name="rightcode",
                    kind="openai_responses",
                    base_url=f"http://127.0.0.1:{provider_httpd.server_address[1]}",
                    api_key="rc-secret",
                )
                definition = AgentDefinition(
                    description="remote child",
                    prompt="REMOTE_HTTP_DEF: follow instructions",
                    tools=("Read",),
                    provider_spec=provider_spec,
                    model="gpt-5.2",
                    executor=AgentExecutorDefinition(kind="k3s", node_name="node-http"),
                    workspace=AgentWorkspaceDefinition(mode="readonly"),
                )
                base_options = OpenAgenticOptions(
                    provider=FailingBaseProvider(),
                    model="fake",
                    api_key="wrong-base-key",
                    cwd=str(repo_root),
                    project_dir=str(repo_root),
                    tools=ToolRegistry([]),
                    permission_gate=PermissionGate(permission_mode="bypass"),
                    session_store=store,
                    agents={"worker_remote": definition},
                )
                worker_server = RemoteTaskHttpWorkerServer(
                    base_options=base_options,
                    session_store=store,
                    repo_root=str(repo_root),
                    node_name="node-http",
                    host="127.0.0.1",
                    port=0,
                )
                httpd = worker_server.make_server()
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                try:
                    dispatcher = HttpRemoteTaskDispatcher(base_url=f"http://127.0.0.1:{httpd.server_address[1]}")
                    request = RemoteTaskRequest(
                        parent_session_id="c" * 32,
                        parent_tool_use_id="call_task",
                        agent_name="worker_remote",
                        prompt="Do remote child work",
                        definition=definition,
                        cwd=str(repo_root),
                        project_dir=str(repo_root),
                        git_revision=git_revision,
                    )

                    handle = await dispatcher.dispatch(request)
                    child_events = [event async for event in handle.events]
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(timeout=5.0)
            finally:
                provider_httpd.shutdown()
                provider_httpd.server_close()
                provider_thread.join(timeout=5.0)

        self.assertTrue(child_events)
        self.assertEqual(getattr(child_events[-1], "final_text", None), "provider spec ok")

    def _init_git_repo(self, root: Path) -> None:
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
        (root / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, text=True)

    def _git_head(self, root: Path) -> str:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True)
        return proc.stdout.strip()

    def _make_responses_stub_server(
        self,
        *,
        assistant_text: str,
        expected_auth_header: str | None = None,
    ) -> ThreadingHTTPServer:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                if self.path != "/responses":
                    self.send_response(404)
                    self.end_headers()
                    return
                if expected_auth_header is not None and self.headers.get("Authorization") != expected_auth_header:
                    self.send_response(401)
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length") or "0")
                payload = json.loads((self.rfile.read(length) if length > 0 else b"{}").decode("utf-8"))
                if payload.get("stream") is True:
                    chunks = [
                        'data: {"type":"response.created","response":{"id":"resp_test"}}\n\n',
                        f'data: {json.dumps({"type": "response.output_item.added", "output_index": 0, "item": {"id": "msg_1", "type": "message"}}, ensure_ascii=False)}\n\n',
                        f'data: {json.dumps({"type": "response.output_text.delta", "item_id": "msg_1", "delta": assistant_text}, ensure_ascii=False)}\n\n',
                        'data: {"type":"response.completed","response":{"id":"resp_test","usage":{"total_tokens":10}}}\n\n',
                        "data: [DONE]\n\n",
                    ]
                    raw = "".join(chunks).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return

                raw = json.dumps(
                    {
                        "id": "resp_test",
                        "output": [
                            {
                                "type": "message",
                                "content": [{"type": "output_text", "text": assistant_text}],
                            }
                        ],
                        "usage": {"total_tokens": 10},
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                _ = (format, args)

        return ThreadingHTTPServer(("127.0.0.1", 0), Handler)

    def _read_envelope_line(self, response) -> ActorEnvelope:  # noqa: ANN001
        line = response.readline()
        if not line:
            raise AssertionError("expected at least one actor envelope")
        return ActorEnvelope.from_dict(json.loads(line.decode("utf-8")))

    def _read_all_envelopes(self, response) -> list[ActorEnvelope]:  # noqa: ANN001
        items: list[ActorEnvelope] = []
        while True:
            line = response.readline()
            if not line:
                return items
            text = line.decode("utf-8").strip()
            if not text:
                continue
            items.append(ActorEnvelope.from_dict(json.loads(text)))


if __name__ == "__main__":
    unittest.main()
