from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.sessions.errors import CorruptSessionLogError

from e2e_tests._harness import make_options


class TestE2EFlowResumeCorruptEventsLogFailsClearlyRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_resume_with_corrupt_events_log_fails_clearly(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex

            # Run 1: create a session with a normal turn.
            opts0 = make_options(root, allowed_tools=[])
            opts1 = replace(opts0, resume=session_id, max_steps=6)
            r1 = await openagentic_sdk.run(prompt="Say: TURN1_OK", options=opts1)
            self.assertIn("TURN1_OK", r1.final_text or "")

            events_path = root / "sessions" / session_id / "events.jsonl"
            self.assertTrue(events_path.exists())

            # Corrupt the log by appending a truncated JSON object.
            with events_path.open("a", encoding="utf-8") as f:
                f.write('{"type": "user.message", "text": "corrupt"\n')

            # Run 2: resume must fail fast with a clear, locatable error.
            opts2 = replace(opts0, resume=session_id, max_steps=6)
            with self.assertRaises(CorruptSessionLogError) as ctx:
                await openagentic_sdk.run(prompt="Say: TURN2_SHOULD_NOT_RUN", options=opts2)

            msg = str(ctx.exception)
            self.assertIn("events.jsonl", msg)
            self.assertIn(f"session_id={session_id}", msg)
            self.assertIn("line=", msg)


if __name__ == "__main__":
    unittest.main()

