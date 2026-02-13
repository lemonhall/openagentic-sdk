from __future__ import annotations

import os
import unicodedata
from collections import deque
from collections.abc import Callable
from typing import TextIO

from .types import _BP_END, _BP_START, _VT_KEY_SEQ_RE, ReplTurn
from .win_ctrl_c import _install_windows_ctrl_c_handler, _windows_ctrl_c_consume, _windows_ctrl_c_peek

_WIN_RAW_ENABLED = False
_WIN_PENDING_CHARS: deque[str] = deque()


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
        _WIN_PENDING_CHARS.clear()

        def _restore() -> None:
            global _WIN_RAW_ENABLED
            try:
                kernel32.SetConsoleMode(handle, old_mode)
            except Exception:  # noqa: BLE001
                pass
            _WIN_RAW_ENABLED = False
            _WIN_PENDING_CHARS.clear()

        return _restore
    except Exception:  # noqa: BLE001
        return None


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
        return None

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

    def _cell_width(ch: str) -> int:
        if not ch:
            return 0
        if unicodedata.combining(ch):
            return 0
        # Treat fullwidth/wide as 2 console cells. This is a pragmatic fix for
        # CJK backspace rendering on Windows terminals.
        return 2 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1

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
        chars: list[tuple[str, int]] = []
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
                    _ch, w = chars.pop()
                    # If the last codepoint is a combining mark, delete the
                    # entire cluster (at least until a non-combining base).
                    while w == 0 and chars:
                        _ch, w = chars.pop()
                    w = max(1, int(w))
                    _write_console(("\b" * w) + (" " * w) + ("\b" * w))
                continue

            if ch == "\r":
                if in_bp:
                    chars.append(("\n", 0))
                    _write_console("\n")
                    continue
                _write_console("\n")
                # Normalize CRLF: if we already have LF queued, drop it.
                if _WIN_PENDING_CHARS and _WIN_PENDING_CHARS[0] == "\n":
                    _WIN_PENDING_CHARS.popleft()
                return "".join(c for c, _w in chars), is_paste
            if ch == "\n":
                if in_bp:
                    chars.append(("\n", 0))
                    _write_console("\n")
                    continue
                _write_console("\n")
                return "".join(c for c, _w in chars), is_paste

            # Normal character.
            chars.append((ch, _cell_width(ch)))
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
