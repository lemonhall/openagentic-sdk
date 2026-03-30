from __future__ import annotations

import asyncio
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _DuplicateSystemInitHost:
    def __init__(self) -> None:
        self._sid = "a" * 32
        self._prompt_started = threading.Event()
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

    def _write_json(self, handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    def _session_entries(self) -> list[dict]:
        entries = [
            {
                "type": "system.init",
                "session_id": self._sid,
                "cwd": "/workspace/repo",
                "sdk_version": "0.1.4",
                "enabled_tools": ["Read"],
                "enabled_providers": ["rightcode"],
            }
        ]
        if self._prompt_started.is_set():
            entries.extend(
                [
                    {
                        "type": "user.message",
                        "text": "你好啊",
                    },
                    {
                        "type": "assistant.message",
                        "text": "你好！有什么我可以帮你处理的？",
                        "is_summary": False,
                    },
                    {
                        "type": "result",
                        "final_text": "你好！有什么我可以帮你处理的？",
                        "session_id": self._sid,
                        "stop_reason": "end",
                    },
                ]
            )
        return entries

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
                        },
                    )
                    return
                if self.path == f"/session/{outer._sid}":
                    outer._write_json(self, 200, {"id": outer._sid, "metadata": {}})
                    return
                if self.path == f"/session/{outer._sid}/events":
                    outer._write_json(self, 200, {"session_id": outer._sid, "entries": outer._session_entries()})
                    return
                if self.path == "/event":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(b'data: {"type":"server.connected"}\n\n')
                    self.wfile.flush()
                    if not outer._prompt_started.wait(timeout=5.0):
                        return
                    payloads = [
                        {
                            "type": "session.event",
                            "session_id": outer._sid,
                            "event": {
                                "type": "system.init",
                                "session_id": outer._sid,
                                "cwd": "/workspace/repo",
                                "sdk_version": "0.1.4",
                                "enabled_tools": ["Read"],
                                "enabled_providers": ["rightcode"],
                            },
                        },
                        {
                            "type": "session.event",
                            "session_id": outer._sid,
                            "event": {
                                "type": "assistant.message",
                                "text": "你好！有什么我可以帮你处理的？",
                                "is_summary": False,
                            },
                        },
                        {
                            "type": "session.event",
                            "session_id": outer._sid,
                            "event": {
                                "type": "result",
                                "final_text": "你好！有什么我可以帮你处理的？",
                                "session_id": outer._sid,
                                "stop_reason": "end",
                            },
                        },
                        {
                            "type": "session.sync",
                            "session_id": outer._sid,
                            "sync": {"status": "ok"},
                        },
                    ]
                    for payload in payloads:
                        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                        self.wfile.write(b"data: " + raw + b"\n\n")
                        self.wfile.flush()
                    return
                outer._write_json(self, 404, {"error": "not_found"})

            def do_POST(self):  # noqa: N802
                if self.path == "/session":
                    outer._write_json(self, 200, {"id": outer._sid, "metadata": {}})
                    return
                if self.path == f"/session/{outer._sid}/prompt_async":
                    outer._prompt_started.set()
                    self.send_response(204)
                    self.end_headers()
                    return
                outer._write_json(self, 404, {"error": "not_found"})

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                _ = (format, args)

        return Handler


class TestClusterChatClientLiveHistoryDedupe(unittest.IsolatedAsyncioTestCase):
    async def test_query_keeps_assistant_message_when_live_stream_repeats_history_system_init(self) -> None:
        from openagentic_sdk.server.cluster_chat_client import ClusterChatClient

        host = _DuplicateSystemInitHost()
        host.start()
        self.addCleanup(host.close)

        client = ClusterChatClient(base_url=host.base_url, timeout_s=1.0)
        events = [event async for event in client.query(prompt="你好啊")]

        self.assertEqual([getattr(event, "type", None) for event in events], ["system.init", "assistant.message", "result"])
        self.assertEqual(getattr(events[1], "text", None), "你好！有什么我可以帮你处理的？")
        self.assertEqual(getattr(events[2], "final_text", None), "你好！有什么我可以帮你处理的？")

    async def test_query_synthesizes_root_assistant_message_when_live_stream_only_has_result(self) -> None:
        from openagentic_sdk.server.cluster_chat_client import ClusterChatClient

        class _ResultOnlyLiveHost(_DuplicateSystemInitHost):
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
                                },
                            )
                            return
                        if self.path == f"/session/{outer._sid}":
                            outer._write_json(self, 200, {"id": outer._sid, "metadata": {}})
                            return
                        if self.path == f"/session/{outer._sid}/events":
                            outer._write_json(self, 200, {"session_id": outer._sid, "entries": outer._session_entries()})
                            return
                        if self.path == "/event":
                            self.send_response(200)
                            self.send_header("Content-Type", "text/event-stream")
                            self.send_header("Cache-Control", "no-cache")
                            self.send_header("Connection", "close")
                            self.end_headers()
                            self.wfile.write(b'data: {"type":"server.connected"}\n\n')
                            self.wfile.flush()
                            if not outer._prompt_started.wait(timeout=5.0):
                                return
                            payloads = [
                                {
                                    "type": "session.event",
                                    "session_id": outer._sid,
                                    "event": {
                                        "type": "system.init",
                                        "session_id": outer._sid,
                                        "cwd": "/workspace/repo",
                                        "sdk_version": "0.1.4",
                                        "enabled_tools": ["Read"],
                                        "enabled_providers": ["rightcode"],
                                    },
                                },
                                {
                                    "type": "session.event",
                                    "session_id": outer._sid,
                                    "event": {
                                        "type": "result",
                                        "final_text": "你好！有什么我可以帮你处理的？",
                                        "session_id": outer._sid,
                                        "stop_reason": "end",
                                    },
                                },
                                {
                                    "type": "session.sync",
                                    "session_id": outer._sid,
                                    "sync": {"status": "ok"},
                                },
                            ]
                            for payload in payloads:
                                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                                self.wfile.write(b"data: " + raw + b"\n\n")
                                self.wfile.flush()
                            return
                        outer._write_json(self, 404, {"error": "not_found"})

                    def do_POST(self):  # noqa: N802
                        if self.path == "/session":
                            outer._write_json(self, 200, {"id": outer._sid, "metadata": {}})
                            return
                        if self.path == f"/session/{outer._sid}/prompt_async":
                            outer._prompt_started.set()
                            self.send_response(204)
                            self.end_headers()
                            return
                        outer._write_json(self, 404, {"error": "not_found"})

                    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                        _ = (format, args)

                return Handler

        host = _ResultOnlyLiveHost()
        host.start()
        self.addCleanup(host.close)

        client = ClusterChatClient(base_url=host.base_url, timeout_s=1.0)
        events = [event async for event in client.query(prompt="你好啊")]

        self.assertEqual([getattr(event, "type", None) for event in events], ["system.init", "assistant.message", "result"])
        self.assertEqual(getattr(events[1], "text", None), "你好！有什么我可以帮你处理的？")
        self.assertEqual(getattr(events[2], "final_text", None), "你好！有什么我可以帮你处理的？")


if __name__ == "__main__":
    unittest.main()
