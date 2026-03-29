from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping

from ..events import Result

ActorDownReasonKind = Literal["normal", "child_exit_error", "transport_lost", "remote_worker_error", "aborted"]
ActorDownFinalState = Literal["exited", "failed", "aborted"]


class RemoteWorkerStreamError(RuntimeError):
    def __init__(self, *, error_type: str, error_message: str) -> None:
        self.remote_error_type = error_type
        self.remote_error_message = error_message
        super().__init__(f"Remote task worker stream failed ({error_type}): {error_message}")


@dataclass(frozen=True, slots=True)
class ActorDownEvent:
    execution_id: str
    actor_id: str
    reason_kind: ActorDownReasonKind
    final_state: ActorDownFinalState
    dispatch_mode: str
    reason_detail: str | None = None
    child_session_id: str | None = None
    target_node: str | None = None
    worker_execution_id: str | None = None

    def to_payload(self) -> dict[str, str]:
        return {
            key: value
            for key, value in asdict(self).items()
            if isinstance(value, str) and value
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ActorDownEvent":
        execution_id = payload.get("execution_id")
        actor_id = payload.get("actor_id")
        reason_kind = payload.get("reason_kind")
        final_state = payload.get("final_state")
        dispatch_mode = payload.get("dispatch_mode")
        if not all(isinstance(item, str) and item for item in (execution_id, actor_id, reason_kind, final_state, dispatch_mode)):
            raise ValueError("invalid actor down payload")
        return cls(
            execution_id=execution_id,
            actor_id=actor_id,
            reason_kind=reason_kind,
            final_state=final_state,
            dispatch_mode=dispatch_mode,
            reason_detail=payload.get("reason_detail") if isinstance(payload.get("reason_detail"), str) else None,
            child_session_id=payload.get("child_session_id") if isinstance(payload.get("child_session_id"), str) else None,
            target_node=payload.get("target_node") if isinstance(payload.get("target_node"), str) else None,
            worker_execution_id=payload.get("worker_execution_id")
            if isinstance(payload.get("worker_execution_id"), str)
            else None,
        )


def classify_child_result_down(
    *,
    execution_id: str,
    actor_id: str,
    dispatch_mode: str,
    result: Result | None,
    child_session_id: str | None = None,
    target_node: str | None = None,
    worker_execution_id: str | None = None,
) -> ActorDownEvent:
    if result is None:
        return ActorDownEvent(
            execution_id=execution_id,
            actor_id=actor_id,
            reason_kind="child_exit_error",
            reason_detail="stream_closed_without_result",
            final_state="failed",
            dispatch_mode=dispatch_mode,
            child_session_id=child_session_id,
            target_node=target_node,
            worker_execution_id=worker_execution_id,
        )

    stop_reason = result.stop_reason or ("end" if result.final_text.strip() else "missing_result")
    reason_detail = f"stop_reason={stop_reason}"
    if stop_reason == "interrupted":
        return ActorDownEvent(
            execution_id=execution_id,
            actor_id=actor_id,
            reason_kind="aborted",
            reason_detail=reason_detail,
            final_state="aborted",
            dispatch_mode=dispatch_mode,
            child_session_id=child_session_id,
            target_node=target_node,
            worker_execution_id=worker_execution_id,
        )
    if stop_reason != "end" or not result.final_text.strip():
        return ActorDownEvent(
            execution_id=execution_id,
            actor_id=actor_id,
            reason_kind="child_exit_error",
            reason_detail=reason_detail,
            final_state="failed",
            dispatch_mode=dispatch_mode,
            child_session_id=child_session_id,
            target_node=target_node,
            worker_execution_id=worker_execution_id,
        )
    return ActorDownEvent(
        execution_id=execution_id,
        actor_id=actor_id,
        reason_kind="normal",
        reason_detail=reason_detail,
        final_state="exited",
        dispatch_mode=dispatch_mode,
        child_session_id=child_session_id,
        target_node=target_node,
        worker_execution_id=worker_execution_id,
    )


def aborted_down(
    *,
    execution_id: str,
    actor_id: str,
    dispatch_mode: str,
    child_session_id: str | None = None,
    target_node: str | None = None,
    worker_execution_id: str | None = None,
    reason_detail: str = "host_abort",
) -> ActorDownEvent:
    return ActorDownEvent(
        execution_id=execution_id,
        actor_id=actor_id,
        reason_kind="aborted",
        reason_detail=reason_detail,
        final_state="aborted",
        dispatch_mode=dispatch_mode,
        child_session_id=child_session_id,
        target_node=target_node,
        worker_execution_id=worker_execution_id,
    )


def exception_down(
    *,
    execution_id: str,
    actor_id: str,
    dispatch_mode: str,
    reason_kind: ActorDownReasonKind,
    exc: BaseException,
    child_session_id: str | None = None,
    target_node: str | None = None,
    worker_execution_id: str | None = None,
) -> ActorDownEvent:
    final_state: ActorDownFinalState = "aborted" if reason_kind == "aborted" else "failed"
    return ActorDownEvent(
        execution_id=execution_id,
        actor_id=actor_id,
        reason_kind=reason_kind,
        reason_detail=f"{type(exc).__name__}: {exc}",
        final_state=final_state,
        dispatch_mode=dispatch_mode,
        child_session_id=child_session_id,
        target_node=target_node,
        worker_execution_id=worker_execution_id,
    )


def classify_remote_exception_down(
    *,
    execution_id: str,
    actor_id: str,
    dispatch_mode: str,
    exc: BaseException,
    child_session_id: str | None = None,
    target_node: str | None = None,
    worker_execution_id: str | None = None,
) -> ActorDownEvent:
    if isinstance(exc, RemoteWorkerStreamError):
        reason_kind: ActorDownReasonKind = "remote_worker_error"
    elif isinstance(exc, (ConnectionError, OSError, TimeoutError)):
        reason_kind = "transport_lost"
    else:
        reason_kind = "remote_worker_error"
    return exception_down(
        execution_id=execution_id,
        actor_id=actor_id,
        dispatch_mode=dispatch_mode,
        reason_kind=reason_kind,
        exc=exc,
        child_session_id=child_session_id,
        target_node=target_node,
        worker_execution_id=worker_execution_id,
    )
