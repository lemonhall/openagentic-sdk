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

    project_root = Path(ctx.project_dir) if isinstance(ctx.project_dir, str) and ctx.project_dir else Path(ctx.cwd)
    cwd = Path(ctx.cwd)

    # Windows gateways/providers sometimes emit POSIX-style absolute paths.
    # Handle these before going through Path(), because WindowsPath treats
    # '/x/y' as an anchored path without a drive (is_absolute() may be False),
    # which would discard `base` when joined.
    if os.name == "nt" and file_path.startswith("/"):
        posix = PurePosixPath(file_path)
        parts = posix.parts

        # WSL-style drive mounts: /mnt/c/Users/... -> C:\Users\...
        if len(parts) >= 4 and parts[1] == "mnt" and len(parts[2]) == 1 and parts[2].isalpha():
            drive = parts[2].upper() + ":"
            return _ensure_under_base(Path(drive) / Path(*parts[3:]), project_root)

        # Workspace-ish mounts used by some runners.
        for prefix in _POSIX_PREFIXES_TO_CWD:
            try:
                rel = posix.relative_to(prefix)
            except ValueError:
                continue
            return _ensure_under_base(project_root / Path(*rel.parts), project_root)

        # If the path is a single filename (e.g. /a.txt), map under base.
        if len(parts) == 2 and parts[0] == "/":
            return _ensure_under_base(project_root / parts[1], project_root)

        raise ValueError(f"Tool path must be under project root: {project_root.resolve()}")

    p = Path(file_path)
    if not p.is_absolute():
        # Relative paths resolve from the working directory, but must remain
        # under the project root.
        return _ensure_under_base(cwd / p, project_root)

    # Absolute paths are only allowed when they resolve under the project root.
    return _ensure_under_base(p, project_root)
