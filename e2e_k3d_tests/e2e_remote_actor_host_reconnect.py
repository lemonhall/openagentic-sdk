from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import openagentic_sdk
from e2e_k3d_tests._harness import AGENT_A_NODE, authoritative_repo_root, ensure_cluster_ready, port_forward_worker
from openagentic_sdk.options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkspaceDefinition,
    OpenAgenticOptions,
)
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.subagents.remote_http import HttpRemoteTaskDispatcher
from openagentic_sdk.tools.defaults import default_tool_registry


class _ParentProvider:
    name = "k3d-actor-parent-host-reconnect"

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


class _FaultInjectingWorkerProxy:
    def __init__(self, *, backend_base_url: str) -> None:
        self.backend_base_url = backend_base_url.rstrip("/")
        self.dispatch_count = 0
        self.stream_queries: list[dict[str, list[str]]] = []
        self.send_bodies: list[dict[str, object]] = []
        self.close_count = 0
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def __enter__(self) -> _FaultInjectingWorkerProxy:
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5.0)

    def _make_handler(self):
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or "0")
                body = self.rfile.read(length) if length > 0 else b"{}"
                if self.path == "/dispatch":
                    proxy.dispatch_count += 1
                    response = urllib_request.urlopen(
                        urllib_request.Request(
                            url=f"{proxy.backend_base_url}/dispatch",
                            data=body,
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        ),
                        timeout=30.0,
                    )
                    try:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                        for header_name in (
                            "X-OA-Child-Session-ID",
                            "X-OA-Target-Node",
                            "X-OA-Git-Revision",
                            "X-OA-Worker-Execution-ID",
                            "X-OA-Execution-ID",
                        ):
                            header_value = response.headers.get(header_name)
                            if header_value is not None:
                                self.send_header(header_name, header_value)
                        self.end_headers()
                        first_line = response.readline()
                        if first_line:
                            self.wfile.write(first_line)
                            self.wfile.flush()
                    finally:
                        response.close()
                    return

                if self.path == "/send":
                    payload = json.loads(body.decode("utf-8"))
                    if isinstance(payload, dict):
                        proxy.send_bodies.append(payload)
                    self._forward_post(path="/send", body=body)
                    return

                if self.path == "/close":
                    proxy.close_count += 1
                    self._forward_post(path="/close", body=body)
                    return

                if self.path == "/abort":
                    self._forward_post(path="/abort", body=body)
                    return

                self.send_response(404)
                self.end_headers()

            def do_GET(self):  # noqa: N802
                parsed = urllib_parse.urlparse(self.path)
                if parsed.path != "/stream":
                    self.send_response(404)
                    self.end_headers()
                    return
                query = urllib_parse.parse_qs(parsed.query)
                proxy.stream_queries.append(query)
                response = urllib_request.urlopen(
                    urllib_request.Request(
                        url=f"{proxy.backend_base_url}{self.path}",
                        method="GET",
                    ),
                    timeout=30.0,
                )
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                    self.end_headers()
                    while True:
                        line = response.readline()
                        if not line:
                            return
                        self.wfile.write(line)
                        self.wfile.flush()
                finally:
                    response.close()

            def _forward_post(self, *, path: str, body: bytes) -> None:
                response = urllib_request.urlopen(
                    urllib_request.Request(
                        url=f"{proxy.backend_base_url}{path}",
                        data=body,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=30.0,
                )
                try:
                    raw = response.read()
                    self.send_response(response.status)
                    self.send_header("Content-Type", response.headers.get("Content-Type", "application/json; charset=utf-8"))
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                finally:
                    response.close()

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                _ = (format, args)

        return Handler


class TestRemoteActorHostReconnect(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_cluster_ready()

    async def test_host_task_reconnects_after_dispatch_stream_cut_without_redispatch(self) -> None:
        workspace_root = authoritative_repo_root()
        with port_forward_worker(AGENT_A_NODE) as backend_base_url:
            with _FaultInjectingWorkerProxy(backend_base_url=backend_base_url) as proxy:
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
                        remote_task_dispatcher=HttpRemoteTaskDispatcher(base_url=proxy.base_url),
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
        self.assertEqual(proxy.dispatch_count, 1)
        self.assertTrue(proxy.stream_queries)
        self.assertEqual(proxy.stream_queries[0].get("mailbox"), ["child_events"])
        self.assertEqual(proxy.stream_queries[0].get("after_seq"), ["1"])
        self.assertTrue(any(body.get("kind") == "ack" for body in proxy.send_bodies))
        self.assertGreaterEqual(proxy.close_count, 1)
        self.assertFalse(task_result.is_error)
        self.assertEqual(task_result.output["target_node"], AGENT_A_NODE)
        self.assertEqual(task_result.output["execution_id"], task_result.output["worker_execution_id"])
        self.assertEqual(task_result.output["down"]["reason_kind"], "normal")
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
