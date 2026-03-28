from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Protocol, TextIO

from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.paths import default_session_root
from openagentic_sdk.runtime import AgentRuntime
from openagentic_sdk.server.cluster_chat_client import ClusterChatClient, ClusterChatRuntime
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.skills.index import index_skills

from .permissions import CliPermissionPolicy, build_permission_gate
from .repl_input import ReplTurn, _windows_ctrl_c_consume
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


async def _remote_host_banner(options: OpenAgenticOptions) -> str | None:
    base_url = getattr(options, "remote_chat_base_url", None)
    if not isinstance(base_url, str) or not base_url.strip():
        return None

    timeout_s = getattr(options, "remote_chat_timeout_s", 10.0) or 10.0
    client = ClusterChatClient(base_url=base_url.strip(), timeout_s=min(float(timeout_s), 2.5))
    try:
        health = await asyncio.to_thread(client.health)
    except Exception as e:  # noqa: BLE001
        return f"note: remote host health preflight failed: {e}"

    deployment_mode = str(health.get("deployment_mode") or "").strip().lower()
    if deployment_mode == "smoke":
        return "warning: remote host is smoke-only; expect deterministic smoke replies, not a real model"
    if deployment_mode == "real-model":
        details: list[str] = []
        provider_profiles = health.get("provider_profiles")
        if isinstance(provider_profiles, list):
            names = [item for item in provider_profiles if isinstance(item, str) and item]
            if names:
                details.append(f"profiles={','.join(names)}")
        host_node_name = health.get("host_node_name")
        if isinstance(host_node_name, str) and host_node_name:
            details.append(f"node={host_node_name}")
        suffix = f" ({', '.join(details)})" if details else ""
        return f"remote: real-model host{suffix}"
    if "provider_ready" not in health and "config_source" not in health:
        return "warning: remote host /health has no provider metadata; this usually means the smoke cluster"
    return None


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
    remote_banner = await _remote_host_banner(opts)

    def _make_runtime(run_opts: OpenAgenticOptions):
        if getattr(run_opts, "remote_chat_base_url", None):
            return ClusterChatRuntime(run_opts)
        return AgentRuntime(run_opts)

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

    def _prompt_toolkit_unavailable_reason() -> str | None:
        if backend != "prompt_toolkit":
            return "disabled by OA_CLI_INPUT_BACKEND"
        if not (stdin_is_tty and is_tty):
            return "not a TTY"
        if not hasattr(stdin, "fileno"):
            return "stdin has no fileno()"
        if not hasattr(stdout, "fileno"):
            return "stdout has no fileno()"
        try:
            import prompt_toolkit  # noqa: F401
        except Exception as e:  # noqa: BLE001
            return f"import prompt_toolkit failed: {type(e).__name__}: {e}"
        return None

    ptk_reason = _prompt_toolkit_unavailable_reason()
    use_prompt_toolkit = ptk_reason is None
    if backend == "prompt_toolkit" and not use_prompt_toolkit and (stdin_is_tty and is_tty):
        details = f" ({ptk_reason})" if ptk_reason else ""
        _print(stdout, dim(f"note: prompt_toolkit input backend unavailable{details}; falling back to legacy", enabled=enable_color))

    debug_input_backend = os.getenv("OA_DEBUG_INPUT", "").strip().lower() in ("1", "true", "yes", "on")
    if debug_input_backend and stdin_is_tty and is_tty:
        chosen = "prompt_toolkit" if use_prompt_toolkit else "legacy"
        _print(stdout, dim(f"input backend: {chosen}", enabled=enable_color))

    if use_prompt_toolkit:
        # Prompt Toolkit backend (default for true TTYs). This is the most robust path
        # on Windows/ConPTY for editing semantics (arrows/backspace/CJK/typeahead).
        from prompt_toolkit import PromptSession  # noqa: PLC0415
        from prompt_toolkit.application.current import create_app_session  # noqa: PLC0415
        from prompt_toolkit.completion import (
            WordCompleter,  # noqa: PLC0415
            merge_completers,  # noqa: PLC0415
        )
        from prompt_toolkit.cursor_shapes import CursorShape  # noqa: PLC0415
        from prompt_toolkit.input.defaults import create_input  # noqa: PLC0415
        from prompt_toolkit.key_binding import KeyBindings  # noqa: PLC0415
        from prompt_toolkit.output.defaults import create_output  # noqa: PLC0415
        from prompt_toolkit.patch_stdout import patch_stdout  # noqa: PLC0415

        from .session_editor import (  # noqa: PLC0415
            SESSION_EDITOR_BUSY_REQUEST,
            SESSION_EDITOR_OPEN_REQUEST,
            run_session_editor,
        )

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

            from .repl_core.win_ctrl_c import (  # noqa: PLC0415
                _disable_windows_processed_input,
                _install_windows_ctrl_c_handler,
            )

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

            if remote_banner:
                _print(stdout, fg_red(remote_banner, enabled=enable_color) if remote_banner.startswith("warning:") else dim(remote_banner, enabled=enable_color))
            ptk_in = create_input(stdin, always_prefer_tty=True)
            ptk_out = create_output(sys.__stdout__ if stdout is sys.stdout else stdout, always_prefer_tty=True)
            session = PromptSession(input=ptk_in, output=ptk_out)

            _print(stdout, dim("Type /help for commands.", enabled=enable_color))

            slash_menu_enabled = os.getenv("OA_CLI_SLASH_MENU", "1").strip().lower() not in (
                "0",
                "false",
                "no",
                "off",
            )

            slash_commands = [
                "/help",
                "/exit",
                "/new",
                "/interrupt",
                "/debug",
                "/skills",
                "/skill",
                "/cmd",
                "/paste",
            ]

            slash_command_completer = (
                WordCompleter(
                    slash_commands,
                    ignore_case=True,
                    # Show a menu with all commands when the user typed only `/`.
                    match_middle=False,
                )
                if slash_menu_enabled
                else None
            )

            skills_menu_enabled = os.getenv("OA_CLI_SKILL_MENU", "1").strip().lower() not in (
                "0",
                "false",
                "no",
                "off",
            )

            project_dir = options.project_dir or options.cwd
            skills = index_skills(project_dir=str(project_dir)) if skills_menu_enabled else []
            skill_words = [f"${s.name}" for s in skills]
            skill_meta = {f"${s.name}": (s.description or "") for s in skills}
            skill_completer = (
                WordCompleter(skill_words, ignore_case=True, meta_dict=skill_meta, match_middle=False)
                if (skills_menu_enabled and skill_words)
                else None
            )

            completer = None
            completers = [c for c in (slash_command_completer, skill_completer) if c is not None]
            if completers:
                completer = merge_completers(completers, deduplicate=True)

            kb = KeyBindings()

            @kb.add("f12")  # type: ignore[misc]
            def _open_session_editor(event) -> None:  # noqa: ANN001
                if current_abort_event is not None:
                    event.app.exit(result=SESSION_EDITOR_BUSY_REQUEST)
                    return
                event.app.exit(result=SESSION_EDITOR_OPEN_REQUEST)

            if slash_menu_enabled or skills_menu_enabled:
                @kb.add("/")  # type: ignore[misc]
                def _slash_opens_menu(event) -> None:  # noqa: ANN001
                    buf = event.app.current_buffer
                    if buf.document.text_before_cursor != "":
                        buf.insert_text("/")
                        return
                    buf.insert_text("/")
                    if slash_menu_enabled:
                        buf.start_completion(select_first=False)

                @kb.add("$")  # type: ignore[misc]
                def _dollar_opens_menu(event) -> None:  # noqa: ANN001
                    buf = event.app.current_buffer
                    buf.insert_text("$")
                    if skill_completer is not None:
                        buf.start_completion(select_first=False)

                @kb.add("enter", eager=True)  # type: ignore[misc]
                def _enter_accepts_menu_item_without_submitting(event) -> None:  # noqa: ANN001
                    buf = event.app.current_buffer
                    if buf.complete_state is not None and buf.complete_state.current_completion is not None:
                        buf.apply_completion(buf.complete_state.current_completion)
                        return
                    buf.validate_and_handle()

            bottom_toolbar_enabled = os.getenv("OA_CLI_BOTTOM_TOOLBAR", "1").strip().lower() not in (
                "0",
                "false",
                "no",
                "off",
            )

            def _bottom_toolbar() -> str:
                if not bottom_toolbar_enabled:
                    return ""
                cols = shutil.get_terminal_size(fallback=(80, 24)).columns
                text = f" cwd: {options.cwd} "
                if cols > 0 and len(text) > cols:
                    keep = max(0, cols - 2)
                    return "…" + text[-keep:]
                return text

            def _ptk_prompt_kwargs(*, paste_mode: bool = False) -> dict[str, object]:
                kwargs: dict[str, object] = {
                    "message": ("paste> " if paste_mode else "oa> "),
                    # No frame: on some Windows terminals/ConPTY combinations, frames can appear to
                    # extend down to the bottom of the viewport. Keep input UX stable and minimal.
                    "wrap_lines": True,
                    "cursor": CursorShape.BLINKING_BEAM,
                    "completer": completer,
                    "key_bindings": kb,
                    "complete_while_typing": False,
                    "reserve_space_for_menu": 6 if (slash_menu_enabled or skills_menu_enabled) else 0,
                    "handle_sigint": False,
                }
                if bottom_toolbar_enabled:
                    kwargs["bottom_toolbar"] = _bottom_toolbar
                return kwargs

            prompt_task: asyncio.Task[object] | None = None
            prefetched_line: object | None = None
            try:
                while True:
                    try:
                        if prefetched_line is not None:
                            line = prefetched_line
                            prefetched_line = None
                        elif prompt_task is not None:
                            line = await prompt_task
                            prompt_task = None
                        else:
                            line = await session.prompt_async(**_ptk_prompt_kwargs())
                    except EOFError:
                        _print(stdout, "")
                        return 0
                    except KeyboardInterrupt:
                        # Ctrl+C at prompt: do not create a user turn.
                        prompt_task = None
                        continue

                    if line == SESSION_EDITOR_BUSY_REQUEST:
                        _print(stdout, dim("session editor unavailable while busy", enabled=enable_color))
                        continue
                    if line == SESSION_EDITOR_OPEN_REQUEST:
                        if not session_id:
                            _print(stdout, dim("current session is empty; nothing to edit", enabled=enable_color))
                            continue
                        with create_app_session(input=ptk_in, output=ptk_out):
                            outcome = await run_session_editor(store=store, session_id=session_id)
                        if outcome.status == "saved":
                            _print(stdout, dim("session updated", enabled=enable_color))
                        elif outcome.status == "conflict":
                            _print(stdout, fg_red("session editor save failed: session changed", enabled=enable_color))
                        elif outcome.status == "error":
                            _print(
                                stdout,
                                fg_red(
                                    outcome.message or "session editor save failed",
                                    enabled=enable_color,
                                ),
                            )
                        elif outcome.status == "empty":
                            _print(stdout, dim("current session has no editable messages", enabled=enable_color))
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
                                    s = await session.prompt_async(**_ptk_prompt_kwargs(paste_mode=True))
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
                        runtime = _make_runtime(run_opts)

                        # Prefetch the next prompt so users can type ahead while output streams.
                        if prompt_task is None:
                            prompt_task = asyncio.create_task(session.prompt_async(**_ptk_prompt_kwargs()))

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
                                if exc is None:
                                    result = None
                                    try:
                                        result = prompt_task.result()
                                    except asyncio.CancelledError:
                                        result = None
                                    except Exception:
                                        result = None
                                    if result == SESSION_EDITOR_BUSY_REQUEST:
                                        _print(stdout, dim("session editor unavailable while busy", enabled=enable_color))
                                        prompt_task = asyncio.create_task(session.prompt_async(**_ptk_prompt_kwargs()))
                                    elif result == SESSION_EDITOR_OPEN_REQUEST:
                                        _print(stdout, dim("session editor unavailable while busy", enabled=enable_color))
                                        prompt_task = asyncio.create_task(session.prompt_async(**_ptk_prompt_kwargs()))
                                    elif result is not None:
                                        prefetched_line = result
                                        prompt_task = None
                            if os.name == "nt" and _windows_ctrl_c_consume():
                                abort_event.set()
                                raise KeyboardInterrupt
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
                            if exc is None:
                                result = None
                                try:
                                    result = prompt_task.result()
                                except asyncio.CancelledError:
                                    result = None
                                except Exception:
                                    result = None
                                if result == SESSION_EDITOR_BUSY_REQUEST:
                                    _print(stdout, dim("session editor unavailable while busy", enabled=enable_color))
                                    prompt_task = asyncio.create_task(session.prompt_async(**_ptk_prompt_kwargs()))
                                elif result == SESSION_EDITOR_OPEN_REQUEST:
                                    _print(stdout, dim("session editor unavailable while busy", enabled=enable_color))
                                    prompt_task = asyncio.create_task(session.prompt_async(**_ptk_prompt_kwargs()))
                                elif result is not None:
                                    prefetched_line = result
                                    prompt_task = None
                        # Visual separation: keep one blank line between the end of the assistant/tool output
                        # and the user's next prompt line.
                        _print(stdout, "")
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
    if remote_banner:
        _print(stdout, fg_red(remote_banner, enabled=enable_color) if remote_banner.startswith("warning:") else dim(remote_banner, enabled=enable_color))
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
                runtime = _make_runtime(run_opts)
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
