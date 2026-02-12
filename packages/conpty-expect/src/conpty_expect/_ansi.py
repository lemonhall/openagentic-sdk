from __future__ import annotations

import re

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def strip_ansi_with_index_map(s: str) -> tuple[str, list[int]]:
    """
    Strip ANSI CSI sequences and return an index map.

    Returns:
      (stripped, index_map)

    Where:
      - stripped is s with ANSI escape sequences removed
      - index_map is a list of length len(stripped)+1
        such that index_map[k] is the corresponding index in the original
        string after consuming k characters of stripped.

    This lets callers translate match spans from stripped text back to the
    original buffer indices for correct consumption.
    """
    out: list[str] = []
    index_map: list[int] = [0]

    cursor = 0
    for m in _ANSI_RE.finditer(s):
        a, b = m.span()
        if a > cursor:
            seg = s[cursor:a]
            out.append(seg)
            for i in range(cursor, a):
                index_map.append(i + 1)
        cursor = b

    if cursor < len(s):
        out.append(s[cursor:])
        for i in range(cursor, len(s)):
            index_map.append(i + 1)

    return ("".join(out), index_map)
