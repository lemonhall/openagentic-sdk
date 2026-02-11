from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from .base import ToolContext


def coerce_non_empty_str(v: object | None) -> str | None:
    if not isinstance(v, str):
        return None
    s = v.strip()
    return s if s else None


_POSIX_PREFIXES_TO_CWD: tuple[PurePosixPath, ...] = (
    PurePosixPath("/mnt/data"),
    PurePosixPath("/mnt/workspace"),
    PurePosixPath("/workspace"),
    PurePosixPath("/home/sandbox"),
    PurePosixPath("/root"),
)

def _is_relative_to(p: Path, base: Path) -> bool:
    try:
        return p.is_relative_to(base)  # py3.9+
    except AttributeError:  # pragma: no cover
        try:
            p.relative_to(base)
            return True
        except ValueError:
            return False


def _ensure_under_base(p: Path, base: Path) -> Path:
    base2 = base.resolve()
    p2 = p.resolve()
    if not _is_relative_to(p2, base2):
        raise ValueError(f"Tool path must be under project root: {base2}")
    return p2


def resolve_tool_path(file_path: str, ctx: ToolContext) -> Path:
    """Resolve a tool file path against the runtime context.

    - Relative paths are resolved under `ctx.cwd`.
    - On Windows, models/providers sometimes emit POSIX-like absolute paths
      (e.g. `/mnt/data/a.txt`). Apply a conservative mapping:
        - `/mnt/<drive>/<...>` -> `<DRIVE>:\\...`
        - known sandbox/workspace prefixes -> `ctx.cwd / <relative>`
      Unknown POSIX absolute paths fall back to `Path(file_path)` (no generic
      basename fallback).
    """

    base = Path(ctx.project_dir) if isinstance(ctx.project_dir, str) and ctx.project_dir else Path(ctx.cwd)

    p = Path(file_path)
    if not p.is_absolute():
        return _ensure_under_base(base / p, base)

    if os.name != "nt" or not file_path.startswith("/"):
        return p

    posix = PurePosixPath(file_path)
    parts = posix.parts

    if len(parts) >= 4 and parts[1] == "mnt" and len(parts[2]) == 1 and parts[2].isalpha():
        drive = parts[2].upper() + ":"
        return Path(drive) / Path(*parts[3:])

    for prefix in _POSIX_PREFIXES_TO_CWD:
        try:
            rel = posix.relative_to(prefix)
        except ValueError:
            continue
        return _ensure_under_base(base / Path(*rel.parts), base)

    return p
