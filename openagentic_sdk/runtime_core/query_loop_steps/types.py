from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ...providers.base import ModelOutput, ToolCall
from ...sessions.store import FileSessionStore


@dataclass(frozen=True, slots=True)
class SessionBootstrap:
    store: FileSessionStore
    session_id: str
    messages: list[Mapping[str, Any]]
    resume_protocol: str | None
    previous_response_id: str | None
    supports_previous_response_id: bool
    pending_responses_tool_calls: list[ToolCall]
    pending_responses_history: list[Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class ModelCallDone:
    model_out: ModelOutput
    messages: list[Mapping[str, Any]]
    supports_previous_response_id: bool


@dataclass(frozen=True, slots=True)
class ModelCallInterrupted:
    pass


@dataclass(frozen=True, slots=True)
class ToolPlumbingDone:
    messages: list[Mapping[str, Any]]
    should_continue: bool
    previous_response_id: str | None
    supports_previous_response_id: bool
    pending_responses_tool_calls: list[ToolCall]
    pending_responses_history: list[Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class CompactionDone:
    messages: list[Mapping[str, Any]]
    previous_response_id: str | None
    should_continue: bool


@dataclass(frozen=True, slots=True)
class StepState:
    messages: list[Mapping[str, Any]]
    supports_previous_response_id: bool
    previous_response_id: str | None
    pending_responses_tool_calls: list[ToolCall]
    pending_responses_history: list[Mapping[str, Any]]
