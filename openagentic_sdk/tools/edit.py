from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .base import Tool, ToolContext


@dataclass(frozen=True, slots=True)
class EditTool(Tool):
    name: str = "Edit"
    description: str = "Apply a precise edit (string replace) to a file."

    async def run(self, tool_input: Mapping[str, Any], ctx: ToolContext) -> dict[str, Any]:
        file_path = tool_input.get("file_path", tool_input.get("filePath"))
        old = tool_input.get("old", tool_input.get("old_string", tool_input.get("oldString")))
        new = tool_input.get("new", tool_input.get("new_string", tool_input.get("newString")))
        replace_all = tool_input.get("replace_all", tool_input.get("replaceAll"))
        count = tool_input.get("count", 1 if not replace_all else 0)
        before = tool_input.get("before")
        after = tool_input.get("after")

        # Models/providers sometimes emit empty-string context anchors. Treat them as "not provided".
        if isinstance(before, str) and before.strip() == "":
            before = None
        if isinstance(after, str) and after.strip() == "":
            after = None

        if not isinstance(file_path, str) or not file_path:
            raise ValueError("Edit: 'file_path' must be a non-empty string")
        if not isinstance(old, str) or old == "":
            raise ValueError("Edit: 'old' must be a non-empty string")
        if not isinstance(new, str):
            raise ValueError("Edit: 'new' must be a string")
        if not isinstance(count, int) or count < 0:
            raise ValueError("Edit: 'count' must be a non-negative integer")
        if before is not None and not isinstance(before, str):
            raise ValueError("Edit: 'before' must be a string")
        if after is not None and not isinstance(after, str):
            raise ValueError("Edit: 'after' must be a string")

        p = Path(file_path)
        if not p.is_absolute():
            p = Path(ctx.cwd) / p

        text = p.read_text(encoding="utf-8", errors="replace")
        if old not in text:
            raise ValueError("Edit: 'old' text not found in file")

        if before is not None or after is not None:
            idx_old = text.find(old)
            idx_before = text.find(before) if isinstance(before, str) else -1
            idx_after = text.find(after) if isinstance(after, str) else -1
            if before is not None and idx_before < 0:
                raise ValueError("Edit: 'before' anchor not found in file")
            if after is not None and idx_after < 0:
                raise ValueError("Edit: 'after' anchor not found in file")
            if before is not None and idx_before >= idx_old:
                raise ValueError("Edit: 'before' must appear before 'old'")
            if after is not None and idx_old >= idx_after:
                raise ValueError("Edit: 'after' must appear after 'old'")

        replaced = text.replace(old, new, count) if count != 0 else text.replace(old, new)
        p.write_text(replaced, encoding="utf-8")
        replacements = text.count(old) if count == 0 else min(text.count(old), count)
        return {
            "message": "Edit applied",
            "file_path": str(p),
            "replacements": replacements,
        }
