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

class SlashCommandMixin:
    def _expand_command_args(self, template: str, args: str) -> str:
        import re

        raw_args = args or ""

        # OpenCode tokenization: [Image N] is one token, quoted strings are one
        # token, otherwise split by whitespace.
        args_regex = re.compile(r'(?:\[Image\s+\d+\]|"[^"]*"|\'[^\']*\'|[^\s"\']+)', re.IGNORECASE)
        quote_trim = re.compile(r"^['\"]|['\"]$")

        raw = args_regex.findall(raw_args)
        parts = [quote_trim.sub("", x) for x in raw]

        placeholder_regex = re.compile(r"\$(\d+)")
        placeholders = placeholder_regex.findall(template)
        last = 0
        for s in placeholders:
            try:
                n = int(s)
            except Exception:  # noqa: BLE001
                continue
            if n > last:
                last = n

        def repl(m: re.Match[str]) -> str:
            try:
                position = int(m.group(1))
            except Exception:  # noqa: BLE001
                return ""
            arg_index = position - 1
            if arg_index >= len(parts) or arg_index < 0:
                return ""
            if position == last:
                return " ".join(parts[arg_index:])
            return parts[arg_index]

        with_args = placeholder_regex.sub(repl, template)
        uses_arguments_placeholder = "$ARGUMENTS" in template
        out = with_args.replace("$ARGUMENTS", raw_args)

        if not placeholders and not uses_arguments_placeholder and raw_args.strip():
            out = out + "\n\n" + raw_args

        return out


    async def _render_slash_command(
        self,
        *,
        session_id: str,
        tool_use_id: str,
        name: str,
        args: str,
    ) -> tuple[str, list[str], list[dict[str, Any]]]:
        """Render a slash command template with file/shell expansions.

        Returns (rendered_text, sources, parts).
        """

        options = self._options
        project_dir = options.project_dir or options.cwd
        tmpl = load_command_template(name=name, project_dir=str(project_dir))
        if tmpl is None:
            raise FileNotFoundError(f"SlashCommand: not found: {name}")

        is_subtask = bool(getattr(tmpl, "subtask", None) is True)

        text = self._expand_command_args(tmpl.content, args)

        sources = [tmpl.source]

        # Expand inline shell snippets: !`cmd`.
        import re as _re

        bash_regex = _re.compile(r"!`([^`]+)`")
        shell_matches = list(bash_regex.finditer(text))
        if shell_matches:
            if options.allowed_tools is not None and "Bash" not in set(options.allowed_tools):
                raise RuntimeError("SlashCommand: Bash tool is not allowed")

            approvals: list[tuple[str, dict[str, Any]]] = []
            for i, m in enumerate(shell_matches):
                cmd = (m.group(1) or "").strip()
                approval = await options.permission_gate.approve(
                    "Bash",
                    {"command": cmd, "workdir": options.cwd, "description": "SlashCommand shell"},
                    context={
                        "session_id": session_id,
                        "tool_use_id": f"{tool_use_id}:bash:{i}",
                        "agent_name": self._agent_name,
                    },
                )
                if not approval.allowed:
                    raise RuntimeError("SlashCommand: Bash not approved")
                approvals.append((cmd, dict(approval.updated_input or {"command": cmd, "workdir": options.cwd})))

            async def _run_bash(inp: dict[str, Any]) -> str:
                tool = options.tools.get("Bash")
                try:
                    out_obj = await tool.run(inp, ToolContext(cwd=options.cwd, project_dir=options.project_dir))
                except Exception as e:  # noqa: BLE001
                    return f"Error executing command: {e}"
                if isinstance(out_obj, dict):
                    s = out_obj.get("stdout")
                    if isinstance(s, str):
                        return s
                return ""

            results = await asyncio.gather(*[_run_bash(inp) for _, inp in approvals])
            idx = 0

            def _sub(_: _re.Match[str]) -> str:
                nonlocal idx
                out = results[idx] if idx < len(results) else ""
                idx += 1
                return out

            text = bash_regex.sub(_sub, text)

        text = text.strip()

        # OpenCode resolvePromptParts(): keep structured parts (text + file:// + agent).
        parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
        if is_subtask:
            # Subtask commands only forward the prompt text (no file parts).
            agent_name = getattr(tmpl, "agent", None)
            if not isinstance(agent_name, str) or not agent_name:
                agent_name = name
            parts = [
                {
                    "type": "subtask",
                    "agent": agent_name,
                    "description": getattr(tmpl, "description", None) if isinstance(getattr(tmpl, "description", None), str) else "",
                    "command": name,
                    "prompt": text,
                    "model": getattr(tmpl, "model", None) if isinstance(getattr(tmpl, "model", None), str) else None,
                }
            ]

        refs = [m.group(1) for m in FILE_REGEX.finditer(text) if m.group(1)]
        refs = list(dict.fromkeys(refs))

        injections: list[str] = []

        def _find_worktree_root(start: Path) -> Path:
            cur = start.resolve()
            for p in [cur, *cur.parents]:
                if (p / ".git").exists():
                    return p
            return Path(cur.anchor or "/").resolve()

        worktree = _find_worktree_root(Path(options.project_dir or options.cwd).expanduser().resolve())
        for i, ref in enumerate(refs):
            if not isinstance(ref, str) or not ref:
                continue

            # @agent / @file (OpenCode resolves relative to worktree).
            ref_path = ref
            if ref_path.startswith("~/"):
                home = Path(os.environ.get("OPENCODE_TEST_HOME") or Path.home()).expanduser().resolve()
                ref_path = str(home / ref_path[2:])
            p = Path(ref_path)
            if not p.is_absolute():
                p = worktree / p
            p = p.expanduser().resolve()

            if not p.exists():
                if ref in (options.agents or {}):
                    if not is_subtask:
                        parts.append({"type": "agent", "name": ref})
                continue

            if not is_subtask:
                parts.append(
                    {
                        "type": "file",
                        "url": p.as_uri(),
                        "filename": ref,
                        "mime": "application/x-directory" if p.is_dir() else "text/plain",
                    }
                )

            if is_subtask:
                continue

            if p.is_dir():
                if options.allowed_tools is not None and "List" not in set(options.allowed_tools):
                    raise RuntimeError("SlashCommand: List tool is not allowed")
                approval = await options.permission_gate.approve(
                    "List",
                    {"path": str(p)},
                    context={"session_id": session_id, "tool_use_id": f"{tool_use_id}:list:{i}", "agent_name": self._agent_name},
                )
                if not approval.allowed:
                    raise RuntimeError("SlashCommand: List not approved")
                tool = options.tools.get("List")
                out_obj = await tool.run(approval.updated_input or {"path": str(p)}, ToolContext(cwd=options.cwd, project_dir=options.project_dir))
                out = out_obj.get("output") if isinstance(out_obj, dict) else None
                if isinstance(out, str) and out:
                    injections.append(out)
                continue

            # Default: treat as text/plain and inline via Read tool.
            if options.allowed_tools is not None and "Read" not in set(options.allowed_tools):
                raise RuntimeError("SlashCommand: Read tool is not allowed")
            approval = await options.permission_gate.approve(
                "Read",
                {"file_path": str(p)},
                context={"session_id": session_id, "tool_use_id": f"{tool_use_id}:read:{i}", "agent_name": self._agent_name},
            )
            if not approval.allowed:
                raise RuntimeError("SlashCommand: Read not approved")
            tool = options.tools.get("Read")
            out_obj = await tool.run(approval.updated_input or {"file_path": str(p)}, ToolContext(cwd=options.cwd, project_dir=options.project_dir))
            content = out_obj.get("content") if isinstance(out_obj, dict) else None
            if isinstance(content, str) and content:
                injections.append(content)

        rendered = text
        if injections and not is_subtask:
            rendered = (rendered + "\n\n" + "\n\n".join([b for b in injections if b.strip()])).strip()
        return rendered, sources, parts


