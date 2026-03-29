from __future__ import annotations

import asyncio
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openagentic_sdk.events import AssistantMessage
from openagentic_sdk.options import AgentDefinition, AgentExecutorDefinition, AgentWorkspaceDefinition
from openagentic_sdk.serialization import event_from_dict, event_to_dict
from openagentic_sdk.subagents.actor_lifecycle import ActorDownEvent
from openagentic_sdk.subagents.actor_protocol import ActorEnvelope
from openagentic_sdk.subagents.remote_types import RemoteTaskRequest


class TestActorHttpTransport(unittest.IsolatedAsyncioTestCase):
    async def test_http_actor_transport_spawn_receive_abort_uses_actor_envelopes(self) -> None:
        from openagentic_sdk.subagents.remote_http import HttpRemoteActorTransport

        first_sent = threading.Event()
        abort_called = threading.Event()
        abort_bodies: list[dict[str, object]] = []
        close_bodies: list[dict[str, object]] = []
        send_bodies: list[dict[str, object]] = []

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
                        text="remote child started",
                    )
                    self.wfile.write(json.dumps(first.to_dict(), ensure_ascii=False).encode("utf-8") + b"\n")
                    self.wfile.flush()
                    first_sent.set()
                    abort_called.wait(timeout=2.0)
                    down = _down_envelope(
                        execution_id="exec-http-1",
                        seq=2,
                        actor_id="worker_remote/exec-http-1",
                        parent_actor_id="host",
                        down=ActorDownEvent(
                            execution_id="exec-http-1",
                            actor_id="worker_remote/exec-http-1",
                            reason_kind="aborted",
                            reason_detail="remote_abort",
                            final_state="aborted",
                            dispatch_mode="k3s",
                            child_session_id="child-http-1",
                            target_node="node-http",
                            worker_execution_id="exec-http-1",
                        ),
                    )
                    self.wfile.write(json.dumps(down.to_dict(), ensure_ascii=False).encode("utf-8") + b"\n")
                    self.wfile.flush()
                    return

                if self.path == "/abort":
                    length = int(self.headers.get("Content-Length") or "0")
                    payload = json.loads((self.rfile.read(length) if length > 0 else b"{}").decode("utf-8"))
                    if isinstance(payload, dict):
                        abort_bodies.append(payload)
                    abort_called.set()
                    self.send_response(202)
                    self.end_headers()
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
                    length = int(self.headers.get("Content-Length") or "0")
                    payload = json.loads((self.rfile.read(length) if length > 0 else b"{}").decode("utf-8"))
                    if isinstance(payload, dict):
                        close_bodies.append(payload)
                    self.send_response(202)
                    self.end_headers()
                    return

                self.send_response(404)
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                _ = (format, args)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            transport = HttpRemoteActorTransport(base_url=f"http://127.0.0.1:{httpd.server_address[1]}")
            handle = await transport.spawn(_request())
            receive_iter = transport.receive(handle)
            first = await asyncio.wait_for(anext(receive_iter), timeout=2.0)
            self.assertEqual(first.kind, "child_event")
            self.assertTrue(first_sent.wait(timeout=2.0))

            await transport.send(
                handle,
                ActorEnvelope(
                    protocol_version="v1",
                    message_id="msg-control-1",
                    execution_id="exec-http-1",
                    sender_actor_id="host",
                    recipient_actor_id="worker_remote/exec-http-1",
                    mailbox="control",
                    seq=1,
                    kind="control",
                    payload={"op": "ping"},
                    ts=3.0,
                ),
            )
            await transport.abort(handle)
            rest = [envelope async for envelope in receive_iter]
            down = await asyncio.wait_for(handle.down_future, timeout=1.0)
            await transport.close(handle)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5.0)

        self.assertEqual(handle.execution_id, "exec-http-1")
        self.assertTrue(send_bodies)
        self.assertEqual(send_bodies[0]["kind"], "control")
        self.assertEqual(send_bodies[0]["mailbox"], "control")
        self.assertEqual(send_bodies[0]["payload"], {"op": "ping"})
        self.assertTrue(abort_bodies)
        self.assertEqual(abort_bodies[0]["execution_id"], "exec-http-1")
        self.assertEqual(abort_bodies[0]["kind"], "abort")
        self.assertTrue(close_bodies)
        self.assertEqual(close_bodies[0]["execution_id"], "exec-http-1")
        self.assertEqual(close_bodies[0]["kind"], "close")
        self.assertEqual(rest[-1].kind, "down")
        self.assertEqual(down.reason_kind, "aborted")
        child_event = event_from_dict(first.payload["event"])
        self.assertEqual(getattr(child_event, "text", None), "remote child started")


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
    text: str,
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
        payload={"event": event_to_dict(AssistantMessage(text=text, agent_name="worker_remote", parent_tool_use_id="call_task"))},
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
