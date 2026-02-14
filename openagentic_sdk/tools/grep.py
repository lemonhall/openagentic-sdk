from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .base import Tool, ToolContext
from .path_utils import resolve_tool_path


@dataclass(frozen=True, slots=True)
class GrepTool(Tool):
    name: str = "Grep"
    description: str = "Search file contents with a regex."
    max_matches: int = 5000

    async def run(self, tool_input: Mapping[str, Any], ctx: ToolContext) -> dict[str, Any]:
        query = tool_input.get("query")
        if not isinstance(query, str) or not query:
            raise ValueError("Grep: 'query' must be a non-empty string")
        file_glob = tool_input.get("file_glob", "**/*")
        if not isinstance(file_glob, str) or not file_glob:
            raise ValueError("Grep: 'file_glob' must be a non-empty string")

        root_in = tool_input.get("root", tool_input.get("path"))
        root = resolve_tool_path(str(root_in), ctx) if root_in is not None else resolve_tool_path(".", ctx)

        flags = 0 if tool_input.get("case_sensitive", True) else re.IGNORECASE
        rx = re.compile(query, flags=flags)

        mode = tool_input.get("mode", "content")
        if not isinstance(mode, str) or not mode:
            raise ValueError("Grep: 'mode' must be a string")

        before_n = tool_input.get("before_context", 0)
        after_n = tool_input.get("after_context", 0)
        if not isinstance(before_n, int) or before_n < 0:
            raise ValueError("Grep: 'before_context' must be a non-negative integer")
        if not isinstance(after_n, int) or after_n < 0:
            raise ValueError("Grep: 'after_context' must be a non-negative integer")

        matches: list[dict[str, Any]] = []
        files_with_matches: set[str] = set()
        for p in root.glob(file_glob):
            if not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = text.splitlines()
            for idx, line in enumerate(lines, start=1):
                if rx.search(line):
                    files_with_matches.add(str(p))
                    if mode == "files_with_matches":
                        continue
                    before_ctx = lines[max(0, idx - 1 - before_n) : idx - 1] if before_n else None
                    after_ctx = lines[idx : idx + after_n] if after_n else None
                    matches.append(
                        {
                            "file_path": str(p),
                            "line": idx,
                            "text": line,
                            "before_context": before_ctx,
                            "after_context": after_ctx,
                        }
                    )
                    if len(matches) >= self.max_matches:
                        return {"root": str(root), "query": query, "matches": matches, "truncated": True}

        if mode == "files_with_matches":
            files = sorted(files_with_matches)
            return {"root": str(root), "query": query, "files": files, "count": len(files)}

        return {"root": str(root), "query": query, "matches": matches, "truncated": False, "total_matches": len(matches)}
