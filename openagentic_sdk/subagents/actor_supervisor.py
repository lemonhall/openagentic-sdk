from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .actor_lifecycle import ActorDownEvent

SupervisorPolicy = Literal["no_restart", "retry_once_on_transport_loss", "fail_parent_tool_use"]
SupervisorAction = Literal["accept_result", "retry", "fail_parent_tool_use"]


@dataclass(frozen=True, slots=True)
class SupervisorDecision:
    action: SupervisorAction
    policy: SupervisorPolicy
    retry_count: int
    reason: str

    def to_payload(self) -> dict[str, str | int]:
        return {
            "action": self.action,
            "policy": self.policy,
            "retry_count": self.retry_count,
            "reason": self.reason,
        }


class ActorSupervisor:
    @staticmethod
    def decide(
        *,
        policy: SupervisorPolicy,
        down: ActorDownEvent,
        retry_count: int,
    ) -> SupervisorDecision:
        if down.reason_kind == "normal":
            return SupervisorDecision(
                action="accept_result",
                policy=policy,
                retry_count=retry_count,
                reason="child_exited_normally",
            )
        if policy == "retry_once_on_transport_loss" and down.reason_kind == "transport_lost" and retry_count == 0:
            return SupervisorDecision(
                action="retry",
                policy=policy,
                retry_count=retry_count,
                reason="retry_once_on_transport_loss",
            )
        return SupervisorDecision(
            action="fail_parent_tool_use",
            policy=policy,
            retry_count=retry_count,
            reason=down.reason_kind,
        )
