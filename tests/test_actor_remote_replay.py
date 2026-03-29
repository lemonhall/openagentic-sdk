from __future__ import annotations

import asyncio
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from openagentic_sdk.events import AssistantMessage
from openagentic_sdk.options import AgentDefinition, AgentExecutorDefinition, AgentWorkspaceDefinition
from openagentic_sdk.serialization import event_to_dict
from openagentic_sdk.subagents.actor_lifecycle import ActorDownEvent
from openagentic_sdk.subagents.actor_protocol import ActorEnvelope
from openagentic_sdk.subagents.remote_types import RemoteTaskRequest


class TestActorRemoteReplay(unittest.IsolatedAsyncioTestCase):
    async def test_reconnect_replays_from_next_unacked_seq_and_dedups_duplicates(self) -> None:
        from openagentic_sdk.subagents.remote_http import HttpRemoteActorTransport

        replay_queries: list[dict[str, list[str]]] = []
        send_bodies: list[dict[str, object]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                if self.path == "/send":
                    length = int(self.headers.get("Content-Length") or "0")
                    payload = json.loads((self.rfile.read(length) if length > 0 else b"{}").decode("utf-8"))
                    if isinstance(payload, dict):
                        send_bodies.append(payload)
                    self.send_response(202)
                    self.end_headers()
                    return
                if self.path != "/dispatch":
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("X-OA-Child-Session-ID", "child-http-2")
                self.send_header("X-OA-Target-Node", "node-http")
                self.send_header("X-OA-Git-Revision", "rev-http-2")
                self.send_header("X-OA-Worker-Execution-ID", "exec-http-2")
                self.send_header("X-OA-Execution-ID", "exec-http-2")
                self.end_headers()
                first = _child_event_envelope(
                    execution_id="exec-http-2",
                    seq=1,
                    actor_id="worker_remote/exec-http-2",
                    parent_actor_id="host",
                    text="first result",
                )
                self.wfile.write(json.dumps(first.to_dict(), ensure_ascii=False).encode("utf-8") + b"\n")
                self.wfile.flush()
                self.connection.shutdown(1)

            def do_GET(self):  # noqa: N802
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
                duplicate = _child_event_envelope(
                    execution_id="exec-http-2",
                    seq=1,
                    actor_id="worker_remote/exec-http-2",
                    parent_actor_id="host",
                    text="first result",
                )
                second = _child_event_envelope(
                    execution_id="exec-http-2",
                    seq=2,
                    actor_id="worker_remote/exec-http-2",
                    parent_actor_id="host",
                    text="second result",
                )
                down = _down_envelope(
                    execution_id="exec-http-2",
                    seq=3,
                    actor_id="worker_remote/exec-http-2",
                    parent_actor_id="host",
                    down=ActorDownEvent(
                        execution_id="exec-http-2",
                        actor_id="worker_remote/exec-http-2",
                        reason_kind="normal",
                        reason_detail="stop_reason=end",
                        final_state="exited",
                        dispatch_mode="k3s",
                        child_session_id="child-http-2",
                        target_node="node-http",
                        worker_execution_id="exec-http-2",
                    ),
                )
                for envelope in (duplicate, second, down):
                    self.wfile.write(json.dumps(envelope.to_dict(), ensure_ascii=False).encode("utf-8") + b"\n")
                    self.wfile.flush()

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                _ = (format, args)

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            transport = HttpRemoteActorTransport(base_url=f"http://127.0.0.1:{httpd.server_address[1]}")
            handle = await transport.spawn(_request())
            envelopes = [envelope async for envelope in transport.receive(handle)]
            down = await asyncio.wait_for(handle.down_future, timeout=1.0)
            await transport.close(handle)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5.0)

        self.assertEqual([envelope.seq for envelope in envelopes], [1, 2, 3])
        self.assertEqual([envelope.kind for envelope in envelopes], ["child_event", "child_event", "down"])
        self.assertTrue(replay_queries)
        self.assertEqual(replay_queries[0].get("execution_id"), ["exec-http-2"])
        self.assertEqual(replay_queries[0].get("after_seq"), ["1"])
        self.assertEqual(replay_queries[0].get("mailbox"), ["child_events"])
        self.assertTrue(send_bodies)
        self.assertEqual(send_bodies[0].get("kind"), "ack")
        self.assertEqual(send_bodies[0].get("mailbox"), "child_events")
        self.assertEqual(send_bodies[0].get("payload"), {"acked_seq": 1, "mailbox": "child_events"})
        self.assertEqual(down.reason_kind, "normal")


def _request() -> RemoteTaskRequest:
    return RemoteTaskRequest(
        parent_session_id="q" * 32,
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
        git_revision="rev-http-2",
        worker_execution_id="exec-http-2",
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
