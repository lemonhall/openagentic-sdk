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

class AskUserQuestionMixin:
    async def _handle_ask_user_question(
        self,
        *,
        session_id: str,
        tool_call: ToolCall,
        tool_input: Mapping[str, Any],
        store: FileSessionStore,
    ) -> AsyncIterator[Any]:
        options = self._options

        questions = tool_input.get("questions")
        if isinstance(questions, dict):
            questions = [questions]

        if not isinstance(questions, list) or not questions:
            q_text0 = tool_input.get("question", tool_input.get("prompt"))
            if isinstance(q_text0, str) and q_text0.strip():
                opts0 = tool_input.get("options", tool_input.get("choices")) or []
                options0: list[dict[str, str]] = []
                if isinstance(opts0, list):
                    for opt in opts0:
                        if isinstance(opt, str) and opt.strip():
                            options0.append({"label": opt.strip()})
                            continue
                        if isinstance(opt, dict):
                            lab = opt.get("label", opt.get("name", opt.get("value")))
                            if isinstance(lab, str) and lab.strip():
                                options0.append({"label": lab.strip()})
                questions = [{"question": q_text0.strip(), "options": options0}]

        if not isinstance(questions, list) or not questions:
            result = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="InvalidAskUserQuestionInput",
                error_message="AskUserQuestion: 'questions' must be a non-empty list",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, result)
            yield result
            return

        user_answerer = options.permission_gate.user_answerer
        if user_answerer is None:
            result = ToolResult(
                tool_use_id=tool_call.tool_use_id,
                output=None,
                is_error=True,
                error_type="NoUserAnswerer",
                error_message="AskUserQuestion: no user_answerer is configured",
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, result)
            yield result
            return

        answers: dict[str, str] = {}
        for i, q in enumerate(questions):
            if not isinstance(q, dict):
                continue
            q_text = q.get("question")
            if not isinstance(q_text, str) or not q_text:
                continue
            opts = q.get("options") or []
            labels: list[str] = []
            if isinstance(opts, list):
                for opt in opts:
                    if isinstance(opt, dict):
                        lab = opt.get("label")
                        if isinstance(lab, str) and lab:
                            labels.append(lab)
            if not labels:
                labels = ["ok"]

            uq = UserQuestion(
                question_id=f"{tool_call.tool_use_id}:{i}",
                prompt=q_text,
                choices=labels,
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, uq)
            yield uq
            ans = await user_answerer(uq)
            answers[q_text] = str(ans)

        result = ToolResult(
            tool_use_id=tool_call.tool_use_id,
            output={"questions": questions, "answers": answers},
            is_error=False,
            parent_tool_use_id=self._parent_tool_use_id,
            agent_name=self._agent_name,
        )
        store.append_event(session_id, result)
        yield result


