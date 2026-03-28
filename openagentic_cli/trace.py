from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, TextIO


def _tool_group(name: str) -> str:
    if name == "Task":
        return "Subagents"
    if name in ("Read", "Glob", "Grep", "WebFetch", "WebSearch", "SlashCommand", "Skill"):
        return "Explored"
    if name in ("Write", "Edit", "NotebookEdit", "TodoWrite"):
        return "Edited"
    if name == "Bash":
        return "Ran"
    return "Tools"


def _summarize_tool_use(name: str, tool_input: Mapping[str, Any] | None) -> str:
    inp = tool_input or {}
    if name == "Bash":
        cmd = inp.get("command")
        return f"`{cmd}`" if isinstance(cmd, str) and cmd else "Bash"
    if name == "Read":
        p = inp.get("file_path", inp.get("filePath"))
        return f"Read `{p}`" if isinstance(p, str) and p else "Read"
    if name == "Write":
        p = inp.get("file_path", inp.get("filePath"))
        return f"Write `{p}`" if isinstance(p, str) and p else "Write"
    if name == "Edit":
        p = inp.get("file_path", inp.get("filePath"))
        return f"Edit `{p}`" if isinstance(p, str) and p else "Edit"
    if name == "NotebookEdit":
        p = inp.get("notebook_path")
        return f"NotebookEdit `{p}`" if isinstance(p, str) and p else "NotebookEdit"
    if name == "Grep":
        q = inp.get("query")
        glob = inp.get("file_glob", "**/*")
        if isinstance(q, str) and q:
            return f"Search `{q}` in `{glob}`"
        return "Search"
    if name == "Glob":
        pat = inp.get("pattern")
        return f"List `{pat}`" if isinstance(pat, str) and pat else "List files"
    if name == "WebSearch":
        q = inp.get("query")
        return f"WebSearch `{q}`" if isinstance(q, str) and q else "WebSearch"
    if name == "WebFetch":
        url = inp.get("url")
        return f"WebFetch `{url}`" if isinstance(url, str) and url else "WebFetch"
    if name == "SlashCommand":
        n = inp.get("name")
        return f"/{n}" if isinstance(n, str) and n else "SlashCommand"
    if name == "Skill":
        n = inp.get("name")
        if isinstance(n, str) and n:
            return f"Skill `{n}`"
        return "Skill"
    if name == "Task":
        agent = inp.get("agent")
        if isinstance(agent, str) and agent:
            return f"Delegate to `{agent}`"
        return "Task"
    return name


def _summarize_tool_result(
    name: str | None,
    output: Any,
    *,
    is_error: bool,
    error_message: str | None,
    error_type: str | None,
    max_lines: int,
) -> list[str]:
    if is_error:
        msg = error_message
        if not isinstance(msg, str) or not msg:
            msg = output.get("error_message") if isinstance(output, dict) else None
        if not isinstance(msg, str) or not msg:
            msg = output.get("message") if isinstance(output, dict) else None
        if not isinstance(msg, str) or not msg:
            msg = "unknown error"
        et = error_type if isinstance(error_type, str) and error_type else None
        return [f"ERROR: {msg}" + (f" ({et})" if et else "")]

    if name == "Bash" and isinstance(output, dict):
        exit_code = output.get("exit_code", output.get("exitCode"))
        lines: list[str] = []
        if isinstance(exit_code, int):
            lines.append(f"exit_code={exit_code}")
        out = output.get("output")
        out_text = out if isinstance(out, str) else ""
        if out_text.strip():
            chunk = out_text.strip("\n").splitlines()
            for ln in chunk[: max(0, max_lines)]:
                lines.append(ln)

        # Friendly hints for common rg failures.
        lower = out_text.lower()
        if "ripgrep requires at least one pattern" in lower:
            lines.append("hint: run `rg <pattern> [path]` (e.g. `rg \"TODO\" .`)")
        if ("rg: command not found" in lower or "bash: rg: command not found" in lower) and isinstance(exit_code, int):
            lines.append("hint: install ripgrep (rg) then retry")
            lines.append("  - Windows: `winget install BurntSushi.ripgrep.MSVC`")
            lines.append("  - WSL/Ubuntu: `sudo apt-get update && sudo apt-get install -y ripgrep`")
        return lines or ["ok"]

    if name == "Grep" and isinstance(output, dict):
        tm = output.get("total_matches")
        if isinstance(tm, int):
            return [f"total_matches={tm}"]
        cnt = output.get("count")
        if isinstance(cnt, int):
            return [f"count={cnt}"]
        return ["ok"]

    if name == "Read" and isinstance(output, dict):
        fp = output.get("file_path")
        lr = output.get("lines_returned")
        tl = output.get("total_lines")
        if isinstance(lr, int) and isinstance(tl, int):
            return [f"lines={lr}/{tl}", f"file={fp}"] if isinstance(fp, str) and fp else [f"lines={lr}/{tl}"]
        return ["ok"]

    if name == "Task" and isinstance(output, dict):
        dispatch_mode = output.get("dispatch_mode")
        target_node = output.get("target_node")
        worker_execution_id = output.get("worker_execution_id")
        child_session_id = output.get("child_session_id")

        lines: list[str] = []
        if isinstance(dispatch_mode, str) and dispatch_mode:
            lines.append(f"dispatch_mode={dispatch_mode}")
        elif isinstance(child_session_id, str) and child_session_id:
            lines.append("dispatch_mode=local")

        if isinstance(target_node, str) and target_node:
            lines.append(f"target_node={target_node}")
        if isinstance(worker_execution_id, str) and worker_execution_id:
            lines.append(f"worker_execution_id={worker_execution_id}")
        if isinstance(child_session_id, str) and child_session_id:
            lines.append(f"child_session_id={child_session_id}")

        return lines or ["ok"]

    return ["ok"]


@dataclass
class TraceRenderer:
    stream: TextIO
    color: bool = False
    max_bash_output_lines: int = 20
    show_hooks: bool = False

    _saw_delta: bool = False
    _current_group: str | None = None
    _group_count: int = 0
    _tool_use_names: dict[str, str] = field(default_factory=dict)

    def on_event(self, ev: Any) -> None:
        t = getattr(ev, "type", None)

        if t == "assistant.delta":
            delta = getattr(ev, "text_delta", "")
            if isinstance(delta, str) and delta:
                self.stream.write(delta)
                self.stream.flush()
                self._saw_delta = True
            return

        if t == "assistant.message":
            if self._saw_delta:
                self.stream.write("\n")
                self.stream.flush()
                self._saw_delta = False
                return
            text = getattr(ev, "text", "")
            if isinstance(text, str) and text:
                self.stream.write(text + "\n")
                self.stream.flush()
            return

        if t == "hook.event":
            if not self.show_hooks:
                return
            group = "Hooks"
            if group != self._current_group:
                self._current_group = group
                self._group_count = 0
                self.stream.write("\n• Hooks\n")
            prefix = "  └ " if self._group_count == 0 else "    "
            self._group_count += 1
            hook_point = getattr(ev, "hook_point", "")
            name = getattr(ev, "name", "")
            action = getattr(ev, "action", None)
            line = f"{hook_point}:{name}"
            if isinstance(action, str) and action:
                line += f" action={action}"
            self.stream.write(prefix + line + "\n")
            self.stream.flush()
            return

        if t == "tool.use":
            tool_use_id = getattr(ev, "tool_use_id", "")
            name = getattr(ev, "name", "")
            tool_input = getattr(ev, "input", None)
            if not isinstance(name, str) or not name:
                return
            if isinstance(tool_use_id, str) and tool_use_id:
                self._tool_use_names[tool_use_id] = name

            group = _tool_group(name)
            if group != self._current_group:
                self._current_group = group
                self._group_count = 0
                self.stream.write("\n" + f"• {group}\n")

            prefix = "  └ " if self._group_count == 0 else "    "
            self._group_count += 1
            summary = _summarize_tool_use(name, tool_input if isinstance(tool_input, dict) else None)
            self.stream.write(prefix + summary + "\n")
            self.stream.flush()
            return

        if t == "tool.result":
            tool_use_id = getattr(ev, "tool_use_id", "")
            output = getattr(ev, "output", None)
            is_error = bool(getattr(ev, "is_error", False))
            error_message = getattr(ev, "error_message", None)
            error_type = getattr(ev, "error_type", None)
            name = self._tool_use_names.get(tool_use_id) if isinstance(tool_use_id, str) else None
            max_lines = int(os.getenv("OA_TRACE_BASH_OUTPUT_LINES", str(self.max_bash_output_lines)) or self.max_bash_output_lines)
            lines = _summarize_tool_result(
                name,
                output,
                is_error=is_error,
                error_message=error_message if isinstance(error_message, str) else None,
                error_type=error_type if isinstance(error_type, str) else None,
                max_lines=max_lines,
            )
            for i, ln in enumerate(lines):
                prefix = "    └ " if i == 0 else "      "
                self.stream.write(prefix + ln + "\n")
            self.stream.flush()
            return

        if t == "result":
            stop_reason = getattr(ev, "stop_reason", None)
            session_id = getattr(ev, "session_id", None)
            line = "• Done"
            if isinstance(stop_reason, str) and stop_reason:
                line += f" stop_reason={stop_reason}"
            if isinstance(session_id, str) and session_id:
                line += f" session_id={session_id}"
            self.stream.write("\n" + line + "\n")
            self.stream.flush()
            return
