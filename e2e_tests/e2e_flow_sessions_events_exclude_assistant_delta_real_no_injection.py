from __future__ import annotations

import json
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EFlowSessionsEventsExcludeAssistantDeltaRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_events_jsonl_never_persists_assistant_delta(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex

            opts0 = make_options(root, allowed_tools=[])
            opts = replace(opts0, resume=session_id, include_partial_messages=True, max_steps=6)
            prompt = (
                "Write a short paragraph (at least 80 words).\n"
                "Do not use any tools.\n"
                "End with exactly: DELTA_DONE\n"
            )

            r = await openagentic_sdk.run(prompt=prompt, options=opts)

            saw_delta_in_memory = any(getattr(e, "type", None) == "assistant.delta" for e in r.events)
            self.assertTrue(saw_delta_in_memory)

            events_path = root / "sessions" / session_id / "events.jsonl"
            self.assertTrue(events_path.exists())
            raw = events_path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("assistant.delta", raw)
            self.assertNotIn("text_delta", raw)

            for line in raw.splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                self.assertNotEqual(obj.get("type"), "assistant.delta")

            self.assertTrue((r.final_text or "").strip().endswith("DELTA_DONE"))


if __name__ == "__main__":
    unittest.main()

