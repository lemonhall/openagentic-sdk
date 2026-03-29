from __future__ import annotations

import asyncio
import json
import time
import unittest
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from e2e_k3d_tests._harness import ensure_tracing_ready, port_forward_chat_host, port_forward_jaeger_query
from openagentic_sdk.server.cluster_chat_client import ClusterChatClient


class TestRemoteActorTraceSmoke(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_tracing_ready()

    async def test_jaeger_receives_cluster_chat_host_to_remote_subagent_trace(self) -> None:
        with port_forward_chat_host() as base_url:
            client = ClusterChatClient(base_url=base_url, timeout_s=5.0)
            events = await self._query_task_with_retry(
                client=client,
                prompt="请研究一下 v56 的 remote subagent 路由方案。",
            )

        task_results = [
            event
            for event in events
            if getattr(event, "type", None) == "tool.result"
            and isinstance(getattr(event, "output", None), dict)
            and getattr(event, "output", {}).get("dispatch_mode") == "k3s"
        ]
        self.assertEqual(len(task_results), 1)

        with port_forward_jaeger_query() as jaeger_base_url:
            trace = self._wait_for_actor_trace(jaeger_base_url, service_name="oa-cluster-chat-host")

        tag_keys = {tag["key"] for span in trace.get("spans", []) for tag in span.get("tags", []) if isinstance(tag, dict)}
        services = {
            process.get("serviceName")
            for process in trace.get("processes", {}).values()
            if isinstance(process, dict)
        }
        self.assertIn("oa.execution.id", tag_keys)
        self.assertIn("oa.agent.name", tag_keys)
        self.assertIn("oa.dispatch.mode", tag_keys)
        self.assertIn("oa-cluster-chat-host", services)
        self.assertIn("oa-remote-worker", services)

    async def _query_task_with_retry(self, *, client: ClusterChatClient, prompt: str) -> list[object]:
        for attempt in range(2):
            events = [event async for event in client.query(prompt=prompt)]
            task_results = [
                event
                for event in events
                if getattr(event, "type", None) == "tool.result"
                and isinstance(getattr(event, "output", None), dict)
                and getattr(event, "output", {}).get("dispatch_mode") == "k3s"
            ]
            if task_results:
                return events
            if attempt == 0:
                await asyncio.sleep(1.0)
        return events

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
