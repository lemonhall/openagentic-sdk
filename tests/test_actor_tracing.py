from __future__ import annotations

import asyncio
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.events import AssistantMessage, Result
from openagentic_sdk.options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkspaceDefinition,
    OpenAgenticOptions,
)
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.subagents.actor_lifecycle import ActorDownEvent
from openagentic_sdk.subagents.actor_protocol import ActorEnvelope
from openagentic_sdk.subagents.remote_types import RemoteTaskRequest
from openagentic_sdk.tools.registry import ToolRegistry
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


class _TaskProvider:
    name = "fake"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = tools
        _ = api_key
        user_text = next((m.get("content") for m in messages if m.get("role") == "user"), "")

        if isinstance(user_text, str) and user_text.startswith("PARENT_TRACE:") and not any(
            m.get("role") == "tool" for m in messages
        ):
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="call_task",
                        name="Task",
                        arguments={"agent": "worker", "prompt": "Do child work"},
                    )
                ],
                usage=None,
                raw=None,
            )

        if isinstance(user_text, str) and user_text.startswith("CHILD_TRACE:"):
            return ModelOutput(assistant_text="child traced", tool_calls=[], usage=None, raw=None)

        if any(m.get("role") == "tool" for m in messages):
            return ModelOutput(assistant_text="parent traced", tool_calls=[], usage=None, raw=None)

        return ModelOutput(assistant_text="unexpected", tool_calls=[], usage=None, raw=None)


class TestActorTracing(unittest.IsolatedAsyncioTestCase):
    async def test_task_records_local_actor_trace_with_stable_attributes(self) -> None:
        import openagentic_sdk
        from openagentic_sdk.sessions.store import FileSessionStore

        tracing, exporter = _build_tracing(service_name="oa-test-host")
        try:
            with TemporaryDirectory() as td:
                root = Path(td)
                store = FileSessionStore(root_dir=root)
                options = OpenAgenticOptions(
                    provider=_TaskProvider(),
                    model="fake",
                    api_key="x",
                    cwd=str(root),
                    tools=ToolRegistry([]),
                    permission_gate=PermissionGate(permission_mode="bypass"),
                    session_store=store,
                    agents={
                        "worker": AgentDefinition(
                            description="child",
                            prompt="CHILD_TRACE: do the work",
                            tools=(),
                        )
                    },
                )
                options.runtime_state.actor_tracing = tracing

                events = []
                async for event in openagentic_sdk.query(prompt="PARENT_TRACE: delegate", options=options):
                    events.append(event)

            task_result = next(
                event
                for event in events
                if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
            )
            execution_id = task_result.output["execution_id"]
            spans = exporter.get_finished_spans()

            host_span = _find_span(spans, name="oa.task.execution", execution_id=execution_id)
            actor_span = _find_span(spans, name="oa.actor.execution", execution_id=execution_id, transport_kind="local")

            self.assertEqual(host_span.attributes["oa.execution.id"], execution_id)
            self.assertEqual(host_span.attributes["oa.agent.name"], "worker")
            self.assertEqual(host_span.attributes["oa.dispatch.mode"], "local")

            self.assertEqual(actor_span.attributes["oa.execution.id"], execution_id)
            self.assertEqual(actor_span.attributes["oa.agent.name"], "worker")
            self.assertEqual(actor_span.attributes["oa.dispatch.mode"], "local")
            self.assertEqual(actor_span.attributes["oa.transport.kind"], "local")

            host_event_names = [event.name for event in host_span.events]
            self.assertIn("spawn", host_event_names)
            self.assertIn("receive", host_event_names)
            self.assertIn("down", host_event_names)
        finally:
            tracing.shutdown()

    async def test_http_remote_actor_transport_records_send_receive_replay_and_down(self) -> None:
        from openagentic_sdk.subagents.remote_http import HttpRemoteActorTransport

        tracing, exporter = _build_tracing(service_name="oa-test-http")
        send_bodies: list[dict[str, object]] = []
        replay_queries: list[dict[str, list[str]]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                if self.path == "/dispatch":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                    self.send_header("X-OA-Child-Session-ID", "child-http-1")
                    self.send_header("X-OA-Target-Node", "node-http")
                    self.send_header("X-OA-Git-Revision", "rev-http-1")
                    self.send_header("X-OA-Worker-Execution-ID", "exec-http-1")
                    self.send_header("X-OA-Execution-ID", "exec-http-1")
                    self.end_headers()
                    first = _child_event_envelope(
                        execution_id="exec-http-1",
                        seq=1,
                        actor_id="worker_remote/exec-http-1",
                        parent_actor_id="host",
                        event=AssistantMessage(
                            text="remote child started",
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

                if self.path == "/close":
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
                replay_queries.append(parse_qs(parsed.query))
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.end_headers()
                second = _child_event_envelope(
                    execution_id="exec-http-1",
                    seq=2,
                    actor_id="worker_remote/exec-http-1",
                    parent_actor_id="host",
                    event=Result(
                        final_text="remote child done",
                        session_id="child-http-1",
                        agent_name="worker_remote",
                        parent_tool_use_id="call_task",
                    ),
                )
                down = _down_envelope(
                    execution_id="exec-http-1",
                    seq=3,
                    actor_id="worker_remote/exec-http-1",
                    parent_actor_id="host",
                    down=ActorDownEvent(
                        execution_id="exec-http-1",
                        actor_id="worker_remote/exec-http-1",
                        reason_kind="normal",
                        reason_detail="stop_reason=end",
                        final_state="exited",
                        dispatch_mode="k3s",
                        child_session_id="child-http-1",
                        target_node="node-http",
                        worker_execution_id="exec-http-1",
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
            transport = HttpRemoteActorTransport(
                base_url=f"http://127.0.0.1:{httpd.server_address[1]}",
                tracing=tracing,
            )
            handle = await transport.spawn(_request())
            receive_iter = transport.receive(handle)
            first = await asyncio.wait_for(anext(receive_iter), timeout=2.0)
            self.assertEqual(first.kind, "child_event")

            await transport.send(
                handle,
                ActorEnvelope(
                    protocol_version="v1",
                    message_id="ctrl-1",
                    execution_id="exec-http-1",
                    sender_actor_id="host",
                    recipient_actor_id="worker_remote/exec-http-1",
                    mailbox="control",
                    seq=1,
                    kind="control",
                    payload={"op": "ping"},
                    ts=1.0,
                ),
            )
            rest = [envelope async for envelope in receive_iter]
            self.assertEqual(rest[-1].kind, "down")
            await asyncio.wait_for(handle.down_future, timeout=1.0)
            await transport.close(handle)

            spans = exporter.get_finished_spans()
            transport_span = _find_span(spans, name="oa.actor.transport", execution_id="exec-http-1", transport_kind="http")
            self.assertEqual(transport_span.attributes["oa.execution.id"], "exec-http-1")
            self.assertEqual(transport_span.attributes["oa.agent.name"], "worker_remote")
            self.assertEqual(transport_span.attributes["oa.dispatch.mode"], "k3s")
            self.assertEqual(transport_span.attributes["oa.transport.kind"], "http")

            event_names = [event.name for event in transport_span.events]
            self.assertIn("spawn", event_names)
            self.assertIn("receive", event_names)
            self.assertIn("send", event_names)
            self.assertIn("replay", event_names)
            self.assertIn("ack", event_names)
            self.assertIn("down", event_names)

            receive_event = next(event for event in transport_span.events if event.name == "receive")
            self.assertEqual(receive_event.attributes["oa.message.id"], "msg-1")
            self.assertEqual(receive_event.attributes["oa.seq"], 1)
            self.assertEqual(receive_event.attributes["oa.mailbox"], "child_events")

            replay_event = next(event for event in transport_span.events if event.name == "replay")
            self.assertEqual(replay_event.attributes["oa.mailbox"], "child_events")
            self.assertEqual(replay_event.attributes["oa.after.seq"], 1)
            self.assertTrue(replay_queries)
            self.assertEqual(replay_queries[0]["after_seq"], ["1"])
            self.assertTrue(any(body.get("kind") == "ack" for body in send_bodies))
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5.0)
            tracing.shutdown()

    async def test_remote_worker_child_actor_span_keeps_trace_link_to_host_context(self) -> None:
        from openagentic_sdk.sessions.store import FileSessionStore
        from openagentic_sdk.subagents.remote_worker import InProcessRemoteTaskWorker

        tracing, exporter = _build_tracing(service_name="oa-test-worker-link")
        try:
            with TemporaryDirectory() as td:
                root = Path(td)
                store = FileSessionStore(root_dir=root / "sessions")
                options = OpenAgenticOptions(
                    provider=_TaskProvider(),
                    model="fake",
                    api_key="x",
                    cwd=str(root),
                    project_dir=str(root),
                    tools=ToolRegistry([]),
                    permission_gate=PermissionGate(permission_mode="bypass"),
                    session_store=store,
                )
                options.runtime_state.actor_tracing = tracing
                worker = InProcessRemoteTaskWorker(base_options=options, session_store=store)

                host_span = tracing.start_span("oa.host.parent", attributes={"oa.execution.id": "parent-host"})
                with tracing.use_span(host_span):
                    request = RemoteTaskRequest(
                        parent_session_id="p" * 32,
                        parent_tool_use_id="call_task",
                        agent_name="worker_remote",
                        prompt="do remote child work",
                        definition=AgentDefinition(
                            description="remote child",
                            prompt="CHILD_TRACE: do the work",
                            tools=(),
                            executor=AgentExecutorDefinition(kind="k3s", node_name="node-remote"),
                            workspace=AgentWorkspaceDefinition(mode="readonly"),
                        ),
                        cwd=str(root),
                        project_dir=str(root),
                        git_revision="rev-remote-1",
                        worker_execution_id="exec-remote-link-1",
                        trace_context=tracing.inject_current_context(),
                    )
                handle = await worker.dispatch(request)
                events = [event async for event in handle.events]
                self.assertTrue(events)
                await asyncio.wait_for(handle.down_future, timeout=2.0)
                tracing.end_span(host_span)

            spans = exporter.get_finished_spans()
            actor_span = _find_span(
                spans,
                name="oa.actor.execution",
                execution_id="exec-remote-link-1",
                transport_kind="local",
            )
            host_context = host_span.get_span_context()
            self.assertTrue(actor_span.links, "remote worker child span should expose at least one trace link")
            linked_contexts = {(link.context.trace_id, link.context.span_id) for link in actor_span.links}
            self.assertIn((host_context.trace_id, host_context.span_id), linked_contexts)
        finally:
            tracing.shutdown()


def _build_tracing(*, service_name: str):
    from openagentic_sdk.subagents.actor_tracing import ActorTracing

    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return ActorTracing(service_name=service_name, tracer_provider=provider), exporter


def _find_span(spans, *, name: str, execution_id: str, transport_kind: str | None = None):  # noqa: ANN001
    for span in spans:
        if span.name != name:
            continue
        if span.attributes.get("oa.execution.id") != execution_id:
            continue
        if transport_kind is not None and span.attributes.get("oa.transport.kind") != transport_kind:
            continue
        return span
    raise AssertionError(f"span not found: name={name} execution_id={execution_id} transport_kind={transport_kind}")


def _request() -> RemoteTaskRequest:
    return RemoteTaskRequest(
        parent_session_id="p" * 32,
        parent_tool_use_id="call_task",
        agent_name="worker_remote",
        prompt="Do remote child work",
        definition=AgentDefinition(
            description="remote child",
            prompt="REMOTE_CHILD_DEF",
            tools=("Read",),
            executor=AgentExecutorDefinition(kind="k3s", node_name="node-http"),
            workspace=AgentWorkspaceDefinition(mode="readonly"),
        ),
        cwd="E:/fake/repo",
        project_dir="E:/fake/repo",
        git_revision="rev-http-1",
        worker_execution_id="exec-http-1",
    )


def _child_event_envelope(
    *,
    execution_id: str,
    seq: int,
    actor_id: str,
    parent_actor_id: str,
    event: AssistantMessage | Result,
) -> ActorEnvelope:
    from openagentic_sdk.serialization import event_to_dict

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
