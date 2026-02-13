from __future__ import annotations

import json
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2ESessionsEventsSeqMonotonicRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_events_jsonl_seq_monotonic(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            token = f"SEQ_TOKEN_{uuid.uuid4().hex}"
            p = root / "x.txt"

            opts0 = make_options(root, allowed_tools=["Write"])
            opts = replace(opts0, resume=session_id, max_steps=10)
            await openagentic_sdk.run(
                prompt="Write ./x.txt with content: " + token + "\nReply with exactly: OK\n",
                options=opts,
            )
            await openagentic_sdk.run(prompt="Write ./x.txt with content: " + token + "\nReply OK\n", options=opts)

            events_path = root / "sessions" / session_id / "events.jsonl"
            self.assertTrue(events_path.exists())
            self.assertTrue(p.exists())

            seqs: list[int] = []
            for raw in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not raw.strip():
                    continue
                obj = json.loads(raw)
                if isinstance(obj, dict) and isinstance(obj.get("seq"), int):
                    seqs.append(int(obj["seq"]))
            self.assertTrue(seqs)
            self.assertEqual(seqs, sorted(seqs))
            self.assertEqual(len(seqs), len(set(seqs)))
            self.assertGreaterEqual(min(seqs), 1)


if __name__ == "__main__":
    unittest.main()

