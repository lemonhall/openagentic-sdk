from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .base import Tool, ToolContext
from .path_utils import coerce_non_empty_str, resolve_tool_path


_IGNORE_PREFIXES = (
    "node_modules",
    "__pycache__",
    ".git",
    "dist",
    "build",
    "target",
    "vendor",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "env",
    ".cache",
    "coverage",
    "tmp",
    "temp",
)


def _should_ignore(rel_parts: tuple[str, ...]) -> bool:
    return any(p in _IGNORE_PREFIXES for p in rel_parts)


@dataclass(frozen=True, slots=True)
class ListTool(Tool):
    """List files under a directory.

    OpenCode's `list` tool is used when a prompt contains `@dir` references.
    We implement a small, deterministic subset: tree render of up to `limit`
    files, skipping common junk directories.
    """

    name: str = "List"
    description: str = "List files under a directory."
    limit: int = 100

    async def run(self, tool_input: Mapping[str, Any], ctx: ToolContext) -> dict[str, Any]:
        raw = tool_input.get("path")
        if raw is None:
            raw = tool_input.get("dir")
        if raw is None:
            raw = tool_input.get("directory")
        path = coerce_non_empty_str(raw)
        if path is None:
            raise ValueError("List: 'path' must be a non-empty string")

        base = resolve_tool_path(path, ctx)

        if not base.exists() or not base.is_dir():
            raise FileNotFoundError(f"List: not a directory: {base}")

        files: list[Path] = []
        for root, dirs, filenames in os.walk(base):
            root_p = Path(root)
            try:
                rel_root = root_p.relative_to(base)
            except Exception:  # noqa: BLE001
                rel_root = Path(".")
            rel_parts = tuple(rel_root.parts)
            if _should_ignore(rel_parts):
                dirs[:] = []
                continue
            dirs[:] = sorted(dirs)
            filenames = sorted(filenames)
            for fn in filenames:
                p = root_p / fn
                try:
                    rel = p.relative_to(base)
                except Exception:  # noqa: BLE001
                    continue
                if _should_ignore(tuple(rel.parts)):
                    continue
                files.append(rel)
                if len(files) >= int(self.limit):
                    dirs[:] = []
                    break
            if len(files) >= int(self.limit):
                break

        # Build a simple tree structure.
        dirs_set: set[tuple[str, ...]] = {()}
        files_by_dir: dict[tuple[str, ...], list[str]] = {}
        for rel in files:
            dir_parts = tuple(rel.parts[:-1])
            for i in range(len(dir_parts) + 1):
                dirs_set.add(dir_parts[:i])
            files_by_dir.setdefault(dir_parts, []).append(rel.parts[-1])

        def render_dir(prefix: tuple[str, ...], depth: int) -> str:
            indent = "  " * depth
            out = ""
            if depth > 0 and prefix:
                out += f"{indent}{prefix[-1]}/\n"

            children = sorted([d for d in dirs_set if len(d) == len(prefix) + 1 and d[: len(prefix)] == prefix])
            for child in children:
                out += render_dir(child, depth + 1)

            child_indent = "  " * (depth + 1)
            for fn in sorted(files_by_dir.get(prefix, [])):
                out += f"{child_indent}{fn}\n"
            return out

        output = str(base) + "/\n" + render_dir((), 0)
        return {
            "path": str(base),
            "count": len(files),
            "truncated": len(files) >= int(self.limit),
            "output": output,
        }
