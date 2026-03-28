from __future__ import annotations

import asyncio
import json
import subprocess
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from openagentic_cli.repl import run_chat
from openagentic_cli.style import StyleConfig
from openagentic_sdk.events import AssistantMessage, Result
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


class _BridgeProvider:
    name = "bridge-provider"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = tools
        _ = api_key
        user_messages = [m.get("content") for m in messages if m.get("role") == "user"]
        user_text = user_messages[-1] if user_messages else ""
        has_tool_output = any(m.get("role") == "tool" for m in messages)
        if isinstance(user_text, str) and user_text.startswith("delegate") and not has_tool_output:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="call_task",
                        name="Task",
                        arguments={"agent": "worker_remote", "prompt": "Do remote child work"},
                    )
                ],
                usage=None,
                raw=None,
            )
        if has_tool_output:
            return ModelOutput(assistant_text="host delegated", tool_calls=[], usage=None, raw=None)
        return ModelOutput(assistant_text="host ok", tool_calls=[], usage=None, raw=None)


class _BridgeOnlyProvider:
    name = "bridge-only"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = messages
        _ = tools
        _ = api_key
        raise AssertionError("local bridge provider should never be called in remote chat mode")


class _SlowBridgeProvider:
    name = "bridge-slow"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = messages
        _ = tools
        _ = api_key
        await asyncio.sleep(0.5)
        return ModelOutput(assistant_text="slow host ok", tool_calls=[], usage=None, raw=None)


class _RecordingRemoteDispatcher:
    def __init__(self) -> None:
        self.requests = []

    async def dispatch(self, request):
        self.requests.append(request)

        async def _events():
            yield AssistantMessage(
                text="remote child says hi",
                agent_name=request.agent_name,
                parent_tool_use_id=request.parent_tool_use_id,
            )
            yield Result(
                final_text="remote child done",
                session_id="b" * 32,
                agent_name=request.agent_name,
                parent_tool_use_id=request.parent_tool_use_id,
            )

        return request.make_handle(
            child_session_id="b" * 32,
            target_node=request.definition.executor.node_name or "",
            git_revision=request.git_revision,
            worker_execution_id="exec-123",
            events=_events(),
        )


class _SequencedRemoteDispatcher:
    def __init__(self) -> None:
        self.requests = []

    async def dispatch(self, request):
        self.requests.append(request)
        final_text = f"{request.agent_name} done on {request.definition.executor.node_name}"

        async def _events():
            yield AssistantMessage(
                text=f"{request.agent_name} says hi",
                agent_name=request.agent_name,
                parent_tool_use_id=request.parent_tool_use_id,
            )
            yield Result(
                final_text=final_text,
                session_id=("b" * 32)[:-len(request.agent_name)] + request.agent_name[: len(request.agent_name)],
                agent_name=request.agent_name,
                parent_tool_use_id=request.parent_tool_use_id,
            )

        return request.make_handle(
            child_session_id="b" * 32,
            target_node=request.definition.executor.node_name or "",
            git_revision=request.git_revision,
            worker_execution_id=f"exec-{request.agent_name}",
            events=_events(),
        )


class _NaturalLanguageBridgeProvider:
    name = "bridge-nl"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = tools
        _ = api_key
        user_messages = [m.get("content") for m in messages if m.get("role") == "user"]
        user_text = user_messages[-1] if user_messages else ""
        last_user_index = max((index for index, message in enumerate(messages) if message.get("role") == "user"), default=-1)
        tool_outputs = self._decode_tool_outputs(messages[last_user_index + 1 :])

        if isinstance(user_text, str) and "你好" in user_text and not tool_outputs:
            return ModelOutput(assistant_text="你好，我可以先研究再写作。", tool_calls=[], usage=None, raw=None)

        if isinstance(user_text, str) and "先研究" in user_text and "摘要" in user_text:
            if "research_step" not in tool_outputs:
                return ModelOutput(
                    assistant_text=None,
                    tool_calls=[
                        ToolCall(
                            tool_use_id="research_step",
                            name="Task",
                            arguments={"agent": "research", "prompt": "RESEARCH_TOPIC::bridge"},
                        )
                    ],
                    usage=None,
                    raw=None,
                )
            if "writer_step" not in tool_outputs:
                research_final = self._task_final_text(tool_outputs.get("research_step")) or "missing"
                return ModelOutput(
                    assistant_text=None,
                    tool_calls=[
                        ToolCall(
                            tool_use_id="writer_step",
                            name="Task",
                            arguments={"agent": "writer", "prompt": f"WRITER_DRAFT::{research_final}"},
                        )
                    ],
                    usage=None,
                    raw=None,
                )
            return ModelOutput(assistant_text="serial route ok", tool_calls=[], usage=None, raw=None)

        return ModelOutput(assistant_text="host ok", tool_calls=[], usage=None, raw=None)

    def _decode_tool_outputs(self, messages) -> dict[str, object]:
        outputs: dict[str, object] = {}
        for message in messages:
            if not isinstance(message, dict) or message.get("role") != "tool":
                continue
            call_id = message.get("tool_call_id")
            content = message.get("content")
            if not isinstance(call_id, str) or not isinstance(content, str):
                continue
            outputs[call_id] = json.loads(content)
        return outputs

    def _task_final_text(self, payload: object) -> str | None:
        if isinstance(payload, dict):
            final_text = payload.get("final_text")
            if isinstance(final_text, str) and final_text:
                return final_text
        return None


class TestRemoteChatBridge(unittest.IsolatedAsyncioTestCase):
    async def test_cluster_chat_host_from_remote_config_inherits_project_prompt_sources(self) -> None:
        from openagentic_sdk.prompt_system import build_system_prompt_text
        from openagentic_sdk.server.cluster_chat_host import build_cluster_chat_host_from_remote_config

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            self._write_remote_cluster_config(root)
            (root / "AGENTS.md").write_text("remote-host-project-rules", encoding="utf-8")

            env = {
                "RIGHTCODE_BASE_URL": "https://rightcode.example.test/v1",
                "RIGHTCODE_API_KEY": "rc-secret",
                "XDG_CONFIG_HOME": str(sandbox / "xdg"),
                "OPENCODE_TEST_HOME": str(sandbox / "home"),
            }
            with mock.patch.dict("os.environ", env, clear=False):
                options, _store, _health_status = build_cluster_chat_host_from_remote_config(
                    repo_root=str(root),
                    session_root=str(sandbox / "session_home"),
                    remote_config_path=str(root / "openagentic.remote.json"),
                    env=env,
                )
                text = build_system_prompt_text(options) or ""

        self.assertIn("project", set(options.setting_sources))
        self.assertIn("remote-host-project-rules", text)

    async def test_remote_worker_from_remote_config_inherits_project_prompt_sources(self) -> None:
        from openagentic_sdk.prompt_system import build_system_prompt_text
        from openagentic_sdk.subagents.remote_http_worker_server import build_remote_http_worker_from_remote_config

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            self._write_remote_cluster_config(root)
            (root / "AGENTS.md").write_text("remote-worker-project-rules", encoding="utf-8")

            env = {
                "RIGHTCODE_BASE_URL": "https://rightcode.example.test/v1",
                "RIGHTCODE_API_KEY": "rc-secret",
                "XDG_CONFIG_HOME": str(sandbox / "xdg"),
                "OPENCODE_TEST_HOME": str(sandbox / "home"),
            }
            with mock.patch.dict("os.environ", env, clear=False):
                options, _store, _health_status = build_remote_http_worker_from_remote_config(
                    repo_root=str(root),
                    session_root=str(sandbox / "session_home"),
                    remote_config_path=str(root / "openagentic.remote.json"),
                    env=env,
                )
                text = build_system_prompt_text(options) or ""

        self.assertIn("project", set(options.setting_sources))
        self.assertIn("remote-worker-project-rules", text)

    async def test_cluster_chat_host_from_remote_config_includes_remote_only_routing_prompt(self) -> None:
        from openagentic_sdk.prompt_system import build_system_prompt_text
        from openagentic_sdk.server.cluster_chat_host import build_cluster_chat_host_from_remote_config

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            self._write_remote_cluster_config(root)

            options, _store, _health_status = build_cluster_chat_host_from_remote_config(
                repo_root=str(root),
                session_root=str(sandbox / "session_home"),
                remote_config_path=str(root / "openagentic.remote.json"),
                env={
                    "RIGHTCODE_BASE_URL": "https://rightcode.example.test/v1",
                    "RIGHTCODE_API_KEY": "rc-secret",
                },
            )
            text = build_system_prompt_text(options) or ""

        self.assertIn("remote cluster routing mode", text.lower())
        self.assertIn("delegate open-ended research", text.lower())
        self.assertIn("`research`", text)
        self.assertIn("`writer`", text)
        self.assertIn("If you are not confident that delegation helps, do the work yourself.", text)

    async def test_remote_worker_from_remote_config_includes_remote_only_routing_prompt(self) -> None:
        from openagentic_sdk.prompt_system import build_system_prompt_text
        from openagentic_sdk.subagents.remote_http_worker_server import build_remote_http_worker_from_remote_config

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            self._write_remote_cluster_config(root)

            options, _store, _health_status = build_remote_http_worker_from_remote_config(
                repo_root=str(root),
                session_root=str(sandbox / "session_home"),
                remote_config_path=str(root / "openagentic.remote.json"),
                env={
                    "RIGHTCODE_BASE_URL": "https://rightcode.example.test/v1",
                    "RIGHTCODE_API_KEY": "rc-secret",
                },
            )
            text = build_system_prompt_text(options) or ""

        self.assertIn("remote cluster routing mode", text.lower())
        self.assertIn("serial route is valid", text.lower())
        self.assertIn("`research`", text)
        self.assertIn("`writer`", text)

    async def test_cluster_chat_host_health_defaults_to_smoke_mode(self) -> None:
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            options = OpenAgenticOptions(
                provider=_BridgeProvider(),
                model="fake",
                api_key="x",
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
                with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/health", timeout=5.0) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5.0)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["deployment_mode"], "smoke")

    async def test_cluster_chat_host_health_reports_provider_status_from_remote_config(self) -> None:
        from openagentic_sdk.server.cluster_chat_host import (
            ClusterChatHostServer,
            build_cluster_chat_host_from_remote_config,
        )

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            self._write_remote_cluster_config(root)
            options, store, health_status = build_cluster_chat_host_from_remote_config(
                repo_root=str(root),
                session_root=str(sandbox / "session_home"),
                remote_config_path=str(root / "openagentic.remote.json"),
                env={
                    "RIGHTCODE_BASE_URL": "https://rightcode.example.test/v1",
                    "RIGHTCODE_API_KEY": "rc-secret",
                },
            )
            httpd = ClusterChatHostServer(
                base_options=options,
                session_store=store,
                host_node_name="node-host",
                health_status=health_status,
            ).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/health", timeout=5.0) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5.0)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["deployment_mode"], "real-model")
        self.assertTrue(payload["provider_ready"])
        self.assertEqual(payload["provider_profiles"], ["rightcode"])
        self.assertEqual(payload["config_source"], str(root / "openagentic.remote.json"))
        self.assertEqual(payload["host_node_name"], "node-host")

    async def test_remote_worker_health_reports_provider_status_from_remote_config(self) -> None:
        from openagentic_sdk.subagents.remote_http import RemoteTaskHttpWorkerServer
        from openagentic_sdk.subagents.remote_http_worker_server import build_remote_http_worker_from_remote_config

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            self._write_remote_cluster_config(root)
            options, store, health_status = build_remote_http_worker_from_remote_config(
                repo_root=str(root),
                session_root=str(sandbox / "session_home"),
                remote_config_path=str(root / "openagentic.remote.json"),
                env={
                    "RIGHTCODE_BASE_URL": "https://rightcode.example.test/v1",
                    "RIGHTCODE_API_KEY": "rc-secret",
                },
            )
            httpd = RemoteTaskHttpWorkerServer(
                base_options=options,
                session_store=store,
                repo_root=str(root),
                node_name="node-worker",
                host="127.0.0.1",
                port=0,
                health_status=health_status,
            ).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/health", timeout=5.0) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5.0)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["deployment_mode"], "real-model")
        self.assertTrue(payload["provider_ready"])
        self.assertEqual(payload["provider_profiles"], ["rightcode"])
        self.assertEqual(payload["config_source"], str(root / "openagentic.remote.json"))
        self.assertEqual(payload["node_name"], "node-worker")

    async def test_cluster_chat_host_from_remote_config_uses_real_provider_api_key(self) -> None:
        from openagentic_sdk.server.cluster_chat_client import ClusterChatClient
        from openagentic_sdk.server.cluster_chat_host import (
            ClusterChatHostServer,
            build_cluster_chat_host_from_remote_config,
        )

        provider_httpd = self._make_responses_stub_server(
            assistant_text="今天是星期六。",
            expected_auth_header="Bearer rc-secret",
        )
        provider_thread = threading.Thread(target=provider_httpd.serve_forever, daemon=True)
        provider_thread.start()
        try:
            with TemporaryDirectory() as td:
                sandbox = Path(td)
                root = sandbox / "repo"
                root.mkdir()
                self._init_git_repo(root)
                self._write_remote_cluster_config(root)
                self._commit_file(root, "openagentic.remote.json", "add remote config")
                options, store, health_status = build_cluster_chat_host_from_remote_config(
                    repo_root=str(root),
                    session_root=str(sandbox / "session_home"),
                    remote_config_path=str(root / "openagentic.remote.json"),
                    env={
                        "RIGHTCODE_BASE_URL": f"http://127.0.0.1:{provider_httpd.server_address[1]}",
                        "RIGHTCODE_API_KEY": "rc-secret",
                    },
                )
                httpd = ClusterChatHostServer(
                    base_options=options,
                    session_store=store,
                    host_node_name="node-host",
                    health_status=health_status,
                ).make_server()
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                try:
                    client = ClusterChatClient(base_url=f"http://127.0.0.1:{httpd.server_address[1]}", timeout_s=1.0)
                    events = [event async for event in client.query(prompt="今天是星期几？")]
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    thread.join(timeout=5.0)
        finally:
            provider_httpd.shutdown()
            provider_httpd.server_close()
            provider_thread.join(timeout=5.0)

        self.assertEqual(getattr(events[-1], "final_text", None), "今天是星期六。")

    async def test_cluster_chat_client_keeps_sse_open_while_host_is_temporarily_idle(self) -> None:
        from openagentic_sdk.server.cluster_chat_client import ClusterChatClient
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            options = OpenAgenticOptions(
                provider=_SlowBridgeProvider(),
                model="fake",
                api_key="x",
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
                client = ClusterChatClient(base_url=f"http://127.0.0.1:{httpd.server_address[1]}", timeout_s=0.2)
                started_at = time.perf_counter()
                events = [e async for e in client.query(prompt="hello")]
                elapsed_s = time.perf_counter() - started_at
                self.assertEqual(getattr(events[-1], "type", None), "result")
                self.assertEqual(getattr(events[-1], "final_text", None), "slow host ok")
                self.assertLess(elapsed_s, 5.0)
            finally:
                httpd.shutdown()
                httpd.server_close()

    async def test_cluster_chat_client_streams_events_and_preserves_resume(self) -> None:
        from openagentic_sdk.server.cluster_chat_client import ClusterChatClient
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            dispatcher = _RecordingRemoteDispatcher()
            options = OpenAgenticOptions(
                provider=_BridgeProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                project_dir=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                remote_task_dispatcher=dispatcher,
                agents={
                    "worker_remote": AgentDefinition(
                        description="remote child",
                        prompt="REMOTE_CHILD_DEF",
                        tools=("Read", "Grep"),
                        executor=AgentExecutorDefinition(kind="k3s", node_name="node-a"),
                        workspace=AgentWorkspaceDefinition(mode="readonly"),
                        worker=AgentWorkerDefinition(profile="py311"),
                    )
                },
            )
            httpd = ClusterChatHostServer(base_options=options, session_store=store).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                client = ClusterChatClient(base_url=f"http://127.0.0.1:{httpd.server_address[1]}", timeout_s=1.0)

                first_events = [e async for e in client.query(prompt="hello")]
                self.assertTrue(first_events)
                self.assertEqual(getattr(first_events[-1], "type", None), "result")
                first_session_id = self._session_id_from(first_events)
                self.assertIsInstance(first_session_id, str)

                second_events = [e async for e in client.query(prompt="delegate now", session_id=first_session_id)]
                self.assertEqual(self._session_id_from(second_events), first_session_id)
                child_events = [e for e in second_events if getattr(e, "agent_name", None) == "worker_remote"]
                self.assertTrue(child_events, "expected child Task events to flow back through remote chat bridge")

                task_results = [
                    e
                    for e in second_events
                    if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", None) == "call_task"
                ]
                self.assertTrue(task_results)
                out = task_results[-1].output
                self.assertEqual(out["dispatch_mode"], "k3s")
                self.assertEqual(out["target_node"], "node-a")
                self.assertEqual(out["worker_execution_id"], "exec-123")
            finally:
                httpd.shutdown()
                httpd.server_close()

    async def test_cluster_chat_client_can_follow_serial_natural_language_route(self) -> None:
        from openagentic_sdk.server.cluster_chat_client import ClusterChatClient
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            dispatcher = _SequencedRemoteDispatcher()
            options = OpenAgenticOptions(
                provider=_NaturalLanguageBridgeProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                project_dir=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                remote_task_dispatcher=dispatcher,
                agents={
                    "research": AgentDefinition(
                        description="Research worker",
                        prompt="REMOTE_RESEARCH_DEF",
                        tools=("Read", "WebSearch"),
                        executor=AgentExecutorDefinition(kind="k3s", node_name="node-a"),
                        workspace=AgentWorkspaceDefinition(mode="readonly"),
                        worker=AgentWorkerDefinition(profile="py311"),
                    ),
                    "writer": AgentDefinition(
                        description="Writer worker",
                        prompt="REMOTE_WRITER_DEF",
                        tools=("Read",),
                        executor=AgentExecutorDefinition(kind="k3s", node_name="node-b"),
                        workspace=AgentWorkspaceDefinition(mode="readonly"),
                        worker=AgentWorkerDefinition(profile="py311"),
                    ),
                },
            )
            httpd = ClusterChatHostServer(base_options=options, session_store=store).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                client = ClusterChatClient(base_url=f"http://127.0.0.1:{httpd.server_address[1]}", timeout_s=1.0)
                events = [e async for e in client.query(prompt="请先研究这个主题，再给我一个摘要。")]
            finally:
                httpd.shutdown()
                httpd.server_close()

        self.assertEqual([request.agent_name for request in dispatcher.requests], ["research", "writer"])
        self.assertEqual([request.definition.executor.node_name for request in dispatcher.requests], ["node-a", "node-b"])

        task_results = [
            e
            for e in events
            if getattr(e, "type", None) == "tool.result"
            and isinstance(getattr(e, "output", None), dict)
            and getattr(e, "output", {}).get("dispatch_mode") == "k3s"
        ]
        self.assertEqual(len(task_results), 2)
        self.assertEqual(task_results[0].output["target_node"], "node-a")
        self.assertEqual(task_results[1].output["target_node"], "node-b")
        self.assertEqual(getattr(events[-1], "final_text", None), "serial route ok")

    async def test_run_chat_uses_remote_bridge_when_base_url_is_configured(self) -> None:
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            dispatcher = _RecordingRemoteDispatcher()
            host_options = OpenAgenticOptions(
                provider=_BridgeProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                project_dir=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                remote_task_dispatcher=dispatcher,
                agents={
                    "worker_remote": AgentDefinition(
                        description="remote child",
                        prompt="REMOTE_CHILD_DEF",
                        tools=("Read", "Grep"),
                        executor=AgentExecutorDefinition(kind="k3s", node_name="node-a"),
                        workspace=AgentWorkspaceDefinition(mode="readonly"),
                        worker=AgentWorkerDefinition(profile="py311"),
                    )
                },
            )
            httpd = ClusterChatHostServer(base_options=host_options, session_store=store).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                client_options = OpenAgenticOptions(
                    provider=_BridgeOnlyProvider(),
                    model="bridge",
                    cwd=str(root),
                    project_dir=str(root),
                    permission_gate=PermissionGate(permission_mode="bypass"),
                    remote_chat_base_url=f"http://127.0.0.1:{httpd.server_address[1]}",
                    remote_chat_timeout_s=1.0,
                )
                stdin = StringIO("delegate now\n/exit\n")
                stdout = StringIO()
                rc = await run_chat(
                    client_options,
                    color_config=StyleConfig(color="never"),
                    debug=False,
                    stdin=stdin,
                    stdout=stdout,
                )
                rendered = stdout.getvalue()
                self.assertEqual(rc, 0)
                self.assertIn("remote child says hi", rendered)
                self.assertIn("host delegated", rendered)
            finally:
                httpd.shutdown()
                httpd.server_close()

    async def test_run_chat_warns_when_remote_host_is_smoke_only(self) -> None:
        from openagentic_sdk.server.cluster_chat_host import ClusterChatHostServer

        with TemporaryDirectory() as td:
            sandbox = Path(td)
            root = sandbox / "repo"
            root.mkdir()
            self._init_git_repo(root)
            store = FileSessionStore(root_dir=sandbox / "session_home")
            host_options = OpenAgenticOptions(
                provider=_BridgeProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                project_dir=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
            )
            httpd = ClusterChatHostServer(base_options=host_options, session_store=store).make_server()
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                client_options = OpenAgenticOptions(
                    provider=_BridgeOnlyProvider(),
                    model="bridge",
                    cwd=str(root),
                    project_dir=str(root),
                    permission_gate=PermissionGate(permission_mode="bypass"),
                    remote_chat_base_url=f"http://127.0.0.1:{httpd.server_address[1]}",
                    remote_chat_timeout_s=1.0,
                )
                stdin = StringIO("/exit\n")
                stdout = StringIO()
                rc = await run_chat(
                    client_options,
                    color_config=StyleConfig(color="never"),
                    debug=False,
                    stdin=stdin,
                    stdout=stdout,
                )
                rendered = stdout.getvalue()
                self.assertEqual(rc, 0)
                self.assertIn("warning: remote host is smoke-only", rendered)
            finally:
                httpd.shutdown()
                httpd.server_close()

    async def test_cluster_chat_client_fails_fast_when_host_is_unreachable(self) -> None:
        from openagentic_sdk.server.cluster_chat_client import ClusterChatClient

        client = ClusterChatClient(base_url="http://127.0.0.1:9", timeout_s=0.2)
        with self.assertRaises(RuntimeError):
            async for _ in client.query(prompt="hello"):
                pass

    def _init_git_repo(self, root: Path) -> None:
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
        (root / "README.md").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, text=True)

    def _write_remote_cluster_config(self, root: Path) -> None:
        (root / "openagentic.remote.json").write_text(
            json.dumps(
                {
                    "providers": {
                        "rightcode": {
                            "kind": "openai_responses",
                            "base_url_env": "RIGHTCODE_BASE_URL",
                            "api_key_env": "RIGHTCODE_API_KEY",
                            "default_model": "gpt-5.2",
                        }
                    },
                    "host": {"provider": "rightcode", "model": "gpt-5.2"},
                    "agents": {
                        "research": {
                            "description": "research worker",
                            "prompt": "You are a research worker.",
                            "tools": ["Read", "WebSearch"],
                            "provider": "rightcode",
                            "model": "gpt-5.2-mini",
                            "executor": {"kind": "k3s", "node_name": "node-worker"},
                            "workspace": {"mode": "readonly"},
                        },
                        "writer": {
                            "description": "writer worker",
                            "prompt": "You are a writing worker.",
                            "tools": ["Read", "Glob", "Grep"],
                            "provider": "rightcode",
                            "model": "gpt-5.2-mini",
                            "executor": {"kind": "k3s", "node_name": "node-writer"},
                            "workspace": {"mode": "readonly"},
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _commit_file(self, root: Path, relative_path: str, message: str) -> None:
        subprocess.run(["git", "add", relative_path], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", message], cwd=root, check=True, capture_output=True, text=True)

    def _make_responses_stub_server(
        self,
        *,
        assistant_text: str,
        expected_auth_header: str | None = None,
    ) -> ThreadingHTTPServer:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                if self.path != "/responses":
                    self.send_response(404)
                    self.end_headers()
                    return
                if expected_auth_header is not None and self.headers.get("Authorization") != expected_auth_header:
                    self.send_response(401)
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length") or "0")
                payload = json.loads((self.rfile.read(length) if length > 0 else b"{}").decode("utf-8"))
                if payload.get("stream") is True:
                    chunks = [
                        'data: {"type":"response.created","response":{"id":"resp_test"}}\n\n',
                        f'data: {json.dumps({"type": "response.output_item.added", "output_index": 0, "item": {"id": "msg_1", "type": "message"}}, ensure_ascii=False)}\n\n',
                        f'data: {json.dumps({"type": "response.output_text.delta", "item_id": "msg_1", "delta": assistant_text}, ensure_ascii=False)}\n\n',
                        'data: {"type":"response.completed","response":{"id":"resp_test","usage":{"total_tokens":10}}}\n\n',
                        "data: [DONE]\n\n",
                    ]
                    raw = "".join(chunks).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return

                raw = json.dumps(
                    {
                        "id": "resp_test",
                        "output": [
                            {
                                "type": "message",
                                "content": [{"type": "output_text", "text": assistant_text}],
                            }
                        ],
                        "usage": {"total_tokens": 10},
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                _ = (format, args)

        return ThreadingHTTPServer(("127.0.0.1", 0), Handler)

    def _session_id_from(self, events: list[object]) -> str:
        for event in events:
            if getattr(event, "type", None) == "system.init":
                session_id = getattr(event, "session_id", None)
                if isinstance(session_id, str) and session_id:
                    return session_id
        raise AssertionError("system.init missing from remote chat events")


if __name__ == "__main__":
    unittest.main()
