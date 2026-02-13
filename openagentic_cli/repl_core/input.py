from __future__ import annotations

import os
import select
from collections.abc import Callable
from typing import TextIO

from . import win_raw
from .types import _BP_END, _BP_START, ReplTurn, _strip_bracketed_paste_markers


def _stdin_has_buffered_input(stdin: TextIO) -> bool:
    """Best-effort check for already-buffered stdin input (TTY only).

    Used as a fallback for terminals that don't emit bracketed paste markers:
    multi-line pastes typically arrive fully buffered, so we can coalesce them
    into one turn without blocking.
    """

    if not bool(getattr(stdin, "isatty", lambda: False)()):
        return False

    # `TextIOWrapper.readline()` may read ahead and keep additional decoded
    # characters buffered in-memory (especially for pipes). If so, we can
    # coalesce multi-line pastes without relying on OS-level readiness checks.
    try:
        decoded = getattr(stdin, "_decoded_chars", None)
        used = int(getattr(stdin, "_decoded_chars_used", 0))
        if isinstance(decoded, str) and len(decoded) > used:
            return True
    except Exception:  # noqa: BLE001
        pass

    try:
        fd = stdin.fileno()
    except Exception:  # noqa: BLE001
        fd = None

    if fd is not None and os.name != "nt":
        try:
            r, _w, _x = select.select([fd], [], [], 0)
            return bool(r)
        except Exception:  # noqa: BLE001
            return False

    if os.name == "nt" and fd is not None:
        # Windows `select()` only supports sockets; for pipes (like our unit
        # tests), use PeekNamedPipe when possible.
        try:
            import ctypes
            import msvcrt  # type: ignore[import-not-found]

            handle = msvcrt.get_osfhandle(fd)
            avail = ctypes.c_uint32(0)
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            ok = kernel32.PeekNamedPipe(handle, None, 0, None, ctypes.byref(avail), None)
            if ok:
                return int(avail.value) > 0
        except Exception:  # noqa: BLE001
            pass

        try:
            import msvcrt  # type: ignore[import-not-found]

            return bool(msvcrt.kbhit())
        except Exception:  # noqa: BLE001
            return False

    return False


def _disable_posix_echoctl(stdin: TextIO) -> Callable[[], None] | None:
    """Best-effort: disable ECHOCTL so bracketed paste markers don't render as `^[[200~`."""

    if os.name == "nt":
        return None
    if not bool(getattr(stdin, "isatty", lambda: False)()):
        return None
    try:
        import termios  # noqa: PLC0415

        echoctl = getattr(termios, "ECHOCTL", None)
        if echoctl is None:
            return None
        fd = stdin.fileno()
        old_attrs = termios.tcgetattr(fd)
        old_lflag = int(old_attrs[3])
        if not (old_lflag & echoctl):
            return None

        new_attrs = list(old_attrs)
        new_attrs[3] = old_lflag & ~echoctl
        termios.tcsetattr(fd, termios.TCSADRAIN, new_attrs)

        def _restore() -> None:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
            except Exception:  # noqa: BLE001
                pass

        return _restore
    except Exception:  # noqa: BLE001
        return None


def read_repl_turn(stdin: TextIO, *, paste_mode: bool = False) -> ReplTurn | None:
    """Read one user 'turn' from stdin.

    - Normal mode: reads exactly one line, unless bracketed paste markers are
      present; in that case, it keeps reading until the end marker.
    - paste_mode=True: reads multiple lines until a sentinel line `/end`.

    Returns None on EOF.
    """

    if os.name == "nt" and win_raw._WIN_RAW_ENABLED and bool(getattr(stdin, "isatty", lambda: False)()):
        turn = win_raw._read_repl_turn_windows_raw(stdin, paste_mode=paste_mode)
        if turn is not None:
            return turn
    return _read_repl_turn_line_based(stdin, paste_mode=paste_mode)


def _read_repl_turn_line_based(stdin: TextIO, *, paste_mode: bool) -> ReplTurn | None:
    if paste_mode:
        lines: list[str] = []
        while True:
            line = stdin.readline()
            if line == "":
                break
            s0 = _strip_bracketed_paste_markers(line)
            s = s0.rstrip("\r\n")
            if s.strip() == "/end":
                break
            # If bracketed paste markers arrive on their own line, ignore them
            # rather than treating them as an intentional blank line.
            if s == "" and line.strip() in {_BP_START, _BP_END}:
                continue
            lines.append(s)
        if not lines and line == "":
            return None
        return ReplTurn("\n".join(lines), is_paste=True, is_manual_paste=True)

    first = stdin.readline()
    if first == "":
        return None

    is_paste = (_BP_START in first) or (_BP_END in first)
    in_paste = (_BP_START in first) and (_BP_END not in first)

    parts = [_strip_bracketed_paste_markers(first)]
    while in_paste:
        chunk = stdin.readline()
        if chunk == "":
            break
        if _BP_END in chunk:
            in_paste = False
        parts.append(_strip_bracketed_paste_markers(chunk))

    # Fallback coalescing for terminals that don't emit bracketed paste markers.
    # On Windows console/ConPTY this readiness heuristic is unreliable and can
    # lead to hangs (blocking on `.readline()` when no full line is available),
    # so keep it POSIX-only.
    if os.name != "nt" and (not is_paste and _stdin_has_buffered_input(stdin)):
        is_paste = True
        while _stdin_has_buffered_input(stdin):
            chunk = stdin.readline()
            if chunk == "":
                break
            parts.append(chunk)

    text = "".join(parts).rstrip("\r\n")
    return ReplTurn(text, is_paste=is_paste)
