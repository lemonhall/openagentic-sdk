from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
from contextlib import nullcontext
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol, TextIO

from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.paths import default_session_root
from openagentic_sdk.runtime import AgentRuntime
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.skills.index import index_skills

from .permissions import CliPermissionPolicy, build_permission_gate
from .repl_input import ReplTurn
from .repl_input import _windows_ctrl_c_consume
from .style import (
    ANSI_BG_GRAY,
    ANSI_FG_DEFAULT,
    ANSI_FG_GREEN,
    ANSI_RESET,
    InlineCodeHighlighter,
    StyleConfig,
    StylizingStream,
    bold,
    dim,
    fg_red,
    should_colorize,
)
from .trace import TraceRenderer


class ReadReplTurn(Protocol):
    def __call__(self, stdin: TextIO, *, paste_mode: bool = False) -> ReplTurn | None: ...


class ParseReplCommand(Protocol):
    def __call__(self, line: str) -> tuple[str, str] | None: ...


class DisablePosixEchoctl(Protocol):
    def __call__(self, stdin: TextIO) -> Callable[[], None] | None: ...


class EnableWindowsVtInput(Protocol):
    def __call__(self, stdin: TextIO) -> Callable[[], None] | None: ...


def _print(stdout: TextIO, text: str) -> None:
    stdout.write(text)
    if not text.endswith("\n"):
        stdout.write("\n")
    stdout.flush()


_CWD_QUESTION_RE = re.compile(
    r"^\s*(?:当前目录(?:是|为)?|当前路径|pwd|where am i|current directory)\s*[?？]?\s*$",
    re.IGNORECASE,
)


async def run_chat_impl(
    options: OpenAgenticOptions,
    *,
    color_config: StyleConfig,
    debug: bool,
    stdin: TextIO,
    stdout: TextIO,
    read_turn: ReadReplTurn,
    parse_command: ParseReplCommand,
    disable_posix_echoctl: DisablePosixEchoctl,
    enable_windows_vt_input: EnableWindowsVtInput,
    bp_enable: str,
    bp_disable: str,
) -> int:
    enable_color = should_colorize(color_config, isatty=getattr(stdout, "isatty", lambda: False)(), platform=sys.platform)
    show_thinking_hint = os.getenv("OA_SHOW_THINKING", "1").strip().lower() not in ("0", "false", "no", "off")
    is_tty = bool(getattr(stdout, "isatty", lambda: False)())
    trace_enabled = os.getenv("OA_TRACE", "1").strip().lower() not in ("0", "false", "no", "off")
    bracketed_paste_enabled = os.getenv("OA_BRACKETED_PASTE", "1").strip().lower() not in ("0", "false", "no", "off")

    render_stream = StylizingStream(stdout, highlighter=InlineCodeHighlighter(enabled=enable_color)) if enable_color else stdout
    renderer = (
        TraceRenderer(stream=render_stream, color=enable_color, show_hooks=debug)
        if trace_enabled
        else TraceRenderer(stream=render_stream, color=False, show_hooks=debug)
    )
    turn = 0

    store = options.session_store
    if store is None:
        root = options.session_root
        if root is None:
            root = default_session_root()
        store = FileSessionStore(root_dir=Path(str(root)).expanduser())
    opts = replace(options, session_store=store)

    def _prompt_yes_no(prompt: str) -> bool:
        stdout.write(prompt)
        stdout.flush()
        ans = stdin.readline()
        return str(ans).strip().lower() in ("y", "yes")

    stdin_is_tty = bool(getattr(stdin, "isatty", lambda: False)())
    perm_mode = getattr(getattr(opts, "permission_gate", None), "permission_mode", "default")
    autoapprove_prompt_enabled = os.getenv("OA_CLI_AUTOAPPROVE_PROMPT", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    if (
        is_tty
        and stdin_is_tty
        and autoapprove_prompt_enabled
        and str(perm_mode).strip().lower() in ("default", "prompt", "acceptedits", "callback")
    ):
        base = Path(opts.cwd)
        auto_prompt = f"Auto-approve Write/Edit/Bash within `{base}` (and subdirs) for this chat session? [y/N] "
        auto_allow = _prompt_yes_no(auto_prompt)
        policy = CliPermissionPolicy(
            cwd=base,
            auto_root=base,
            auto_allow_dangerous=auto_allow,
            prompt_fn=_prompt_yes_no,
        )
        opts = replace(opts, permission_gate=build_permission_gate(policy))

    session_id = opts.resume
    current_abort_event: asyncio.Event | None = None

    backend0 = os.getenv("OA_CLI_INPUT_BACKEND", "prompt_toolkit").strip().lower()
    backend = backend0 if backend0 in ("prompt_toolkit", "legacy") else "prompt_toolkit"

    def _can_use_prompt_toolkit() -> bool:
        if backend != "prompt_toolkit":
            return False
        if not (stdin_is_tty and is_tty):
            return False
        if not hasattr(stdin, "fileno"):
            return False
        if not hasattr(stdout, "fileno"):
            return False
        try:
            import prompt_toolkit  # noqa: F401
        except Exception:
            return False
        return True

    use_prompt_toolkit = _can_use_prompt_toolkit()
    if backend == "prompt_toolkit" and not use_prompt_toolkit and (stdin_is_tty and is_tty):
        _print(stdout, dim("note: prompt_toolkit input backend unavailable; falling back to legacy", enabled=enable_color))

    debug_input_backend = os.getenv("OA_DEBUG_INPUT", "").strip().lower() in ("1", "true", "yes", "on")
    if debug_input_backend and stdin_is_tty and is_tty:
        chosen = "prompt_toolkit" if use_prompt_toolkit else "legacy"
        _print(stdout, dim(f"input backend: {chosen}", enabled=enable_color))

    if use_prompt_toolkit:
        # Prompt Toolkit backend (default for true TTYs). This is the most robust path
        # on Windows/ConPTY for editing semantics (arrows/backspace/CJK/typeahead).
        from prompt_toolkit import PromptSession  # noqa: PLC0415
        from prompt_toolkit.input.defaults import create_input  # noqa: PLC0415
        from prompt_toolkit.output.defaults import create_output  # noqa: PLC0415
        from prompt_toolkit.patch_stdout import patch_stdout  # noqa: PLC0415

        restore_processed: Callable[[], None] | None = None
        restore_sigint = None
        if os.name == "nt":
            # On Windows + ConPTY, Ctrl+C can surface as a process-level SIGINT that
            # bypasses our coroutine-level try/except and terminates the process.
            # Ignore SIGINT and rely on Prompt Toolkit keybindings + our own abort plumbing.
            import signal  # noqa: PLC0415

            old_sigint = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            restore_sigint = lambda: signal.signal(signal.SIGINT, old_sigint)  # noqa: E731

            from .repl_core.win_ctrl_c import _disable_windows_processed_input, _install_windows_ctrl_c_handler  # noqa: PLC0415

            _install_windows_ctrl_c_handler()
            restore_processed = _disable_windows_processed_input(stdin)

        patch_ctx = patch_stdout() if stdout is sys.stdout else nullcontext()
        with patch_ctx:
            # Inside patch_stdout, prefer writing through the patched sys.stdout proxy.
            if stdout is sys.stdout:
                stdout = sys.stdout
                render_stream = (
                    StylizingStream(stdout, highlighter=InlineCodeHighlighter(enabled=enable_color)) if enable_color else stdout
                )
                renderer = (
                    TraceRenderer(stream=render_stream, color=enable_color, show_hooks=debug)
                    if trace_enabled
                    else TraceRenderer(stream=render_stream, color=False, show_hooks=debug)
                )

            ptk_in = create_input(stdin, always_prefer_tty=True)
            ptk_out = create_output(sys.__stdout__ if stdout is sys.stdout else stdout, always_prefer_tty=True)
            session = PromptSession(input=ptk_in, output=ptk_out)

            _print(stdout, dim("Type /help for commands.", enabled=enable_color))

            prompt_task: asyncio.Task[str] | None = None
            try:
                while True:
                    try:
                        if prompt_task is not None:
                            line = await prompt_task
                            prompt_task = None
                        else:
                            stdout.write("oa> ")
                            stdout.flush()
                            line = await session.prompt_async("", handle_sigint=False)
                    except EOFError:
                        _print(stdout, "")
                        return 0
                    except KeyboardInterrupt:
                        # Ctrl+C at prompt: do not create a user turn.
                        prompt_task = None
                        continue

                    turn_obj = ReplTurn(line, is_paste=("\n" in line))
                    line2 = turn_obj.text

                    # Do not interpret pasted content as a REPL command.
                    cmd = None if turn_obj.is_paste else parse_command(line2)
                    if cmd is not None:
                        name, arg = cmd
                        if name in ("exit", "quit"):
                            return 0
                        if name == "help":
                            _print(
                                stdout,
                                "\n".join(
                                    [
                                        bold("Commands:", enabled=enable_color),
                                        "  /help",
                                        "  /exit",
                                        "  /new",
                                        "  /interrupt",
                                        "  /debug",
                                        "  /skills",
                                        "  /skill <name>",
                                        "  /cmd <name>",
                                        "  /paste (finish with /end)",
                                    ]
                                ),
                            )
                            continue
                        if name == "debug":
                            debug = not debug
                            _print(stdout, dim(f"debug={'on' if debug else 'off'}", enabled=enable_color))
                            continue
                        if name == "interrupt":
                            if current_abort_event is not None:
                                current_abort_event.set()
                            _print(stdout, dim("interrupt signaled", enabled=enable_color))
                            continue
                        if name == "new":
                            session_id = None
                            opts = replace(opts, resume=None)
                            turn = 0
                            _print(stdout, dim("started new session", enabled=enable_color))
                            continue
                        if name == "skills":
                            project_dir = options.project_dir or options.cwd
                            skills = index_skills(project_dir=str(project_dir))
                            if not skills:
                                _print(stdout, "(no skills found)")
                            else:
                                for s in skills:
                                    _print(stdout, f"- {s.name}: {s.description}".rstrip())
                            continue
                        if name == "paste":
                            _print(stdout, dim("paste mode: finish with /end", enabled=enable_color))
                            lines: list[str] = []
                            while True:
                                try:
                                    s = await session.prompt_async("", handle_sigint=False)
                                except EOFError:
                                    break
                                if s.strip() == "/end":
                                    break
                                lines.append(s)
                            line2 = "\n".join(lines)
                            turn_obj = ReplTurn(line2, is_paste=True, is_manual_paste=True)
                        elif name == "skill":
                            if not arg:
                                _print(stdout, fg_red("usage: /skill <name>", enabled=enable_color))
                                continue
                            line2 = f"执行技能 {arg}"
                        elif name == "cmd":
                            if not arg:
                                _print(stdout, fg_red("usage: /cmd <name>", enabled=enable_color))
                                continue
                            line2 = f"Run slash command {arg}"
                        else:
                            _print(stdout, fg_red(f"unknown command: /{name}", enabled=enable_color))
                            continue

                    prompt_text = line2.rstrip("\r\n")
                    if not prompt_text.strip():
                        continue
                    if _CWD_QUESTION_RE.match(prompt_text):
                        _print(stdout, f"当前目录：{options.cwd}")
                        continue

                    try:
                        turn += 1
                        if show_thinking_hint and is_tty:
                            _print(stdout, dim("thinking…", enabled=enable_color))

                        abort_event = asyncio.Event()
                        current_abort_event = abort_event
                        run_opts = replace(opts, resume=session_id, abort_event=abort_event)
                        runtime = AgentRuntime(run_opts)

                        # Prefetch the next prompt so users can type ahead while output streams.
                        if prompt_task is None:
                            stdout.write("oa> ")
                            stdout.flush()
                            prompt_task = asyncio.create_task(session.prompt_async("", handle_sigint=False))

                        async for ev in runtime.query(prompt_text):
                            if getattr(ev, "type", None) == "system.init":
                                sid = getattr(ev, "session_id", None)
                                if isinstance(sid, str) and sid:
                                    session_id = sid
                            renderer.on_event(ev)
                            if prompt_task is not None and prompt_task.done():
                                exc = None
                                try:
                                    exc = prompt_task.exception()
                                except asyncio.CancelledError:
                                    exc = None
                                except Exception:
                                    exc = None
                                if isinstance(exc, KeyboardInterrupt):
                                    prompt_task = None
                                    abort_event.set()
                                    raise KeyboardInterrupt
                            if os.name == "nt" and _windows_ctrl_c_consume():
                                abort_event.set()
                                raise KeyboardInterrupt
                        current_abort_event = None
                        if session_id:
                            opts = replace(opts, resume=session_id)
                    except KeyboardInterrupt:
                        if current_abort_event is not None:
                            current_abort_event.set()
                        _print(stdout, dim("interrupted", enabled=enable_color))
                        continue
                    except SystemExit as e:
                        _print(stdout, fg_red(str(e), enabled=enable_color))
                        return 1
                    except Exception as e:  # noqa: BLE001
                        _print(stdout, fg_red(str(e), enabled=enable_color))
                        return 1
            finally:
                if restore_processed is not None:
                    restore_processed()
                if restore_sigint is not None:
                    try:
                        restore_sigint()
                    except Exception:
                        pass
                if prompt_task is not None:
                    try:
                        prompt_task.cancel()
                    except Exception:
                        pass

    # Input mode should be keyed off stdin TTY-ness. We still only emit the
    # bracketed-paste enable/disable sequences when stdout is a TTY.
    enable_bracketed_paste = bool(bracketed_paste_enabled and stdin_is_tty)
    restore_vt: Callable[[], None] | None = None
    restore_echoctl: Callable[[], None] | None = None
    if enable_bracketed_paste:
        try:
            restore_echoctl = disable_posix_echoctl(stdin)
            restore_vt = enable_windows_vt_input(stdin)
            if is_tty:
                stdout.write(bp_enable)
                stdout.flush()
        except Exception:
            enable_bracketed_paste = False
            if restore_echoctl is not None:
                restore_echoctl()
                restore_echoctl = None
            if restore_vt is not None:
                restore_vt()
                restore_vt = None

    if backend == "legacy" and (stdin_is_tty and is_tty):
        _print(stdout, dim("note: legacy CLI input backend is deprecated (use OA_CLI_INPUT_BACKEND=prompt_toolkit)", enabled=enable_color))
    _print(stdout, dim("Type /help for commands.", enabled=enable_color))
    try:
        while True:
            prompt = "oa> "
            if enable_color:
                cols = int(shutil.get_terminal_size(fallback=(80, 24)).columns)

                # Add some vertical padding for the input area: one blank gray line above.
                stdout.write(ANSI_BG_GRAY + (" " * cols) + ANSI_RESET + "\n")

                # Render the prompt on a full-width gray background while keeping the cursor
                # right after the prompt (so the user types on the gray line).
                styled_prompt = f"{ANSI_BG_GRAY}{ANSI_FG_GREEN}{prompt}{ANSI_FG_DEFAULT}"
                fill = " " * max(0, cols - len(prompt))
                if fill:
                    stdout.write(styled_prompt + fill + "\r" + styled_prompt)
                else:
                    stdout.write(styled_prompt)
                stdout.flush()
            else:
                stdout.write(prompt)
                stdout.flush()

            try:
                turn_obj = read_turn(stdin)
            except KeyboardInterrupt:
                if enable_color:
                    stdout.write(ANSI_RESET + "\n")
                    stdout.flush()
                continue

            if enable_color:
                # Add one blank gray line below the user's input ("margin-bottom"), then
                # reset so subsequent model output has no background.
                cols = int(shutil.get_terminal_size(fallback=(80, 24)).columns)
                stdout.write(ANSI_BG_GRAY + (" " * cols) + ANSI_RESET + "\n")
                stdout.flush()

            if turn_obj is None:
                if enable_color:
                    stdout.write(ANSI_RESET)
                    stdout.flush()
                _print(stdout, "")
                return 0

            line = turn_obj.text

            # Do not interpret pasted content as a REPL command.
            cmd = None if turn_obj.is_paste else parse_command(line)
            if cmd is not None:
                name, arg = cmd
                if name in ("exit", "quit"):
                    return 0
                if name == "help":
                    _print(
                        stdout,
                        "\n".join(
                            [
                                bold("Commands:", enabled=enable_color),
                                "  /help",
                                "  /exit",
                                "  /new",
                                "  /interrupt",
                                "  /debug",
                                "  /skills",
                                "  /skill <name>",
                                "  /cmd <name>",
                                "  /paste (finish with /end)",
                            ]
                        ),
                    )
                    continue
                if name == "debug":
                    debug = not debug
                    _print(stdout, dim(f"debug={'on' if debug else 'off'}", enabled=enable_color))
                    continue
                if name == "interrupt":
                    if current_abort_event is not None:
                        current_abort_event.set()
                    _print(stdout, dim("interrupt signaled", enabled=enable_color))
                    continue
                if name == "new":
                    session_id = None
                    opts = replace(opts, resume=None)
                    turn = 0
                    _print(stdout, dim("started new session", enabled=enable_color))
                    continue
                if name == "skills":
                    project_dir = options.project_dir or options.cwd
                    skills = index_skills(project_dir=str(project_dir))
                    if not skills:
                        _print(stdout, "(no skills found)")
                    else:
                        for s in skills:
                            _print(stdout, f"- {s.name}: {s.description}".rstrip())
                    continue
                if name == "paste":
                    _print(stdout, dim("paste mode: finish with /end", enabled=enable_color))
                    turn_obj2 = read_turn(stdin, paste_mode=True)
                    if turn_obj2 is None:
                        _print(stdout, "")
                        return 0
                    line = turn_obj2.text
                elif name == "skill":
                    if not arg:
                        _print(stdout, fg_red("usage: /skill <name>", enabled=enable_color))
                        continue
                    line = f"执行技能 {arg}"
                elif name == "cmd":
                    if not arg:
                        _print(stdout, fg_red("usage: /cmd <name>", enabled=enable_color))
                        continue
                    line = f"Run slash command {arg}"
                else:
                    _print(stdout, fg_red(f"unknown command: /{name}", enabled=enable_color))
                    continue

            prompt_text = line.rstrip("\r\n")
            if not prompt_text.strip():
                continue
            if _CWD_QUESTION_RE.match(prompt_text):
                _print(stdout, f"当前目录：{options.cwd}")
                continue

            try:
                turn += 1
                if show_thinking_hint and is_tty:
                    _print(stdout, dim("thinking…", enabled=enable_color))

                abort_event = asyncio.Event()
                current_abort_event = abort_event
                run_opts = replace(opts, resume=session_id, abort_event=abort_event)
                runtime = AgentRuntime(run_opts)
                async for ev in runtime.query(prompt_text):
                    if getattr(ev, "type", None) == "system.init":
                        sid = getattr(ev, "session_id", None)
                        if isinstance(sid, str) and sid:
                            session_id = sid
                    renderer.on_event(ev)
                    if os.name == "nt" and _windows_ctrl_c_consume():
                        abort_event.set()
                        raise KeyboardInterrupt
                current_abort_event = None
                if session_id:
                    opts = replace(opts, resume=session_id)
            except KeyboardInterrupt:
                if current_abort_event is not None:
                    current_abort_event.set()
                _print(stdout, dim("interrupted", enabled=enable_color))
                continue
            except SystemExit as e:
                _print(stdout, fg_red(str(e), enabled=enable_color))
                return 1
            except Exception as e:  # noqa: BLE001
                _print(stdout, fg_red(str(e), enabled=enable_color))
                return 1
    finally:
        if enable_bracketed_paste and is_tty:
            try:
                stdout.write(bp_disable)
                stdout.flush()
            except Exception:
                pass
        if restore_echoctl is not None:
            restore_echoctl()
        if restore_vt is not None:
            restore_vt()
