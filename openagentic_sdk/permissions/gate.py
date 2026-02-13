from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Optional

from ..events import UserQuestion
from .cas import CanUseTool, PermissionResultAllow, PermissionResultDeny, ToolPermissionContext
from .interactive import InteractiveApprover

Approver = Callable[[str, Mapping[str, Any], Mapping[str, Any]], Awaitable[bool]]
UserAnswerer = Callable[[UserQuestion], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    allowed: bool
    question: UserQuestion | None = None
    updated_input: Mapping[str, Any] | None = None
    deny_message: str | None = None
    interrupt: bool = False


@dataclass(frozen=True, slots=True)
class PermissionGate:
    permission_mode: str
    approver: Optional[Approver] = None
    can_use_tool: CanUseTool | None = None
    interactive: bool = False
    interactive_approver: InteractiveApprover | None = None
    user_answerer: UserAnswerer | None = None

    async def approve(
        self, tool_name: str, tool_input: Mapping[str, Any], *, context: Mapping[str, Any]
    ) -> ApprovalResult:
        mode = self.permission_mode
        if mode == "bypassPermissions":
            mode = "bypass"
        if mode == "plan":
            mode = "deny"

        if self.can_use_tool is not None:
            res = await self.can_use_tool(tool_name, dict(tool_input), ToolPermissionContext())
            if isinstance(res, PermissionResultAllow):
                if res.updated_input is not None:
                    return ApprovalResult(True, updated_input=res.updated_input)
                return ApprovalResult(True)
            if isinstance(res, PermissionResultDeny):
                return ApprovalResult(False, deny_message=res.message or "denied", interrupt=bool(res.interrupt))

        if mode == "acceptEdits":
            if tool_name in ("Edit", "Write", "NotebookEdit"):
                return ApprovalResult(True)
            mode = "prompt"

        if mode == "default":
            safe = {"Read", "Glob", "Grep", "Skill", "SlashCommand", "AskUserQuestion"}
            if tool_name in safe:
                return ApprovalResult(True)
            mode = "prompt"

        if mode == "bypass":
            return ApprovalResult(True)
        if mode == "deny":
            return ApprovalResult(False)

        if mode == "callback":
            if self.approver is None:
                return ApprovalResult(False)
            try:
                allowed = await self.approver(tool_name, tool_input, context)
            except Exception as e:  # noqa: BLE001
                return ApprovalResult(False, deny_message=f"permission callback error: {e}")
            return ApprovalResult(bool(allowed))

        if mode == "prompt":
            if not self.interactive:
                tool_use_id = context.get("tool_use_id")
                question_id = tool_use_id if isinstance(tool_use_id, str) and tool_use_id else uuid.uuid4().hex
                question = UserQuestion(
                    question_id=question_id,
                    prompt=f"Allow tool {tool_name}?",
                    choices=["yes", "no"],
                    parent_tool_use_id=tool_use_id if isinstance(tool_use_id, str) else None,
                    agent_name=context.get("agent_name") if isinstance(context.get("agent_name"), str) else None,
                )
                if self.user_answerer is None:
                    return ApprovalResult(False, question=question)
                answer = await self.user_answerer(question)
                allowed = str(answer).strip().lower() in ("y", "yes")
                return ApprovalResult(allowed, question=question)
            if self.interactive_approver is None:
                raise ValueError("interactive_approver is required when interactive=True")
            allowed = self.interactive_approver.ask_yes_no(f"Allow tool {tool_name}? [y/N] ")
            return ApprovalResult(allowed)

        raise ValueError(f"unknown permission_mode: {mode}")
