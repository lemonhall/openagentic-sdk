from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import openagentic_sdk
from e2e_k3d_tests._harness import (
    AGENT_A_NODE,
    authoritative_repo_root,
    build_dispatcher,
    ensure_tracing_ready,
    port_forward_jaeger_query,
    port_forward_otel_collector_http,
)
from openagentic_sdk.options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkspaceDefinition,
    OpenAgenticOptions,
)
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.tools.defaults import default_tool_registry


class _ParentTraceProvider:
    name = "k3d-trace-parent"

    def __init__(self) -> None:
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
                        arguments={"agent": "trace_worker", "prompt": "REPORT_NODE"},
                    )
                ],
                usage=None,
                raw=None,
            )
        return ModelOutput(assistant_text="trace parent ok", tool_calls=[], usage=None, raw=None)


class TestRemoteActorTraceSmoke(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_tracing_ready()

    async def test_jaeger_receives_host_to_remote_subagent_trace(self) -> None:
        workspace_root = authoritative_repo_root()
        with port_forward_otel_collector_http() as collector_base_url:
            previous_env = _apply_trace_env(
                service_name="oa-test-k3d-host",
                collector_base_url=collector_base_url,
            )
            try:
                with TemporaryDirectory() as td:
                    store = FileSessionStore(root_dir=Path(td) / "sessions")
                    options = OpenAgenticOptions(
                        provider=_ParentTraceProvider(),
                        model="fake",
                        api_key="x",
                        cwd=str(workspace_root),
                        project_dir=str(workspace_root),
                        tools=default_tool_registry(),
                        permission_gate=PermissionGate(permission_mode="bypass"),
                        session_store=store,
                        remote_task_dispatcher=build_dispatcher(),
                        agents={
                            "trace_worker": AgentDefinition(
                                description="k3d trace smoke worker",
                                prompt="REMOTE_K3D_DEF",
                                tools=("Read",),
                                executor=AgentExecutorDefinition(kind="k3s", node_name=AGENT_A_NODE),
                                workspace=AgentWorkspaceDefinition(mode="readonly"),
                            )
                        },
                    )
                    events = [event async for event in openagentic_sdk.query(prompt="dispatch remote trace task", options=options)]
                    task_results = [
                        event
                        for event in events
                        if getattr(event, "type", None) == "tool.result"
                        and isinstance(getattr(event, "output", None), dict)
                        and getattr(event, "output", {}).get("dispatch_mode") == "k3s"
                    ]
                    self.assertEqual(len(task_results), 1)
                    tracing = options.runtime_state.actor_tracing
                    if tracing is not None:
                        tracing.shutdown()
            finally:
                _restore_env(previous_env)

        with port_forward_jaeger_query() as jaeger_base_url:
            trace = self._wait_for_actor_trace(jaeger_base_url, service_name="oa-test-k3d-host")

        tag_keys = {tag["key"] for span in trace.get("spans", []) for tag in span.get("tags", []) if isinstance(tag, dict)}
        services = {
            process.get("serviceName")
            for process in trace.get("processes", {}).values()
            if isinstance(process, dict)
        }
        self.assertIn("oa.execution.id", tag_keys)
        self.assertIn("oa.agent.name", tag_keys)
        self.assertIn("oa.dispatch.mode", tag_keys)
        self.assertIn("oa-test-k3d-host", services)
        self.assertIn("oa-remote-worker", services)

    def _wait_for_actor_trace(self, base_url: str, *, service_name: str) -> dict[str, object]:
        deadline = time.time() + 30.0
        last_payload: dict[str, object] = {}
        while time.time() < deadline:
            payload = _load_json(
                f"{base_url}/api/traces?{urllib_parse.urlencode({'service': service_name, 'limit': '20'})}"
            )
            last_payload = payload
            data = payload.get("data")
            if not isinstance(data, list):
                time.sleep(1.0)
                continue
            for trace in data:
                if _is_actor_trace(trace, service_name=service_name):
                    return trace
            time.sleep(1.0)
        raise AssertionError(f"actor trace not found in Jaeger payload: {last_payload}")


def _load_json(url: str) -> dict[str, object]:
    with urllib_request.urlopen(url, timeout=10.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _apply_trace_env(*, service_name: str, collector_base_url: str) -> dict[str, str | None]:
    patch = {
        "OTEL_SERVICE_NAME": service_name,
        "OTEL_EXPORTER_OTLP_ENDPOINT": collector_base_url,
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": f"{collector_base_url}/v1/traces",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OA_DISABLE_ACTOR_TRACING": None,
    }
    previous = {key: os.environ.get(key) for key in patch}
    for key, value in patch.items():
        if value is None:
            os.environ.pop(key, None)
            continue
        os.environ[key] = value
    return previous


def _restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
            continue
        os.environ[key] = value


def _is_actor_trace(raw_trace: object, *, service_name: str) -> bool:
    if not isinstance(raw_trace, dict):
        return False
    spans = raw_trace.get("spans")
    processes = raw_trace.get("processes")
    if not isinstance(spans, list) or not isinstance(processes, dict):
        return False
    services = {
        process.get("serviceName")
        for process in processes.values()
        if isinstance(process, dict) and isinstance(process.get("serviceName"), str)
    }
    if service_name not in services or "oa-remote-worker" not in services:
        return False
    tag_keys = {tag.get("key") for span in spans if isinstance(span, dict) for tag in span.get("tags", []) if isinstance(tag, dict)}
    return {"oa.execution.id", "oa.agent.name", "oa.dispatch.mode"}.issubset(tag_keys)


if __name__ == "__main__":
    unittest.main()
