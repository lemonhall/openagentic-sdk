from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, cast

ActorEnvelopeKind = Literal[
    "spawn",
    "control",
    "child_event",
    "ack",
    "down",
    "abort",
    "replay",
    "close",
]

_ALLOWED_KINDS: set[str] = {
    "spawn",
    "control",
    "child_event",
    "ack",
    "down",
    "abort",
    "replay",
    "close",
}


@dataclass(frozen=True, slots=True)
class ActorEnvelope:
    protocol_version: str
    message_id: str
    execution_id: str
    sender_actor_id: str
    recipient_actor_id: str
    mailbox: str
    seq: int
    kind: ActorEnvelopeKind
    payload: Any
    ts: float

    def __post_init__(self) -> None:
        for field_name in (
            "protocol_version",
            "message_id",
            "execution_id",
            "sender_actor_id",
            "recipient_actor_id",
            "mailbox",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.seq, int) or self.seq <= 0:
            raise ValueError("seq must be a positive int")
        if cast(str, self.kind) not in _ALLOWED_KINDS:
            raise ValueError(f"unsupported actor envelope kind: {self.kind!r}")
        if not isinstance(self.ts, (int, float)):
            raise ValueError("ts must be numeric")

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "message_id": self.message_id,
            "execution_id": self.execution_id,
            "sender_actor_id": self.sender_actor_id,
            "recipient_actor_id": self.recipient_actor_id,
            "mailbox": self.mailbox,
            "seq": self.seq,
            "kind": self.kind,
            "payload": self.payload,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ActorEnvelope:
        if not isinstance(raw, Mapping):
            raise ValueError("raw envelope must be a mapping")
        required = (
            "protocol_version",
            "message_id",
            "execution_id",
            "sender_actor_id",
            "recipient_actor_id",
            "mailbox",
            "seq",
            "kind",
            "payload",
            "ts",
        )
        missing = [name for name in required if name not in raw]
        if missing:
            raise ValueError(f"missing actor envelope fields: {', '.join(missing)}")
        return cls(
            protocol_version=cast(str, raw["protocol_version"]),
            message_id=cast(str, raw["message_id"]),
            execution_id=cast(str, raw["execution_id"]),
            sender_actor_id=cast(str, raw["sender_actor_id"]),
            recipient_actor_id=cast(str, raw["recipient_actor_id"]),
            mailbox=cast(str, raw["mailbox"]),
            seq=cast(int, raw["seq"]),
            kind=cast(ActorEnvelopeKind, raw["kind"]),
            payload=raw["payload"],
            ts=float(raw["ts"]),
        )
