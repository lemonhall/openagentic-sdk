from __future__ import annotations

import unittest


class TestActorMailboxStore(unittest.TestCase):
    def _env(self, *, message_id: str, seq: int) -> object:
        from openagentic_sdk.subagents.actor_protocol import ActorEnvelope

        return ActorEnvelope(
            protocol_version="v1",
            message_id=message_id,
            execution_id="exec-1",
            sender_actor_id="worker",
            recipient_actor_id="host",
            mailbox="child_events",
            seq=seq,
            kind="child_event",
            payload={"seq": seq},
            ts=100.0 + seq,
        )

    def test_mailbox_appends_in_order(self) -> None:
        from openagentic_sdk.subagents.actor_mailbox import ActorMailboxStore

        store = ActorMailboxStore()
        first = self._env(message_id="msg-1", seq=1)
        second = self._env(message_id="msg-2", seq=2)

        self.assertTrue(store.append(first))
        self.assertTrue(store.append(second))
        self.assertEqual(store.head_seq("exec-1", "child_events"), 2)
        self.assertEqual(store.list_mailbox("exec-1", "child_events"), [first, second])

    def test_duplicate_message_id_is_ignored(self) -> None:
        from openagentic_sdk.subagents.actor_mailbox import ActorMailboxStore

        store = ActorMailboxStore()
        first = self._env(message_id="msg-1", seq=1)
        duplicate = self._env(message_id="msg-1", seq=1)

        self.assertTrue(store.append(first))
        self.assertFalse(store.append(duplicate))
        self.assertEqual(store.list_mailbox("exec-1", "child_events"), [first])

    def test_out_of_order_seq_fails(self) -> None:
        from openagentic_sdk.subagents.actor_mailbox import ActorMailboxStore

        store = ActorMailboxStore()

        with self.assertRaises(ValueError):
            store.append(self._env(message_id="msg-2", seq=2))

    def test_registry_can_report_state_and_mailbox_head(self) -> None:
        from openagentic_sdk.subagents.actor_mailbox import ActorMailboxStore
        from openagentic_sdk.subagents.actor_registry import ActorExecutionRegistry

        store = ActorMailboxStore()
        registry = ActorExecutionRegistry()
        registry.register_execution(
            execution_id="exec-1",
            agent_name="worker",
            dispatch_mode="local",
        )
        registry.update_state("exec-1", "running")

        self.assertTrue(store.append(self._env(message_id="msg-1", seq=1)))
        registry.record_mailbox_head("exec-1", mailbox="child_events", seq=store.head_seq("exec-1", "child_events"))

        record = registry.get("exec-1")
        self.assertEqual(record.execution_id, "exec-1")
        self.assertEqual(record.agent_name, "worker")
        self.assertEqual(record.dispatch_mode, "local")
        self.assertEqual(record.state, "running")
        self.assertEqual(record.mailbox_heads["child_events"], 1)


if __name__ == "__main__":
    unittest.main()
