from __future__ import annotations

import inspect
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Mapping, Sequence

from .._version import __version__ as _SDK_VERSION
from ..events import (
    AssistantDelta,
    AssistantMessage,
    Result,
    SystemInit,
    ToolOutputCompacted,
    ToolResult,
    ToolUse,
    UserMessage,
    UserCompaction,
    UserQuestion,
)
from ..hooks.engine import HookEngine
from ..mcp.sdk import McpSdkServerConfig, wrap_sdk_server_tools
from ..mcp.client import StdioMcpClient
from ..mcp.remote_client import RemoteMcpClient
from ..mcp.wrappers import (
    wrap_http_mcp_prompts,
    wrap_http_mcp_resources,
    wrap_http_mcp_tools,
    wrap_stdio_mcp_prompts,
    wrap_stdio_mcp_resources,
    wrap_stdio_mcp_tools,
)
from ..options import OpenAgenticOptions
from ..paths import default_session_root
from ..prompt_system import BuiltSystemPrompt, build_system_prompt
from ..compaction import (
    COMPACTION_MARKER_QUESTION,
    COMPACTION_SYSTEM_PROMPT,
    COMPACTION_USER_INSTRUCTION,
    TOOL_OUTPUT_PLACEHOLDER,
    select_tool_outputs_to_prune,
    would_overflow,
)
from ..providers.base import ModelOutput, ToolCall
from ..sessions.rebuild import rebuild_messages, rebuild_responses_input
from ..sessions.store import FileSessionStore
from ..skills.index import index_skills
from ..tools.base import ToolContext
from ..tools.openai import tool_schemas_for_openai
from ..tools.openai_responses import tool_schemas_for_responses
from ..tools.task import TaskTool
from ..commands import load_command_template
from ..opencode_markdown import FILE_REGEX

import shlex
import asyncio
import uuid


def _callable_accepts_kw(fn: Any, name: str) -> bool:
    try:
        sig = inspect.signature(fn)
    except Exception:  # noqa: BLE001
        return False
    if name in sig.parameters:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


def _tool_result_payload(ev: "ToolResult") -> Any:
    # Provider protocols only get `output`, so on errors we must serialize the
    # error fields too (otherwise the model sees `null`).
    if not getattr(ev, "is_error", False):
        return getattr(ev, "output", None)
    return {
        "is_error": True,
        "error_type": getattr(ev, "error_type", None),
        "error_message": getattr(ev, "error_message", None),
        "output": getattr(ev, "output", None),
    }


def _filter_supported_kwargs(fn: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Drop kwargs a callable doesn't accept.

    This avoids runtime TypeErrors and lets custom providers implement only a
    subset of the Responses API keyword surface.
    """

    try:
        sig = inspect.signature(fn)
    except Exception:  # noqa: BLE001
        return kwargs
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return kwargs
    allowed = set(sig.parameters.keys())
    return {k: v for k, v in kwargs.items() if k in allowed}


def _detect_provider_protocol(provider: Any) -> str:
    """Best-effort protocol detection based on provider call signatures.

    We prefer to detect via `complete()` (used for non-streaming providers), but
    fall back to `stream()` when a provider only supports streaming.
    """

    for attr in ("complete", "stream"):
        fn = getattr(provider, attr, None)
        if fn is None:
            continue
        try:
            sig = inspect.signature(fn)
        except Exception:  # noqa: BLE001
            continue
        params = sig.parameters
        if "input" in params:
            return "responses"
        if "messages" in params:
            return "legacy"
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            # Prefer modern protocol when the provider is flexible.
            return "responses"

    return "responses"


def _default_session_root() -> Path:
    return default_session_root()


def _build_project_system_prompt(options: OpenAgenticOptions) -> BuiltSystemPrompt:
    """Backwards-compatible wrapper.

    The system prompt builder now returns both the system text and any
    Responses-level `instructions` (used for Codex OAuth sessions).
    """

    return build_system_prompt(options)


def _base_system_role_for_model(*, model_id: str, provider_protocol: str) -> str:
    if provider_protocol != "responses":
        return "system"
    mid = (model_id or "").lower()
    # Match OpenCode's openai-compatible Responses adapter defaults:
    # reasoning families prefer developer role.
    if mid.startswith("o") or "gpt-5" in mid or mid.startswith("codex-") or mid.startswith("computer-use"):
        return "developer"
    return "system"


_EXEC_SKILL_RE = re.compile(
    r"^\s*(?:执行技能|运行技能|run skill|execute skill)\s*[:：]?\s*([A-Za-z0-9_.-]+)\s*$",
    re.IGNORECASE,
)

_LIST_SKILLS_RE = re.compile(
    r"^\s*(?:what\s+skills\s+are\s+available\??|list\s+skills|有哪些技能\??|有什么技能\??|技能有哪些\??)\s*$",
    re.IGNORECASE,
)


def _maybe_expand_execute_skill_prompt(prompt: str, options: OpenAgenticOptions) -> str:
    """
    Best-effort helper for users who type "执行技能<name>" expecting an automatic skill run.

    If the prompt matches and the skill exists on disk, instruct the model to load it via the
    `Skill` tool and follow the Workflow/Checklist without asking for extra input.
    """
    m = _EXEC_SKILL_RE.match(prompt or "")
    if not m:
        return prompt

    skill_name = m.group(1)
    project_dir = options.project_dir or options.cwd
    skills = index_skills(project_dir=project_dir)
    match = next((s for s in skills if s.name == skill_name), None)
    if match is None:
        return prompt

    return (
        f"你正在执行技能 `{skill_name}`。\n"
        "除非技能文档明确要求，否则不要向用户询问额外的目标/输入。\n"
        "请严格按技能的 Workflow/Checklist 执行。\n\n"
        f'你 MUST 调用 `Skill` 工具加载该技能：`Skill({{"name": "{skill_name}"}})`。\n'
    )


def _maybe_expand_list_skills_prompt(prompt: str, options: OpenAgenticOptions) -> str:
    """
    Best-effort helper for users who ask to list available skills without explicitly naming the tool.
    """
    if not _LIST_SKILLS_RE.match(prompt or ""):
        return prompt

    # If there are no skills, keep the prompt as-is.
    project_dir = options.project_dir or options.cwd
    skills = index_skills(project_dir=project_dir)
    if not skills:
        return prompt

    return (
        "List the available Skills for this project.\n"
        "The available skills are listed in the `Skill` tool description under <available_skills>.\n"
        "Present them as a short bullet list: `name` — description (or summary).\n"
    )


def _unsupported_previous_response_id_error(e: BaseException) -> bool:
    msg = str(e)
    if not msg:
        return False
    msg_l = msg.lower()
    return "previous_response_id" in msg_l and ("unsupported parameter" in msg_l or "unsupported" in msg_l)


def _no_tool_call_found_for_call_output_error(e: BaseException) -> bool:
    msg = str(e)
    if not msg:
        return False
    msg_l = msg.lower()
    return "no tool call found for function call output" in msg_l and "call_id" in msg_l


def _extract_function_call_outputs(items: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Extract Responses tool outputs from an input list.

    Some hook pipelines may prepend role-based messages (system/developer) even
    when the runtime is in Responses incremental mode and is trying to send only
    `function_call_output` items.

    For retry/fallback logic we want to:
    - detect when the input effectively contains only tool outputs (plus optional
      system/developer role messages)
    - re-send a combined `function_call` + `function_call_output` input without
      accidentally placing role-based items in the middle of Responses items.
    """

    outs: list[Mapping[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("type") == "function_call_output":
            outs.append(it)
    return outs


def _looks_like_outputs_without_calls(items: Sequence[Mapping[str, Any]]) -> bool:
    """True when `items` contains tool outputs but no matching tool calls.

    We allow role-based system/developer messages to be present (some hooks
    prepend them), but we consider any other non-output item a mismatch.
    """

    outs = 0
    for it in items:
        if not isinstance(it, dict):
            return False
        if it.get("type") == "function_call_output":
            outs += 1
            continue
        if it.get("type") == "function_call":
            return False
        role = it.get("role")
        if role in {"system", "developer"}:
            continue
        # Unknown item (could be user/assistant/other Responses item) - don't
        # treat this as an output-only continuation.
        return False
    return outs > 0


def _prepend_function_calls_for_responses(tool_calls: Sequence[ToolCall], outputs: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    calls: list[Mapping[str, Any]] = []
    for tc in tool_calls:
        calls.append(
            {
                "type": "function_call",
                "call_id": tc.tool_use_id,
                "name": tc.name,
                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
            }
        )
    return calls + list(outputs)


@dataclass(frozen=True, slots=True)
class RunResult:
    final_text: str
    session_id: str
    events: Sequence[Any]


