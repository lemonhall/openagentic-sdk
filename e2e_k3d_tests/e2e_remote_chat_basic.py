from __future__ import annotations

import asyncio
import unittest

from e2e_k3d_tests._harness import AGENT_A_NODE, AGENT_B_NODE, ensure_cluster_ready, port_forward_chat_host
from openagentic_sdk.server.cluster_chat_client import ClusterChatClient


class TestRemoteChatBasic(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_cluster_ready()

    async def test_local_client_can_chat_with_cluster_host_and_receive_task_events(self) -> None:
        with port_forward_chat_host() as base_url:
            client = ClusterChatClient(base_url=base_url, timeout_s=5.0)

            first_events = [event async for event in client.query(prompt="你好啊")]
            first_session_id = self._session_id_from(first_events)
            assistant_messages = [event for event in first_events if getattr(event, "type", None) == "assistant.message"]
            self.assertTrue(assistant_messages)
            self.assertIn("你好", assistant_messages[-1].text)

            second_events = await self._query_task_with_retry(
                client=client,
                session_id=first_session_id,
                prompt="请先研究一下 v56 的 remote subagent 路由方案，再根据研究结果写一个简短摘要。",
            )
            self.assertEqual(self._session_id_from(second_events), first_session_id)

            task_results = self._successful_task_results(second_events)
            self.assertEqual(len(task_results), 2)
            targets = {event.output["target_node"] for event in task_results}
            self.assertEqual(targets, {AGENT_A_NODE, AGENT_B_NODE})
            self.assertTrue(all(event.output["dispatch_mode"] == "k3s" for event in task_results))
            self.assertTrue(all(isinstance(event.output.get("worker_execution_id"), str) and event.output["worker_execution_id"] for event in task_results))

            research_results = [
                event
                for event in second_events
                if getattr(event, "type", None) == "result" and getattr(event, "agent_name", None) == "research"
            ]
            writer_results = [
                event
                for event in second_events
                if getattr(event, "type", None) == "result" and getattr(event, "agent_name", None) == "writer"
            ]
            self.assertTrue(research_results)
            self.assertTrue(writer_results)
            self.assertIn(AGENT_A_NODE, research_results[-1].final_text)
            self.assertIn(AGENT_B_NODE, writer_results[-1].final_text)

    def _session_id_from(self, events: list[object]) -> str:
        for event in events:
            if getattr(event, "type", None) == "system.init":
                session_id = getattr(event, "session_id", None)
                if isinstance(session_id, str) and session_id:
                    return session_id
        raise AssertionError("system.init missing from remote chat events")

    async def _query_task_with_retry(self, *, client: ClusterChatClient, session_id: str, prompt: str) -> list[object]:
        for attempt in range(2):
            events = [event async for event in client.query(prompt=prompt, session_id=session_id)]
            task_results = self._successful_task_results(events)
            if task_results:
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
