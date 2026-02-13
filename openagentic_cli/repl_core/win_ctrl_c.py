from __future__ import annotations

import os
from collections.abc import Callable
from typing import Final

_WIN_CTRL_C_HANDLER_INSTALLED: bool = False
_WIN_CTRL_C_HANDLER = None
_WIN_CTRL_C_PRESSED = None

_CTRL_C_EVENT: Final[int] = 0
_CTRL_BREAK_EVENT: Final[int] = 1


def _install_windows_ctrl_c_handler() -> None:
    """Install a Windows Ctrl+C handler that can be polled from anywhere.

    This is used to interrupt in-flight streaming even when we're not actively
    reading from stdin (e.g., during model output).
    """

    global _WIN_CTRL_C_HANDLER_INSTALLED, _WIN_CTRL_C_HANDLER, _WIN_CTRL_C_PRESSED

    if os.name != "nt":
        return
    if _WIN_CTRL_C_HANDLER_INSTALLED:
        return

    import ctypes
    import threading
    from ctypes import wintypes

    _WIN_CTRL_C_PRESSED = threading.Event()
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    HANDLER = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def _handler(ctrl_type: int) -> int:
        if ctrl_type in (_CTRL_C_EVENT, _CTRL_BREAK_EVENT):
            assert _WIN_CTRL_C_PRESSED is not None
            _WIN_CTRL_C_PRESSED.set()
            return 1
        return 0

    _WIN_CTRL_C_HANDLER = HANDLER(_handler)
    kernel32.SetConsoleCtrlHandler(_WIN_CTRL_C_HANDLER, True)
    _WIN_CTRL_C_HANDLER_INSTALLED = True


def _windows_ctrl_c_peek() -> bool:
    if os.name != "nt":
        return False
    if _WIN_CTRL_C_PRESSED is None:
        return False
    return bool(_WIN_CTRL_C_PRESSED.is_set())


def _windows_ctrl_c_consume() -> bool:
    if os.name != "nt":
        return False
    if _WIN_CTRL_C_PRESSED is None:
        return False
    if _WIN_CTRL_C_PRESSED.is_set():
        _WIN_CTRL_C_PRESSED.clear()
        return True
    return False


def _disable_windows_processed_input(stdin) -> Callable[[], None] | None:
    """Best-effort: disable ENABLE_PROCESSED_INPUT on Windows consoles.

    This prevents Ctrl+C from terminating the process when sent through ConPTY
    as `\\x03`, allowing the app to handle it as an interactive keybinding.
    """

    if os.name != "nt":
        return None
    if not bool(getattr(stdin, "isatty", lambda: False)()):
        return None
    if not hasattr(stdin, "fileno"):
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
        enable_processed = 0x0001  # ENABLE_PROCESSED_INPUT
        new_mode = old_mode & ~enable_processed
        if new_mode == old_mode:
            return lambda: None
        if not kernel32.SetConsoleMode(handle, new_mode):
            return None

        def _restore() -> None:
            try:
                kernel32.SetConsoleMode(handle, old_mode)
            except Exception:  # noqa: BLE001
                pass

        return _restore
    except Exception:  # noqa: BLE001
        return None
