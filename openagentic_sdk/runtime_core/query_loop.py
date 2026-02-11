from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .query_loop_steps.mcp import close_mcp_clients, register_mcp_surface
from .query_loop_steps.orchestrator import run_query


class QueryLoopMixin:
    async def query(self, prompt: str) -> AsyncIterator[Any]:
        options = self._options
        mcp_clients, remote_mcp_clients = await register_mcp_surface(options)
        try:
            async for ev in run_query(self, prompt):
                yield ev
        finally:
            await close_mcp_clients(mcp_clients, remote_mcp_clients)

