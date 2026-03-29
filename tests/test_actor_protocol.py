from __future__ import annotations

import unittest


class TestActorProtocol(unittest.TestCase):
    def test_envelope_roundtrip_is_stable(self) -> None:
        from openagentic_sdk.subagents.actor_protocol import ActorEnvelope

        envelope = ActorEnvelope(
            protocol_version="v1",
            message_id="msg-1",
            execution_id="exec-1",
            sender_actor_id="host",
            recipient_actor_id="worker",
            mailbox="child_events",
            seq=1,
            kind="child_event",
            payload={"type": "assistant.message", "text": "hello"},
            ts=123.45,
        )

        self.assertEqual(ActorEnvelope.from_dict(envelope.to_dict()), envelope)

    def test_invalid_kind_fails_fast(self) -> None:
        from openagentic_sdk.subagents.actor_protocol import ActorEnvelope

        with self.assertRaises(ValueError):
            ActorEnvelope(
                protocol_version="v1",
                message_id="msg-1",
                execution_id="exec-1",
                sender_actor_id="host",
                recipient_actor_id="worker",
                mailbox="child_events",
                seq=1,
                kind="bogus",
                payload={},
                ts=123.45,
            )

    def test_missing_required_field_fails_from_dict(self) -> None:
        from openagentic_sdk.subagents.actor_protocol import ActorEnvelope

        with self.assertRaises(ValueError):
            ActorEnvelope.from_dict(
                {
                    "protocol_version": "v1",
                    "message_id": "msg-1",
                    "sender_actor_id": "host",
                    "recipient_actor_id": "worker",
                    "mailbox": "child_events",
                    "seq": 1,
                    "kind": "child_event",
                    "payload": {},
                    "ts": 123.45,
                }
            )


if __name__ == "__main__":
    unittest.main()
