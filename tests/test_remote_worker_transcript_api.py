from __future__ import annotations

import json
import subprocess
import threading
import unittest
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.events import AssistantMessage, UserMessage
from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.tools.registry import ToolRegistry


class _Provider:
    name = "worker-transcript-provider"

    async def complete(self, **kwargs):  # noqa: ANN003
        _ = kwargs
        return ModelOutput(assistant_text="ok", tool_calls=(), usage=None, raw=None)


class TestRemoteWorkerTranscriptApi(unittest.TestCase):
    def test_worker_transcript_route_returns_structured_messages(self) -> None:
        from openagentic_sdk.subagents.remote_http import RemoteTaskHttpWorkerServer

        with TemporaryDirectory() as td:
            root = Path(td)
            repo_root = root / "repo"
            repo_root.mkdir()
            self._init_git_repo(repo_root)
            store = FileSessionStore(root_dir=root / "session_home")
            sid = store.create_session(metadata={"agent_name": "research"})
            store.append_event(sid, UserMessage(text="你好"))
            store.append_event(sid, AssistantMessage(text="研究结果"))
            options = OpenAgenticOptions(
                provider=_Provider(),
                model="fake",
                cwd=str(repo_root),
                project_dir=str(repo_root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
            )
            worker_server = RemoteTaskHttpWorkerServer(
                base_options=options,
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
                with urllib.request.urlopen(  # noqa: S310
                    f"http://127.0.0.1:{httpd.server_address[1]}/oa/transcript/session/{sid}",
                    timeout=5,
                ) as resp:
                    payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5.0)

        self.assertEqual(payload["session_id"], sid)
        self.assertEqual(payload["agent_name"], "research")
        self.assertEqual(payload["source"], "worker")
        self.assertEqual([m["text"] for m in payload["messages"]], ["你好", "研究结果"])

    def _init_git_repo(self, root: Path) -> None:
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
        (root / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
