from __future__ import annotations

import asyncio
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from openagentic_cli.repl import run_chat
from openagentic_cli.style import StyleConfig
from openagentic_sdk.events import AssistantMessage, Result, SystemInit, ToolResult, ToolUse, UserMessage
from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.serialization import event_to_dict


class _PollingRecoveryHost:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sid = "f" * 32
        self._events: list[dict] = []
        self._prompt_started = False
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5.0)

    def _append(self, event) -> None:  # noqa: ANN001
        with self._lock:
            self._events.append(event_to_dict(event))

    def _snapshot(self) -> list[dict]:
        with self._lock:
            return list(self._events)

    def _produce_events(self, prompt: str) -> None:
        _ = prompt
        if self._prompt_started:
            return
        self._prompt_started = True

        def _run() -> None:
            time.sleep(0.03)
            self._append(
                SystemInit(
                    session_id=self._sid,
                    cwd="E:\\development\\openagentic-sdk",
                    sdk_version="test-sdk",
                    enabled_tools=["Task"],
                    enabled_providers=["rightcode"],
                )
            )
            self._append(UserMessage(text="你让你的写作团队，写一篇与周一相关的小作文吧"))
            time.sleep(0.03)
            self._append(
                ToolUse(
                    tool_use_id="call_task",
                    name="Task",
                    input={"agent": "writer"},
                )
            )
            time.sleep(0.03)
            self._append(
                SystemInit(
                    session_id="c" * 32,
                    cwd="E:\\development\\openagentic-sdk",
                    sdk_version="test-sdk",
                    agent_name="writer",
                    parent_tool_use_id="call_task",
                    enabled_tools=["Read"],
                    enabled_providers=["rightcode"],
                )
            )
            self._append(
                AssistantMessage(
                    text="周一的早晨有一点冷，地铁门一开，风和咖啡味一起挤进来。",
                    agent_name="writer",
                    parent_tool_use_id="call_task",
                )
            )
            self._append(
                Result(
                    final_text="周一的早晨有一点冷，地铁门一开，风和咖啡味一起挤进来。",
                    session_id="c" * 32,
                    agent_name="writer",
                    parent_tool_use_id="call_task",
                )
            )
            self._append(
                ToolResult(
                    tool_use_id="call_task",
                    output={
                        "dispatch_mode": "k3s",
                        "target_node": "k3d-v56-openagentic-agent-1",
                        "worker_execution_id": "exec-1",
                        "child_session_id": "c" * 32,
                    },
                )
            )
            time.sleep(0.03)
            self._append(AssistantMessage(text="周一的早晨有一点冷，地铁门一开，风和咖啡味一起挤进来。"))
            self._append(
                Result(
                    final_text="周一的早晨有一点冷，地铁门一开，风和咖啡味一起挤进来。",
                    session_id=self._sid,
                )
            )

        threading.Thread(target=_run, daemon=True).start()

    def _write_json(self, handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    def _make_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path == "/health":
                    outer._write_json(
                        self,
                        200,
                        {
                            "ok": True,
                            "deployment_mode": "real-model",
                            "provider_profiles": ["rightcode"],
                            "host_node_name": "k3d-v56-openagentic-server-0",
                        },
                    )
                    return

                if self.path == "/event":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(b'data: {"type":"server.connected"}\n\n')
                    self.wfile.flush()
                    # Deliberately stall here: session events are only visible through
                    # /session/<id>/events, reproducing the k3d/port-forward/SSE issue.
                    time.sleep(1.0)
                    return

                if self.path == f"/session/{outer._sid}":
                    outer._write_json(self, 200, {"id": outer._sid, "metadata": {}})
                    return

                if self.path == f"/session/{outer._sid}/events":
                    outer._write_json(self, 200, {"session_id": outer._sid, "entries": outer._snapshot()})
                    return

                outer._write_json(self, 404, {"error": "not_found"})

            def do_POST(self):  # noqa: N802
                if self.path == "/session":
                    outer._write_json(self, 200, {"id": outer._sid, "metadata": {}})
                    return

                if self.path == f"/session/{outer._sid}/prompt_async":
                    length = int(self.headers.get("Content-Length") or "0")
                    raw = self.rfile.read(length) if length > 0 else b"{}"
                    payload = json.loads(raw.decode("utf-8"))
                    outer._produce_events(str(payload.get("prompt") or ""))
                    outer._write_json(self, 200, {"ok": True})
                    return

                outer._write_json(self, 404, {"error": "not_found"})

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                _ = (format, args)

        return Handler


class TestCliRemoteEventPollRecovery(unittest.IsolatedAsyncioTestCase):
    async def test_run_chat_recovers_when_remote_event_stream_stalls_but_session_events_advance(self) -> None:
        import openagentic_sdk.server.cluster_chat_client as cluster_chat_client

        host = _PollingRecoveryHost()
        host.start()
        self.addCleanup(host.close)

        with TemporaryDirectory() as td:
            opts = OpenAgenticOptions(
                provider=None,
                model="bridge",
                cwd="E:\\development\\openagentic-sdk",
                project_dir="E:\\development\\openagentic-sdk",
                permission_gate=PermissionGate(permission_mode="deny"),
                setting_sources=[],
                session_root=Path(td),
                remote_chat_base_url=host.base_url,
                remote_chat_timeout_s=5.0,
            )
            stdin = StringIO("你让你的写作团队，写一篇与周一相关的小作文吧\n/exit\n")
            stdout = StringIO()
            with mock.patch.object(cluster_chat_client, "_SESSION_EVENT_POLL_INTERVAL_S", 0.05, create=True):
                rc = await asyncio.wait_for(
                    run_chat(
                        opts,
                        color_config=StyleConfig(color="never"),
                        debug=False,
                        stdin=stdin,
                        stdout=stdout,
                    ),
                    timeout=2.0,
                )

        rendered = stdout.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Delegate to `writer`", rendered)
        self.assertIn("agent=writer", rendered)
        self.assertIn("周一的早晨有一点冷", rendered)


if __name__ == "__main__":
    unittest.main()
