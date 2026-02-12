from __future__ import annotations

import os
import re
import select
from collections.abc import Callable
from collections import deque
from dataclasses import dataclass
from typing import TextIO

_BP_ENABLE = "\x1b[?2004h"
_BP_DISABLE = "\x1b[?2004l"
_BP_START = "\x1b[200~"
_BP_END = "\x1b[201~"


@dataclass(frozen=True, slots=True)
class ReplTurn:
    text: str
    is_paste: bool
    is_manual_paste: bool = False


_VT_KEY_SEQ_RE = re.compile(
    r"(?:\x1b\[[0-9;?]*[A-Za-z~]|\x1bO[PFQRS])"
)

_WIN_RAW_ENABLED = False
_WIN_CTRL_C_PRESSED = None
_WIN_CTRL_C_HANDLER_INSTALLED = False
_WIN_CTRL_C_HANDLER = None
_WIN_PENDING_CHARS: deque[str] = deque()


def _windows_ctrl_c_consume() -> bool:
    global _WIN_CTRL_C_PRESSED
    if os.name != "nt":
        return False
    if _WIN_CTRL_C_PRESSED is None:
        return False
    if _WIN_CTRL_C_PRESSED.is_set():
        _WIN_CTRL_C_PRESSED.clear()
        return True
    return False


def _windows_ctrl_c_peek() -> bool:
    if os.name != "nt":
        return False
    if _WIN_CTRL_C_PRESSED is None:
        return False
    return bool(_WIN_CTRL_C_PRESSED.is_set())


def _install_windows_ctrl_c_handler() -> None:
    global _WIN_CTRL_C_HANDLER_INSTALLED, _WIN_CTRL_C_HANDLER, _WIN_CTRL_C_PRESSED

    if os.name != "nt":
        return
    if _WIN_CTRL_C_HANDLER_INSTALLED:
        return

    import ctypes
    from ctypes import wintypes
    import threading

    _WIN_CTRL_C_PRESSED = threading.Event()

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    # https://learn.microsoft.com/windows/console/handlerroutine
    HANDLER = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    CTRL_C_EVENT = 0

    def _handler(ctrl_type: int) -> int:
        if ctrl_type == CTRL_C_EVENT:
            assert _WIN_CTRL_C_PRESSED is not None
            _WIN_CTRL_C_PRESSED.set()
            return 1
        return 0

    _WIN_CTRL_C_HANDLER = HANDLER(_handler)
    kernel32.SetConsoleCtrlHandler(_WIN_CTRL_C_HANDLER, True)
    _WIN_CTRL_C_HANDLER_INSTALLED = True


def _strip_bracketed_paste_markers(s: str) -> str:
    # Terminals wrap pasted content in these escape sequences when bracketed
    # paste mode is enabled.
    return s.replace(_BP_START, "").replace(_BP_END, "")


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


def _enable_windows_vt_input(stdin: TextIO) -> Callable[[], None] | None:
    """Enable Windows virtual terminal input so bracketed paste markers arrive on stdin."""

    if os.name != "nt":
        return None
    try:
        import ctypes
        import msvcrt  # type: ignore[import-not-found]

        handle = msvcrt.get_osfhandle(stdin.fileno())
        mode = ctypes.c_uint32()
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return None
        old_mode = int(mode.value)
        enable_vt = 0x0200  # ENABLE_VIRTUAL_TERMINAL_INPUT
        enable_processed = 0x0001  # ENABLE_PROCESSED_INPUT
        enable_line = 0x0002  # ENABLE_LINE_INPUT
        enable_echo = 0x0004  # ENABLE_ECHO_INPUT

        # When VT input is enabled, many terminals send Backspace as DEL (0x7f).
        # With Windows line editing enabled, DEL can delete the whole last word.
        # Switch to a minimal "raw-ish" mode and handle editing ourselves.
        new_mode = (old_mode | enable_vt) & ~(enable_line | enable_echo)
        new_mode = new_mode & ~enable_processed
        if new_mode == old_mode:
            return lambda: None
        if not kernel32.SetConsoleMode(handle, new_mode):
            return None

        _install_windows_ctrl_c_handler()
        global _WIN_RAW_ENABLED
        _WIN_RAW_ENABLED = True

        def _restore() -> None:
            global _WIN_RAW_ENABLED
            try:
                kernel32.SetConsoleMode(handle, old_mode)
            except Exception:  # noqa: BLE001
                pass
            _WIN_RAW_ENABLED = False

        return _restore
    except Exception:  # noqa: BLE001
        return None


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

    if os.name == "nt" and _WIN_RAW_ENABLED and bool(getattr(stdin, "isatty", lambda: False)()):
        return _read_repl_turn_windows_raw(stdin, paste_mode=paste_mode)
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


def _read_repl_turn_windows_raw(stdin: TextIO, *, paste_mode: bool) -> ReplTurn | None:
    """Windows-only: raw-ish console input reader (ConPTY-friendly).

    Requires `_enable_windows_vt_input()` to have flipped console modes; this is
    intentionally conservative so unit tests using StringIO keep the simple path.
    """

    import ctypes
    import msvcrt  # type: ignore[import-not-found]
    from ctypes import wintypes

    if _windows_ctrl_c_consume():
        raise KeyboardInterrupt

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = msvcrt.get_osfhandle(stdin.fileno())

    # Validate handle is a console handle.
    mode = wintypes.DWORD()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        # Fallback to line-based path if we can't treat this as a console.
        return _read_repl_turn_line_based(stdin, paste_mode=paste_mode)

    class _CHAR_UNION(ctypes.Union):
        _fields_ = [("UnicodeChar", wintypes.WCHAR), ("AsciiChar", wintypes.CHAR)]

    class _KEY_EVENT_RECORD(ctypes.Structure):
        _fields_ = [
            ("bKeyDown", wintypes.BOOL),
            ("wRepeatCount", wintypes.WORD),
            ("wVirtualKeyCode", wintypes.WORD),
            ("wVirtualScanCode", wintypes.WORD),
            ("uChar", _CHAR_UNION),
            ("dwControlKeyState", wintypes.DWORD),
        ]

    class _EVENT_UNION(ctypes.Union):
        _fields_ = [("KeyEvent", _KEY_EVENT_RECORD)]

    class _INPUT_RECORD(ctypes.Structure):
        _anonymous_ = ("Event",)
        _fields_ = [("EventType", wintypes.WORD), ("Event", _EVENT_UNION)]

    KEY_EVENT = 0x0001
    WAIT_OBJECT_0 = 0
    WAIT_TIMEOUT = 0x00000102

    def _write_console(s: str) -> None:
        try:
            out_handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            if out_handle in (0, -1):
                return
            written = wintypes.DWORD(0)
            kernel32.WriteConsoleW(out_handle, s, len(s), ctypes.byref(written), None)
        except Exception:  # noqa: BLE001
            pass

    def _fill_pending(timeout_ms: int = 50) -> None:
        if _windows_ctrl_c_peek():
            return
        rc = int(kernel32.WaitForSingleObject(handle, int(timeout_ms)))
        if rc == WAIT_TIMEOUT:
            return
        if rc != WAIT_OBJECT_0:
            return
        buf = (_INPUT_RECORD * 64)()
        nread = wintypes.DWORD(0)
        if not kernel32.ReadConsoleInputW(handle, buf, 64, ctypes.byref(nread)):
            return
        for i in range(int(nread.value)):
            rec = buf[i]
            if rec.EventType != KEY_EVENT:
                continue
            if not bool(rec.KeyEvent.bKeyDown):
                continue
            ch = str(rec.KeyEvent.uChar.UnicodeChar or "")
            if ch == "\x00":
                continue
            if ch == "":
                continue
            rep = int(rec.KeyEvent.wRepeatCount) or 1
            for _ in range(rep):
                _WIN_PENDING_CHARS.append(ch)

    def _next_char() -> str:
        while True:
            if _windows_ctrl_c_consume():
                raise KeyboardInterrupt
            if _WIN_PENDING_CHARS:
                return _WIN_PENDING_CHARS.popleft()
            _fill_pending(timeout_ms=50)

    def _read_line_raw() -> tuple[str, bool]:
        chars: list[str] = []
        is_paste = False
        in_bp = False
        esc: list[str] | None = None

        while True:
            ch = _next_char()
            if ch == "\x03":
                raise KeyboardInterrupt

            if esc is not None:
                esc.append(ch)
                seq = "".join(esc)

                if seq.startswith("\x1bO") and len(seq) >= 3:
                    # SS3 sequence (e.g. F1-F4)
                    esc = None
                    continue
                if seq.startswith("\x1b[") and len(seq) >= 3:
                    last = seq[-1]
                    if "@" <= last <= "~":
                        # CSI sequence. Keep only bracketed paste markers.
                        if seq == _BP_START:
                            is_paste = True
                            in_bp = True
                        elif seq == _BP_END:
                            in_bp = False
                        esc = None
                        continue
                if len(esc) > 64:
                    esc = None
                continue

            if ch == "\x1b":
                esc = ["\x1b"]
                continue

            if ch in ("\b", "\x7f"):
                if chars:
                    chars.pop()
                    _write_console("\b \b")
                continue

            if ch == "\r":
                if in_bp:
                    chars.append("\n")
                    _write_console("\n")
                    continue
                _write_console("\n")
                # Normalize CRLF: if we already have LF queued, drop it.
                if _WIN_PENDING_CHARS and _WIN_PENDING_CHARS[0] == "\n":
                    _WIN_PENDING_CHARS.popleft()
                return "".join(chars), is_paste
            if ch == "\n":
                if in_bp:
                    chars.append("\n")
                    _write_console("\n")
                    continue
                _write_console("\n")
                return "".join(chars), is_paste

            # Normal character.
            chars.append(ch)
            _write_console(ch)

    if paste_mode:
        lines: list[str] = []
        while True:
            line, _is_paste = _read_line_raw()
            s = line.strip()
            if s == "/end":
                break
            if line == "" and _is_paste:
                # Ignore marker-only lines (bracketed paste start/end).
                continue
            lines.append(line)
        return ReplTurn("\n".join(lines), is_paste=True, is_manual_paste=True)

    text, is_paste = _read_line_raw()
    if not is_paste:
        text = _VT_KEY_SEQ_RE.sub("", text)
    return ReplTurn(text, is_paste=is_paste)
