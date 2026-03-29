from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ActorDispatchMode = Literal["local", "k3s"]
ActorExecutionState = Literal["created", "running", "exited", "failed", "aborted", "closed"]


@dataclass(slots=True)
class ActorExecutionRecord:
    execution_id: str
    agent_name: str
    dispatch_mode: ActorDispatchMode
    state: ActorExecutionState = "created"
    target_node: str | None = None
    worker_execution_id: str | None = None
    mailbox_heads: dict[str, int] = field(default_factory=dict)


class ActorExecutionRegistry:
    def __init__(self) -> None:
        self._records: dict[str, ActorExecutionRecord] = {}

    def register_execution(
        self,
        *,
        execution_id: str,
        agent_name: str,
        dispatch_mode: ActorDispatchMode,
        target_node: str | None = None,
        worker_execution_id: str | None = None,
    ) -> ActorExecutionRecord:
        if execution_id in self._records:
            raise ValueError(f"execution already registered: {execution_id}")
        record = ActorExecutionRecord(
            execution_id=execution_id,
            agent_name=agent_name,
            dispatch_mode=dispatch_mode,
            target_node=target_node,
            worker_execution_id=worker_execution_id,
        )
        self._records[execution_id] = record
        return record

    def get(self, execution_id: str) -> ActorExecutionRecord:
        try:
            return self._records[execution_id]
        except KeyError as exc:
            raise KeyError(f"unknown execution_id: {execution_id}") from exc

    def update_state(self, execution_id: str, state: ActorExecutionState) -> ActorExecutionRecord:
        record = self.get(execution_id)
        record.state = state
        return record

    def record_mailbox_head(self, execution_id: str, *, mailbox: str, seq: int) -> ActorExecutionRecord:
        if seq < 0:
            raise ValueError("seq must be non-negative")
        record = self.get(execution_id)
        record.mailbox_heads[mailbox] = seq
        return record
