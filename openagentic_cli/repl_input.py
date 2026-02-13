from __future__ import annotations

from collections.abc import Callable
from typing import TextIO

from .repl_core.input import _disable_posix_echoctl, read_repl_turn
from .repl_core.types import _BP_DISABLE, _BP_ENABLE, _BP_END, _BP_START, ReplTurn
from .repl_core.win_raw import _enable_windows_vt_input, _windows_ctrl_c_consume

__all__ = [
    "ReplTurn",
    "read_repl_turn",
    "_disable_posix_echoctl",
    "_enable_windows_vt_input",
    "_windows_ctrl_c_consume",
    "_BP_ENABLE",
    "_BP_DISABLE",
    "_BP_START",
    "_BP_END",
]

