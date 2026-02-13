from __future__ import annotations

import os
import shutil
import subprocess
import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

from .base import Tool, ToolContext


_WSL_MNT_RE = re.compile(r"(?P<prefix>^|[\s'\"(])(?P<path>/mnt/(?P<drive>[a-zA-Z])/(?P<rest>[^ \r\n\t'\"()]+))")
_MSYS_DRIVE_RE = re.compile(r"(?P<prefix>^|[\s'\"(])(?P<path>/(?P<drive>[a-zA-Z])/(?P<rest>[^ \r\n\t'\"()]+))")


def _normalize_posix_paths_to_windows(text: str) -> str:
    if os.name != "nt" or not text:
        return text

    def _mnt_repl(m: re.Match[str]) -> str:
        drive = m.group("drive").upper()
        rest = m.group("rest").replace("/", "\\")
        return f"{m.group('prefix')}{drive}:\\{rest}"

    def _msys_repl(m: re.Match[str]) -> str:
        drive = m.group("drive").upper()
        rest = m.group("rest").replace("/", "\\")
        return f"{m.group('prefix')}{drive}:\\{rest}"

    out = _WSL_MNT_RE.sub(_mnt_repl, text)
    out = _MSYS_DRIVE_RE.sub(_msys_repl, out)
    return out


@dataclass(frozen=True, slots=True)
class BashTool(Tool):
    name: str = "Bash"
    description: str = "Run a shell command."
    timeout_s: float = 60.0
    max_output_bytes: int = 1024 * 1024
    max_output_lines: int = 2000

    def _shell_argv(self, command: str) -> tuple[list[str], bool]:
        """
        Returns (argv, is_wsl_bash).

        On Windows, `C:\\Windows\\System32\\bash.exe` is the WSL shim. It can hold
        directory handles briefly after exit; we add a small post-run delay when
        used to avoid flaky tempdir cleanup.
        """
        # Prefer bash for consistent quoting/semantics.
        bash_path = shutil.which("bash")
        if bash_path:
            p = Path(bash_path)
            is_wsl = os.name == "nt" and p.name.lower() == "bash.exe" and ("\\system32\\" in str(p).lower() or "\\windowsapps\\" in str(p).lower())
            return ["bash", "-lc", command], is_wsl

        if os.name != "nt":
            sh_path = shutil.which("sh")
            if sh_path:
                return ["sh", "-lc", command], False

        # Keep the contract strict: this tool is "Bash", not a generic shell.
        raise RuntimeError("Bash: no compatible shell found (need bash/sh)")

    async def run(self, tool_input: Mapping[str, Any], ctx: ToolContext) -> dict[str, Any]:
        command = tool_input.get("command")
        if not isinstance(command, str) or not command:
            raise ValueError("Bash: 'command' must be a non-empty string")

        workdir = tool_input.get("workdir")
        if workdir is not None and not isinstance(workdir, str):
            raise ValueError("Bash: 'workdir' must be a string")
        run_cwd = Path(ctx.cwd) if not workdir else Path(workdir)
        if not run_cwd.is_absolute():
            run_cwd = Path(ctx.cwd) / run_cwd

        timeout_ms = tool_input.get("timeout")
        if timeout_ms is not None:
            timeout_s = float(timeout_ms) / 1000.0
        else:
            timeout_s = float(tool_input.get("timeout_s", self.timeout_s))

        argv, is_wsl_bash = self._shell_argv(command)
        # Run in a worker thread so shell calls don't block the event loop.
        proc = await asyncio.to_thread(
            subprocess.run,
            argv,
            cwd=str(run_cwd),
            capture_output=True,
            text=False,
            timeout=timeout_s,
        )
        if is_wsl_bash and os.name == "nt":
            # WSL bash.exe can keep a handle on the cwd for a short time after
            # the process exits, breaking TemporaryDirectory cleanup.
            await asyncio.sleep(0.25)
        stdout_full = proc.stdout or b""
        stderr_full = proc.stderr or b""
        stdout_truncated = len(stdout_full) > self.max_output_bytes
        stderr_truncated = len(stderr_full) > self.max_output_bytes
        stdout = stdout_full[: self.max_output_bytes]
        stderr = stderr_full[: self.max_output_bytes]

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        stdout_text = _normalize_posix_paths_to_windows(stdout_text)
        stderr_text = _normalize_posix_paths_to_windows(stderr_text)

        output = _normalize_posix_paths_to_windows((stdout + stderr).decode("utf-8", errors="replace"))
        lines = output.splitlines()
        output_lines_truncated = len(lines) > self.max_output_lines
        if output_lines_truncated:
            output = "\n".join(lines[: self.max_output_lines])

        full_output_file_path: str | None = None
        if (stdout_truncated or stderr_truncated or output_lines_truncated) and ctx.project_dir:
            try:
                out_dir = Path(ctx.project_dir) / ".openagentic-sdk" / "tool-output"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"bash.{uuid.uuid4().hex}.txt"
                out_path.write_bytes(stdout_full + stderr_full)
                full_output_file_path = str(out_path)
            except Exception:  # pragma: no cover
                full_output_file_path = None

        return {
            "command": command,
            "exit_code": int(proc.returncode),
            "stdout": stdout_text,
            "stderr": stderr_text,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "output_lines_truncated": output_lines_truncated,
            "full_output_file_path": full_output_file_path,
            # CAS-compatible aliases:
            "output": output,
            "exitCode": int(proc.returncode),
            "killed": False,
            "shellId": None,
        }
