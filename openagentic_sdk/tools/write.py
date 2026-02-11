from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .base import Tool, ToolContext
from .path_utils import coerce_non_empty_str, resolve_tool_path


@dataclass(frozen=True, slots=True)
class WriteTool(Tool):
    name: str = "Write"
    description: str = "Create or overwrite a file."

    async def run(self, tool_input: Mapping[str, Any], ctx: ToolContext) -> dict[str, Any]:
        file_path = coerce_non_empty_str(tool_input.get("file_path")) or coerce_non_empty_str(tool_input.get("filePath"))
        content = tool_input.get("content")
        overwrite = bool(tool_input.get("overwrite", False))

        if not isinstance(file_path, str) or not file_path:
            raise ValueError("Write: 'file_path' must be a non-empty string")
        if not isinstance(content, str):
            raise ValueError("Write: 'content' must be a string")

        p = resolve_tool_path(file_path, ctx)
        p.parent.mkdir(parents=True, exist_ok=True)

        if p.exists() and not overwrite:
            raise FileExistsError(f"Write: file exists: {p}")

        tmp = p.with_name(f".{p.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(p)
        finally:
            if tmp.exists():
                tmp.unlink()
        bytes_written = len(content.encode("utf-8"))
        return {
            "message": f"Wrote {bytes_written} bytes",
            "file_path": str(p),
            "bytes_written": bytes_written,
        }
