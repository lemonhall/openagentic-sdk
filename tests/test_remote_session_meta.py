from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkerDefinition,
    AgentWorkspaceDefinition,
    OpenAgenticOptions,
)
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.tools.registry import ToolRegistry


class _MetaProvider:
    name = "meta-provider"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = tools
        _ = api_key
        user_text = next((m.get("content") for m in messages if m.get("role") == "user"), "")
        has_tool_output = any(m.get("role") == "tool" for m in messages)
        if isinstance(user_text, str) and user_text.startswith("META") and not has_tool_output:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="call_task",
                        name="Task",
                        arguments={"agent": "worker_remote", "prompt": "meta child"},
                    )
                ],
                usage=None,
                raw=None,
            )
        if has_tool_output:
            return ModelOutput(assistant_text="parent meta ok", tool_calls=[], usage=None, raw=None)
        return ModelOutput(assistant_text="worker meta ok", tool_calls=[], usage=None, raw=None)


class _WorkerBackedDispatcher:
    def __init__(self, worker) -> None:
        self._worker = worker

    async def dispatch(self, request):
        return await self._worker.dispatch(request)


class TestRemoteSessionMeta(unittest.IsolatedAsyncioTestCase):
    async def test_parent_and_child_sessions_record_remote_trace_metadata(self) -> None:
        from openagentic_sdk.subagents.remote_worker import InProcessRemoteTaskWorker

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            base_options = OpenAgenticOptions(
                provider=_MetaProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                project_dir=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
            )
            worker = InProcessRemoteTaskWorker(base_options=base_options, session_store=store)
            options = OpenAgenticOptions(
                provider=_MetaProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                project_dir=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                remote_task_dispatcher=_WorkerBackedDispatcher(worker),
                agents={
                    "worker_remote": AgentDefinition(
                        description="remote child",
                        prompt="REMOTE_CHILD_DEF",
                        tools=("Read",),
                        executor=AgentExecutorDefinition(kind="k3s", node_name="node-z"),
                        workspace=AgentWorkspaceDefinition(mode="readonly"),
                        worker=AgentWorkerDefinition(profile="py311"),
                    )
                },
            )

            import openagentic_sdk

            events = []
            async for event in openagentic_sdk.query(prompt="META please delegate", options=options):
                events.append(event)

            parent_session_id = self._session_id_from(events)
            parent_meta = store.read_metadata(parent_session_id)
            child_session_id = self._tool_result_from(events)["child_session_id"]
            child_meta = store.read_metadata(child_session_id)
            expected_revision = self._head(root)

            self.assertEqual(parent_meta["authoritative_revision"], expected_revision)
            self.assertEqual(parent_meta["git_revision"], expected_revision)
            self.assertEqual(child_meta["dispatch_mode"], "k3s")
            self.assertEqual(child_meta["target_node"], "node-z")
            self.assertEqual(child_meta["git_revision"], expected_revision)
            self.assertTrue(isinstance(child_meta.get("worker_execution_id"), str) and child_meta["worker_execution_id"])

            tool_result = self._tool_result_from(events)
            self.assertEqual(tool_result["target_node"], child_meta["target_node"])
            self.assertEqual(tool_result["git_revision"], child_meta["git_revision"])
            self.assertEqual(tool_result["worker_execution_id"], child_meta["worker_execution_id"])

    def _init_git_repo(self, root: Path) -> None:
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
        (root / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, text=True)

    def _head(self, root: Path) -> str:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True)
        return proc.stdout.strip()

    def _session_id_from(self, events: list[object]) -> str:
        for event in events:
            if getattr(event, "type", None) == "system.init":
                session_id = getattr(event, "session_id", None)
                if isinstance(session_id, str) and session_id:
                    return session_id
        raise AssertionError("system.init missing")

    def _tool_result_from(self, events: list[object]) -> dict:
        for event in events:
            if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task":
                output = getattr(event, "output", None)
                if isinstance(output, dict):
                    return output
        raise AssertionError("tool.result for call_task missing")


if __name__ == "__main__":
    unittest.main()
