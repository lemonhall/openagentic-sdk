from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..errors import OpenAgentSdkError


@dataclass(frozen=True, slots=True)
class CorruptSessionLogError(OpenAgentSdkError, ValueError):
    session_id: str
    path: Path
    line: int | None = None
    reason: str | None = None

    def __str__(self) -> str:
        parts: list[str] = [f"Corrupt session log: {self.path} (session_id={self.session_id})"]
        if isinstance(self.line, int) and self.line > 0:
            parts.append(f"line={self.line}")
        if isinstance(self.reason, str) and self.reason.strip():
            parts.append(self.reason.strip())
        return " ".join(parts)

