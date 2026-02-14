from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .base import Tool, ToolContext
from .path_utils import coerce_non_empty_str, resolve_tool_path


@dataclass(frozen=True, slots=True)
class ReadTool(Tool):
    name: str = "Read"
    description: str = "Read a file from disk."
    max_bytes: int = 1024 * 1024

    async def run(self, tool_input: Mapping[str, Any], ctx: ToolContext) -> dict[str, Any]:
        file_path = coerce_non_empty_str(tool_input.get("file_path")) or coerce_non_empty_str(tool_input.get("filePath"))
        if not isinstance(file_path, str) or not file_path:
            raise ValueError("Read: 'file_path' must be a non-empty string")

        p = resolve_tool_path(file_path, ctx)

        offset_raw = tool_input.get("offset")
        limit_raw = tool_input.get("limit")

        def _coerce_int(v: Any, *, name: str) -> int | None:
            if v is None:
                return None
            if isinstance(v, bool):
                raise ValueError(f"Read: '{name}' must be an integer")
            if isinstance(v, int):
                return v
            if isinstance(v, str):
                s = v.strip()
                if not s:
                    return None
                try:
                    return int(s)
                except ValueError as e:
                    raise ValueError(f"Read: '{name}' must be an integer") from e
            raise ValueError(f"Read: '{name}' must be an integer")

        offset = _coerce_int(offset_raw, name="offset")
        limit = _coerce_int(limit_raw, name="limit")
        if offset == 0:
            # Models sometimes pass 0 when they mean "from the start".
            offset = 1
        if offset is not None and (not isinstance(offset, int) or offset < 1):
            raise ValueError("Read: 'offset' must be a positive integer (1-based)")
        if limit is not None and (not isinstance(limit, int) or limit < 0):
            raise ValueError("Read: 'limit' must be a non-negative integer")

        full_data = p.read_bytes()
        truncated = len(full_data) > self.max_bytes
        data = full_data[: self.max_bytes] if truncated else full_data

        # Image mode (best-effort): return base64 for common image types.
        suffix = p.suffix.lower()
        if suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }.get(suffix, "application/octet-stream")
            return {
                "file_path": str(p),
                "image": base64.b64encode(data).decode("ascii"),
                "mime_type": mime,
                "file_size": len(data),
                "truncated": truncated,
            }

        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()

        # CAS compatibility: if offset/limit is provided, return line-numbered content.
        if offset is not None or limit is not None:
            start = (offset - 1) if isinstance(offset, int) else 0
            end = start + limit if isinstance(limit, int) else len(lines)
            slice_lines = lines[start:end]
            numbered = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(slice_lines, start=start))
            return {
                "file_path": str(p),
                "content": numbered,
                "total_lines": len(lines),
                "lines_returned": len(slice_lines),
                "truncated": truncated,
            }

        return {"file_path": str(p), "content": text, "truncated": truncated}
