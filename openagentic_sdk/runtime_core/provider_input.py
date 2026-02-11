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


from .common import (
    _base_system_role_for_model,
    _build_project_system_prompt,
    _callable_accepts_kw,
    _default_session_root,
    _detect_provider_protocol,
    _extract_function_call_outputs,
    _filter_supported_kwargs,
    _looks_like_outputs_without_calls,
    _maybe_expand_execute_skill_prompt,
    _maybe_expand_list_skills_prompt,
    _no_tool_call_found_for_call_output_error,
    _prepend_function_calls_for_responses,
    _tool_result_payload,
    _unsupported_previous_response_id_error,
)

class ProviderInputMixin:
    def _with_base_system(self, items: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        sys_prompt = getattr(self, "_base_system_prompt", None)
        sys_role = getattr(self, "_base_system_role", None) or "system"
        if not isinstance(sys_prompt, str) or not sys_prompt.strip():
            return items
        if items and isinstance(items[0], dict) and items[0].get("role") == sys_role:
            # The runtime keeps the base system prompt stable by rewriting index 0.
            return [{"role": sys_role, "content": sys_prompt}, *items[1:]]
        return [{"role": sys_role, "content": sys_prompt}, *items]


    def _rebuild_provider_input(
        self,
        *,
        store: FileSessionStore,
        session_id: str,
        provider_protocol: str,
        options: OpenAgenticOptions,
    ) -> list[Mapping[str, Any]]:
        events = store.read_events(session_id)
        if provider_protocol == "legacy":
            items = list(
                rebuild_messages(
                    events,
                    max_events=options.resume_max_events,
                    max_bytes=options.resume_max_bytes,
                )
            )
        else:
            items = list(
                rebuild_responses_input(
                    events,
                    max_events=options.resume_max_events,
                    max_bytes=options.resume_max_bytes,
                )
            )
        return self._with_base_system(items)


    async def _maybe_prune_tool_outputs(
        self,
        *,
        store: FileSessionStore,
        session_id: str,
    ) -> AsyncIterator[Any]:
        options = self._options
        if not getattr(options, "compaction", None) or not options.compaction.prune:
            return

        # Append-only marking of old tool results.
        events = store.read_events(session_id)
        to_prune = select_tool_outputs_to_prune(events=events, compaction=options.compaction)
        if not to_prune:
            return
        now = time.time()
        for tid in to_prune:
            ev = ToolOutputCompacted(
                tool_use_id=tid,
                compacted_ts=now,
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, ev)
            yield ev


    async def _run_compaction_pass(
        self,
        *,
        store: FileSessionStore,
        session_id: str,
        provider_protocol: str,
    ) -> AsyncIterator[Any]:
        """Run a dedicated, tool-less compaction call and store a summary pivot."""

        options = self._options

        complete_fn: Any = getattr(options.provider, "complete", None)
        if complete_fn is None:
            return

        # Summarize the current post-pivot window. Use rebuild_messages so the
        # compaction model sees a normal chat-style transcript.
        history = list(
            rebuild_messages(
                store.read_events(session_id),
                max_events=options.resume_max_events,
                max_bytes=options.resume_max_bytes,
            )
        )

        # OpenCode parity: allow plugins to inject compaction context/prompt.
        compacting = {"context": [], "prompt": None}
        out2, hook_events, decision = await options.hooks.run_session_compacting(
            output=compacting,
            context={"session_id": session_id, "agent_name": self._agent_name},
        )
        for he in hook_events:
            store.append_event(session_id, he)
            yield he
        if decision is not None and decision.block:
            return
        compacting2 = out2 if isinstance(out2, dict) else compacting
        ctx_items = compacting2.get("context") if isinstance(compacting2, dict) else None
        ctx_list = [str(x) for x in ctx_items] if isinstance(ctx_items, list) else []
        prompt_override = compacting2.get("prompt") if isinstance(compacting2, dict) else None
        if isinstance(prompt_override, str) and prompt_override.strip():
            prompt_text = prompt_override.strip()
        else:
            prompt_text = "\n\n".join([COMPACTION_USER_INSTRUCTION, *ctx_list]).strip()

        # The compaction marker question is already present in history (rebuild
        # renders UserCompaction as "What did we do so far?").
        compaction_input: list[Mapping[str, Any]] = [
            {"role": "system", "content": COMPACTION_SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": prompt_text},
        ]

        if provider_protocol == "legacy":
            kwargs = {
                "model": options.model,
                "messages": compaction_input,
                "tools": (),
                "api_key": options.api_key,
            }
        else:
            kwargs = {
                "model": options.model,
                "input": compaction_input,
                "tools": (),
                "api_key": options.api_key,
                # Avoid polluting provider-side stored conversations.
                "store": False,
                "previous_response_id": None,
            }

        model_out = await complete_fn(**_filter_supported_kwargs(complete_fn, kwargs))
        summary = model_out.assistant_text or ""
        if not summary.strip():
            return

        msg = AssistantMessage(
            text=summary.strip(),
            is_summary=True,
            parent_tool_use_id=self._parent_tool_use_id,
            agent_name=self._agent_name,
        )
        store.append_event(session_id, msg)
        yield msg


