from __future__ import annotations

import asyncio
import unittest

from e2e_k3d_tests._harness import AGENT_A_NODE, ensure_cluster_ready, port_forward_chat_host
from openagentic_sdk.server.cluster_chat_client import ClusterChatClient


class TestRemoteChatBasic(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_cluster_ready()

    async def test_local_client_can_chat_with_cluster_host_and_receive_task_events(self) -> None:
        with port_forward_chat_host() as base_url:
            client = ClusterChatClient(base_url=base_url, timeout_s=5.0)

            first_events = [event async for event in client.query(prompt="CHAT_PING")]
            first_session_id = self._session_id_from(first_events)
            self.assertTrue(any(getattr(event, "type", None) == "assistant.message" for event in first_events))

            second_events = await self._query_task_with_retry(client=client, session_id=first_session_id, prompt="TASK_A")
            self.assertEqual(self._session_id_from(second_events), first_session_id)

            task_results = [
                event
                for event in second_events
                if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
            ]
            self.assertTrue(task_results)
            output = task_results[-1].output
            self.assertEqual(output["dispatch_mode"], "k3s")
            self.assertEqual(output["target_node"], AGENT_A_NODE)
            self.assertTrue(isinstance(output.get("worker_execution_id"), str) and output["worker_execution_id"])

            child_results = [
                event
                for event in second_events
                if getattr(event, "type", None) == "result" and getattr(event, "agent_name", None) == "worker_a"
            ]
            self.assertTrue(child_results)
            self.assertIn(AGENT_A_NODE, child_results[-1].final_text)

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
            task_results = [
                event
                for event in events
                if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
            ]
            if task_results and isinstance(task_results[-1].output, dict):
                return events
            if attempt == 0:
                await asyncio.sleep(1.0)
        return events


if __name__ == "__main__":
    unittest.main()
