from __future__ import annotations

import subprocess
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkspaceDefinition,
    OpenAgenticOptions,
)
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.subagents.remote_types import RemoteTaskRequest
from openagentic_sdk.tools.registry import ToolRegistry


class HttpWorkerChildProvider:
    name = "http-child"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        user_text = next((m.get("content") for m in messages if m.get("role") == "user"), "")
        if isinstance(user_text, str) and user_text.startswith("REMOTE_HTTP_DEF:"):
            return ModelOutput(assistant_text="remote http ok", tool_calls=[], usage=None, raw=None)
        return ModelOutput(assistant_text="unexpected", tool_calls=[], usage=None, raw=None)


class TestRemoteHttpTransport(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
