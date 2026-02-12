from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.options import CompactionOptions

from e2e_tests._harness import make_options


class TestE2EFlowPruneThenResumeReadSmallRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_prune_then_resume_can_read_small_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            session_id = uuid.uuid4().hex
            big_token = f"BIG_{uuid.uuid4().hex}"
            small_token = f"SMALL_{uuid.uuid4().hex}"
            (root / "big.txt").write_text(("X" * 8000) + big_token + ("\n" + ("Y" * 8000)), encoding="utf-8")
            (root / "small.txt").write_text(small_token + "\n", encoding="utf-8")

            compaction = CompactionOptions(auto=False, prune=True, protect_tool_output_tokens=1, min_prune_tokens=1)
            opts0 = make_options(root, allowed_tools=["Read"])

            # Run 1: read big tool output.
            opts1 = replace(opts0, resume=session_id, compaction=compaction, max_steps=10)
            prompt1 = (
                "You MUST use tools.\n"
                "Step 1: Call Read on ./big.txt.\n"
                "Step 2: Reply with exactly: TURN1_OK\n"
            )
            r1 = await openagentic_sdk.run(prompt=prompt1, options=opts1)
            self.assertEqual((r1.final_text or "").strip(), "TURN1_OK")

            # Run 2/3: extra user turns (no tools).
            opts2 = replace(opts0, resume=session_id, compaction=compaction, max_steps=2)
            r2 = await openagentic_sdk.run(prompt="Reply with exactly: TURN2_OK (no tools).", options=opts2)
            self.assertIn("TURN2_OK", (r2.final_text or ""))
            opts3 = replace(opts0, resume=session_id, compaction=compaction, max_steps=2)
            r3 = await openagentic_sdk.run(prompt="Reply with exactly: TURN3_OK (no tools).", options=opts3)
            self.assertIn("TURN3_OK", (r3.final_text or ""))

            events_path = root / "sessions" / session_id / "events.jsonl"
            self.assertTrue(events_path.exists())
            text = events_path.read_text(encoding="utf-8", errors="replace")
            self.assertIn('"type":"tool.output_compacted"', text)

            # Run 4: still usable; read small and echo token.
            for attempt in range(4):
                opts4 = replace(opts0, resume=session_id, compaction=compaction, max_steps=10)
                prompt4 = (
                    "You MUST use tools.\n"
                    "Step 1: Call Read on ./small.txt.\n"
                    "Step 2: Reply with exactly the token you saw.\n"
                    "Do not add other text.\n"
                    f"(attempt={attempt + 1})\n"
                )
                r4 = await openagentic_sdk.run(prompt=prompt4, options=opts4)
                if small_token in (r4.final_text or ""):
                    return
            self.fail("after prune, resume read small.txt did not return token after 4 attempts")


if __name__ == "__main__":
    unittest.main()

