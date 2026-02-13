from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from openagentic_sdk.options import CompactionOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.sessions.store import FileSessionStore


class _LegacyCompactionProvider:
    name = "offline-legacy-compaction"

    def __init__(self) -> None:
        self._n = 0

    async def complete(self, *, model: str, messages, tools=(), api_key=None):  # noqa: ANN001
        _ = model, tools, api_key
        from openagentic_sdk.compaction import COMPACTION_SYSTEM_PROMPT
        from openagentic_sdk.providers.base import ModelOutput

        self._n += 1
        msgs = list(messages)
        sys0 = msgs[0].get("content") if msgs and isinstance(msgs[0], dict) else ""

        # Compaction pass call.
        if isinstance(sys0, str) and sys0.strip() == COMPACTION_SYSTEM_PROMPT.strip():
            return ModelOutput(assistant_text="OFFLINE_SUMMARY", tool_calls=(), usage={"total_tokens": 1})

        # First normal call: force overflow by usage totals (boundary >=).
        if self._n == 1:
            return ModelOutput(assistant_text="first", tool_calls=(), usage={"total_tokens": 90})

        # After compaction, runtime prompts: "Continue if you have next steps"
        return ModelOutput(assistant_text="E2E_OFFLINE_COMPACTION_OK", tool_calls=(), usage={"total_tokens": 1})


class TestE2EOfflineCompactionOverflowLegacy(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_overflow_triggers_compaction_and_continues(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root / "sessions")
            provider = _LegacyCompactionProvider()

            # Make overflow math deterministic and reachable in tests.
            compaction = CompactionOptions(
                auto=True,
                prune=False,
                context_limit=100,
                output_limit=20,
                global_output_cap=20,
                reserved=10,
            )

            from openagentic_sdk.options import OpenAgenticOptions

            opts = OpenAgenticOptions(
                provider=provider,
                model="fake",
                api_key="offline",
                cwd=str(root),
                project_dir=str(root),
                session_store=store,
                permission_gate=PermissionGate(permission_mode="bypass"),
                allowed_tools=[],
                compaction=compaction,
            )
            opts = replace(opts, max_steps=10)

            r = await openagentic_sdk.run(prompt="trigger overflow", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_COMPACTION_OK")
            self.assertTrue(any(getattr(e, "type", "") == "user.compaction" for e in r.events))
            self.assertTrue(any(getattr(e, "type", "") == "assistant.message" and bool(getattr(e, "is_summary", False)) for e in r.events))


if __name__ == "__main__":
    unittest.main()

