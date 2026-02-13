from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass


def _truthy_env(name: str) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return v in {"1", "true", "yes", "on"}


@dataclass
class DebugTimeline:
    enabled: bool
    path: str | None
    lines: deque[str]

    @classmethod
    def from_env(cls) -> "DebugTimeline":
        enabled = _truthy_env("CONPTY_EXPECT_DEBUG")
        path = os.environ.get("CONPTY_EXPECT_DEBUG_PATH", "").strip() or None
        return cls(enabled=enabled, path=path, lines=deque(maxlen=200))

    def add(self, msg: str) -> None:
        if not self.enabled:
            return
        line = f"{time.time():.6f} {msg}"
        self.lines.append(line)
        if self.path:
            try:
                with open(self.path, "a", encoding="utf-8", errors="replace") as f:
                    f.write(line + "\n")
            except Exception:
                pass

    def dump(self) -> str:
        if not self.enabled:
            return ""
        return "\n".join(self.lines)

