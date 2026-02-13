from __future__ import annotations

import re
from dataclasses import dataclass

_BP_ENABLE = "\x1b[?2004h"
_BP_DISABLE = "\x1b[?2004l"
_BP_START = "\x1b[200~"
_BP_END = "\x1b[201~"


@dataclass(frozen=True, slots=True)
class ReplTurn:
    text: str
    is_paste: bool
    is_manual_paste: bool = False


_VT_KEY_SEQ_RE = re.compile(r"(?:\x1b\[[0-9;?]*[A-Za-z~]|\x1bO[PFQRS])")


def _strip_bracketed_paste_markers(s: str) -> str:
    # Terminals wrap pasted content in these escape sequences when bracketed
    # paste mode is enabled.
    return s.replace(_BP_START, "").replace(_BP_END, "")

