from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.events import AssistantMessage, UserMessage
from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.tools.registry import ToolRegistry


class _Provider:
    name = "cluster-transcript-provider"

    async def complete(self, **kwargs):  # noqa: ANN003
        _ = kwargs
        return ModelOutput(assistant_text="ok", tool_calls=(), usage=None, raw=None)


def _http_json(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            return int(resp.status), json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8", errors="replace"))


class TestClusterChatTranscriptApi(unittest.TestCase):
    def test_host_transcript_route_returns_structured_messages(self) -> None:
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root / "sessions_home")
            sid = store.create_session(metadata={})
            store.append_event(sid, UserMessage(text="hello"))
            store.append_event(sid, AssistantMessage(text="world"))
            options = OpenAgenticOptions(
                provider=_Provider(),
                model="fake",
                cwd=str(root),
                project_dir=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
            )
            httpd = ClusterChatHostServer(base_options=options, session_store=store).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                status, payload = _http_json(f"http://127.0.0.1:{httpd.server_address[1]}/oa/transcript/session/{sid}")
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5.0)

        self.assertEqual(status, 200)
        self.assertEqual(payload["session_id"], sid)
        self.assertEqual(payload["source"], "host")
        self.assertEqual([m["text"] for m in payload["messages"]], ["hello", "world"])

    def test_host_transcript_route_maps_missing_session_to_not_found(self) -> None:
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root / "sessions_home")
            options = OpenAgenticOptions(
                provider=_Provider(),
                model="fake",
                cwd=str(root),
                project_dir=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
            )
            httpd = ClusterChatHostServer(base_options=options, session_store=store).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                status, payload = _http_json(f"http://127.0.0.1:{httpd.server_address[1]}/oa/transcript/session/{'f' * 32}")
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5.0)

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "not_found")

    def test_host_can_proxy_child_transcript_by_target_node(self) -> None:
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer, StaticNodeHttpRemoteTaskDispatcher

        class WorkerHandler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path != "/oa/transcript/session/" + ("c" * 32):
                    self.send_response(404)
                    self.end_headers()
                    return
                raw = json.dumps(
                    {
                        "session_id": "c" * 32,
                        "agent_name": "writer",
                        "source": "worker",
                        "messages": [{"role": "assistant", "text": "child body"}],
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                _ = (format, args)

        worker_httpd = ThreadingHTTPServer(("127.0.0.1", 0), WorkerHandler)
        worker_thread = threading.Thread(target=worker_httpd.serve_forever, daemon=True)
        worker_thread.start()
        try:
            with TemporaryDirectory() as td:
                root = Path(td)
                store = FileSessionStore(root_dir=root / "sessions_home")
                dispatcher = StaticNodeHttpRemoteTaskDispatcher(
                    node_urls={"node-a": f"http://127.0.0.1:{worker_httpd.server_address[1]}"}
                )
                options = OpenAgenticOptions(
                    provider=_Provider(),
                    model="fake",
                    cwd=str(root),
                    project_dir=str(root),
                    tools=ToolRegistry([]),
                    permission_gate=PermissionGate(permission_mode="bypass"),
                    session_store=store,
                    remote_task_dispatcher=dispatcher,
                )
                httpd = ClusterChatHostServer(base_options=options, session_store=store).make_server()
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                try:
                    status, payload = _http_json(
                        f"http://127.0.0.1:{httpd.server_address[1]}/oa/transcript/child/node-a/{'c' * 32}"
                    )
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(timeout=5.0)
        finally:
            worker_httpd.shutdown()
            worker_httpd.server_close()
            worker_thread.join(timeout=5.0)

        self.assertEqual(status, 200)
        self.assertEqual(payload["session_id"], "c" * 32)
        self.assertEqual(payload["agent_name"], "writer")
        self.assertEqual(payload["source"], "worker")
        self.assertEqual(payload["messages"][0]["text"], "child body")

    def test_host_proxies_child_transcript_via_explicit_dispatcher_contract(self) -> None:
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        class DispatcherWithTranscriptProxy:
            async def dispatch(self, request):  # noqa: ANN001
                _ = request
                raise AssertionError("dispatch should not be called for transcript proxy tests")

            def read_transcript(self, *, target_node: str, session_id: str) -> tuple[int, dict]:
                self.last_call = (target_node, session_id)
                return (
                    200,
                    {
                        "session_id": session_id,
                        "agent_name": "research",
                        "source": "worker",
                        "messages": [{"role": "assistant", "text": "proxy body"}],
                    },
                )

        dispatcher = DispatcherWithTranscriptProxy()

        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root / "sessions_home")
            options = OpenAgenticOptions(
                provider=_Provider(),
                model="fake",
                cwd=str(root),
                project_dir=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                remote_task_dispatcher=dispatcher,
            )
            httpd = ClusterChatHostServer(base_options=options, session_store=store).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                status, payload = _http_json(
                    f"http://127.0.0.1:{httpd.server_address[1]}/oa/transcript/child/researchers/{'d' * 32}"
                )
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5.0)

        self.assertEqual(status, 200)
        self.assertEqual(dispatcher.last_call, ("researchers", "d" * 32))
        self.assertEqual(payload["messages"][0]["text"], "proxy body")

    def test_host_child_proxy_maps_worker_unreachable_error_code(self) -> None:
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        class DispatcherWithBrokenTranscriptProxy:
            async def dispatch(self, request):  # noqa: ANN001
                _ = request
                raise AssertionError("dispatch should not be called for transcript proxy tests")

            def read_transcript(self, *, target_node: str, session_id: str) -> tuple[int, dict]:
                _ = (target_node, session_id)
                raise ConnectionError("dial tcp timeout")

        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root / "sessions_home")
            options = OpenAgenticOptions(
                provider=_Provider(),
                model="fake",
                cwd=str(root),
                project_dir=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                remote_task_dispatcher=DispatcherWithBrokenTranscriptProxy(),
            )
            httpd = ClusterChatHostServer(base_options=options, session_store=store).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                status, payload = _http_json(
                    f"http://127.0.0.1:{httpd.server_address[1]}/oa/transcript/child/researchers/{'e' * 32}"
                )
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5.0)

        self.assertEqual(status, 502)
        self.assertEqual(payload["error"], "worker_unreachable")

    def test_host_child_proxy_without_contract_maps_to_transcript_unavailable(self) -> None:
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        class DispatcherWithoutTranscriptProxy:
            async def dispatch(self, request):  # noqa: ANN001
                _ = request
                raise AssertionError("dispatch should not be called for transcript proxy tests")

        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root / "sessions_home")
            options = OpenAgenticOptions(
                provider=_Provider(),
                model="fake",
                cwd=str(root),
                project_dir=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                remote_task_dispatcher=DispatcherWithoutTranscriptProxy(),
            )
            httpd = ClusterChatHostServer(base_options=options, session_store=store).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                status, payload = _http_json(
                    f"http://127.0.0.1:{httpd.server_address[1]}/oa/transcript/child/researchers/{'a' * 32}"
                )
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5.0)

        self.assertEqual(status, 503)
        self.assertEqual(payload["error"], "transcript_unavailable")


if __name__ == "__main__":
    unittest.main()
