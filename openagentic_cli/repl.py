from __future__ import annotations

from typing import TextIO

from openagentic_sdk.options import OpenAgenticOptions

from .repl_chat import run_chat_impl as _run_chat_impl
from .repl_commands import parse_repl_command
from .repl_input import (
    ReplTurn,
    _BP_DISABLE,
    _BP_ENABLE,
    _disable_posix_echoctl,
    _enable_windows_vt_input,
    read_repl_turn,
)
from .style import StyleConfig


async def run_chat(
    options: OpenAgenticOptions,
    *,
    color_config: StyleConfig,
    debug: bool,
    stdin: TextIO,
    stdout: TextIO,
) -> int:
    return await _run_chat_impl(
        options,
        color_config=color_config,
        debug=debug,
        stdin=stdin,
        stdout=stdout,
        read_turn=read_repl_turn,
        parse_command=parse_repl_command,
        disable_posix_echoctl=_disable_posix_echoctl,
        enable_windows_vt_input=_enable_windows_vt_input,
        bp_enable=_BP_ENABLE,
        bp_disable=_BP_DISABLE,
    )

