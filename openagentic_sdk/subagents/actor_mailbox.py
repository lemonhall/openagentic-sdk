from __future__ import annotations

from collections import defaultdict

from .actor_protocol import ActorEnvelope


class ActorMailboxStore:
    def __init__(self) -> None:
        self._mailboxes: dict[tuple[str, str], list[ActorEnvelope]] = defaultdict(list)
        self._seen_message_ids: dict[str, set[str]] = defaultdict(set)

    def append(self, envelope: ActorEnvelope) -> bool:
        seen = self._seen_message_ids[envelope.execution_id]
        if envelope.message_id in seen:
            return False
        key = (envelope.execution_id, envelope.mailbox)
        messages = self._mailboxes[key]
        expected_seq = len(messages) + 1
        if envelope.seq != expected_seq:
            raise ValueError(
                f"out-of-order envelope for execution={envelope.execution_id!r} mailbox={envelope.mailbox!r}: "
                f"expected seq {expected_seq}, got {envelope.seq}"
            )
        messages.append(envelope)
        seen.add(envelope.message_id)
        return True

    def head_seq(self, execution_id: str, mailbox: str) -> int:
        return len(self._mailboxes[(execution_id, mailbox)])

    def next_seq(self, execution_id: str, mailbox: str) -> int:
        return self.head_seq(execution_id, mailbox) + 1

    def list_mailbox(self, execution_id: str, mailbox: str) -> list[ActorEnvelope]:
        return list(self._mailboxes[(execution_id, mailbox)])

    def read_from(self, execution_id: str, mailbox: str, *, after_seq: int = 0) -> list[ActorEnvelope]:
        return [env for env in self._mailboxes[(execution_id, mailbox)] if env.seq > after_seq]
