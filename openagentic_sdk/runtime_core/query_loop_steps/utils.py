from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any


async def collect_events(source: AsyncIterator[Any]) -> list[Any]:
    out: list[Any] = []
    async for ev in source:
        out.append(ev)
    return out

