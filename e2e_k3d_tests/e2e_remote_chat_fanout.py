from __future__ import annotations

import asyncio
import unittest

from e2e_k3d_tests._harness import AGENT_A_NODE, ensure_cluster_ready, port_forward_chat_host
from openagentic_sdk.server.cluster_chat_client import ClusterChatClient


class TestRemoteChatFanout(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_cluster_ready()

    async def test_local_client_can_request_parallel_research_fanout_and_receive_summary(self) -> None:
        with port_forward_chat_host() as base_url:
            client = ClusterChatClient(base_url=base_url, timeout_s=5.0)
            events = await self._query_task_with_retry(
                client=client,
                prompt="请并发研究四个方向，并把结果汇总给我。",
            )
            task_results = self._successful_task_results(events)
            self.assertEqual(len(task_results), 4)
            self.assertTrue(all(event.output["target_node"] == AGENT_A_NODE for event in task_results))

            child_results = [
                event
                for event in events
                if getattr(event, "type", None) == "result" and getattr(event, "agent_name", None) == "research"
            ]
            self.assertEqual(len(child_results), 4)
            self.assertTrue(all(AGENT_A_NODE in event.final_text for event in child_results))

            final_results = [event for event in events if getattr(event, "type", None) == "result" and getattr(event, "agent_name", None) is None]
            self.assertTrue(final_results)
            self.assertIn("FANOUT_SUMMARY", final_results[-1].final_text)

    async def _query_task_with_retry(self, *, client: ClusterChatClient, prompt: str) -> list[object]:
        for attempt in range(2):
            events = [event async for event in client.query(prompt=prompt)]
            if len(self._successful_task_results(events)) >= 4:
                return events
            if attempt == 0:
                await asyncio.sleep(1.0)
        return events

    def _successful_task_results(self, events: list[object]) -> list[object]:
        return [
            event
            for event in events
            if getattr(event, "type", None) == "tool.result"
            and isinstance(getattr(event, "output", None), dict)
            and getattr(event, "output", {}).get("dispatch_mode") == "k3s"
        ]


if __name__ == "__main__":
    unittest.main()
