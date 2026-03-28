from __future__ import annotations

import asyncio
import unittest

from e2e_k3d_tests._harness import AGENT_A_NODE, authoritative_repo_root, ensure_cluster_ready, port_forward_chat_host
from openagentic_sdk.server.cluster_chat_client import ClusterChatClient


class TestRemoteChatSyncAfterSession(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_cluster_ready()

    async def test_dirty_authoritative_worktree_blocks_sync_until_cleared(self) -> None:
        with port_forward_chat_host() as base_url:
            client = ClusterChatClient(base_url=base_url, timeout_s=5.0)
            first_events = [event async for event in client.query(prompt="CHAT_PING")]
            session_id = self._session_id_from(first_events)

            dirty_marker = authoritative_repo_root() / "DIRTY_SYNC_MARKER.tmp"
            dirty_marker.write_text("dirty\n", encoding="utf-8")
            try:
                with self.assertRaises(RuntimeError) as cm:
                    async for _event in client.query(prompt="CHAT_PING", session_id=session_id):
                        pass
                self.assertIn("dirty-worktree", str(cm.exception))
            finally:
                dirty_marker.unlink(missing_ok=True)

            clean_events = await self._query_task_with_retry(client=client, session_id=session_id, prompt="TASK_A")
            task_results = [
                event
                for event in clean_events
                if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
            ]
            self.assertTrue(task_results)
            self.assertEqual(task_results[-1].output["target_node"], AGENT_A_NODE)

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
