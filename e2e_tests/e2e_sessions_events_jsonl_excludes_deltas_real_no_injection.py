from __future__ import annotations

import json
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2ESessionsEventsJsonlExcludesDeltasRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_events_jsonl_does_not_persist_assistant_delta(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            token = f"E2E_NO_DELTA_PERSIST_OK_{uuid.uuid4().hex}_END"
            opts0 = make_options(root, allowed_tools=[])
            opts = replace(opts0, include_partial_messages=True, resume=session_id, max_steps=10)

            saw_delta = False
            async for ev in openagentic_sdk.query(prompt=f"Reply with exactly: {token}", options=opts):
                if getattr(ev, "type", None) == "assistant.delta" and getattr(ev, "text_delta", ""):
                    saw_delta = True
            self.assertTrue(saw_delta)

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
            self.assertTrue(any(token in t for t in texts), "final assistant text missing from events.jsonl")


if __name__ == "__main__":
    unittest.main()

