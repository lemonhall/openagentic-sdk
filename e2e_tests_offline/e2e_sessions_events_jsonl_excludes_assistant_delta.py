from __future__ import annotations

import json
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline


class _DeltaStreamingProvider:
    name = "offline-delta-stream"

    async def stream(self, *, model: str, input, **kwargs):  # noqa: A002
        _ = model, input, kwargs
        from openagentic_sdk.providers.stream_events import DoneEvent, TextDeltaEvent

        yield TextDeltaEvent(delta="E2E_OFFLINE_DELTA_")
        yield TextDeltaEvent(delta="NO_PERSIST_OK")
        yield DoneEvent(response_id="resp-delta-1", usage={"protocol": "offline"})


class TestE2EOfflineSessionsEventsJsonlExcludesAssistantDelta(unittest.IsolatedAsyncioTestCase):
    async def test_events_jsonl_does_not_persist_assistant_delta(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            opts0 = make_options_offline(root, provider=_DeltaStreamingProvider(), allowed_tools=[])
            opts = replace(opts0, include_partial_messages=True, resume=session_id, max_steps=6)

            saw_delta = False
            final_text = ""
            async for ev in openagentic_sdk.query(prompt="stream deltas", options=opts):
                if getattr(ev, "type", None) == "assistant.delta" and getattr(ev, "text_delta", ""):
                    saw_delta = True
                if getattr(ev, "type", None) == "result":
                    final_text = getattr(ev, "final_text", "") or ""

            self.assertTrue(saw_delta)
            self.assertIn("E2E_OFFLINE_DELTA_NO_PERSIST_OK", final_text)

            p = root / "sessions" / session_id / "events.jsonl"
            self.assertTrue(p.exists(), f"events.jsonl not found at: {p}")

            types: list[str] = []
            texts: list[str] = []
            for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if not raw.strip():
                    continue
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    continue
                t = obj.get("type")
                if isinstance(t, str):
                    types.append(t)
                txt = obj.get("text")
                if isinstance(txt, str):
                    texts.append(txt)
                ft = obj.get("final_text")
                if isinstance(ft, str):
                    texts.append(ft)

            self.assertNotIn("assistant.delta", types)
            self.assertTrue(
                any("E2E_OFFLINE_DELTA_NO_PERSIST_OK" in t for t in texts),
                "final assistant text missing from events.jsonl",
            )


if __name__ == "__main__":
    unittest.main()

