from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options


class TestE2ESessionsTranscriptRedactionReal(unittest.IsolatedAsyncioTestCase):
    async def test_events_include_tool_output_but_transcript_excludes_it(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"TOOL_OUTPUT_TOKEN_{uuid.uuid4().hex}"
            (root / "secret.txt").write_text(f"secret:{token}\n", encoding="utf-8")

            stage = 0

            async def inject_read_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_read_secret",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "./secret.txt"})
                            ],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                if stage == 1:
                    stage = 2
                    return HookDecision(
                        action="inject_final_text",
                        override_tool_output=ModelOutput(
                            assistant_text="SESSION_REDACTION_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-read-secret", tool_name_pattern="*", hook=inject_read_then_finish)])
            opts0 = make_options(root, allowed_tools=["Read"], hooks=hooks)
            opts = replace(opts0, max_steps=5)

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt="Read the secret file.", options=opts):
                events.append(ev)

            session_ids = [getattr(e, "session_id", "") for e in events if getattr(e, "type", None) == "result"]
            self.assertTrue(session_ids)
            session_id = session_ids[-1]
            self.assertTrue(session_id)

            events_p = root / "sessions" / session_id / "events.jsonl"
            transcript_p = root / "sessions" / session_id / "transcript.jsonl"
            self.assertTrue(events_p.exists())
            self.assertTrue(transcript_p.exists())

            events_text = events_p.read_text(encoding="utf-8", errors="replace")
            transcript_text = transcript_p.read_text(encoding="utf-8", errors="replace")

            self.assertIn(token, events_text)
            self.assertNotIn(token, transcript_text)
            self.assertIn("SESSION_REDACTION_OK", transcript_text)


if __name__ == "__main__":
    unittest.main()

