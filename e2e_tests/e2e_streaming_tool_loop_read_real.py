from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.message_query import query_messages
from openagentic_sdk.messages import AssistantMessage, ResultMessage, StreamEvent, ToolResultBlock, ToolUseBlock

from e2e_tests._harness import make_options


class TestE2EStreamingToolLoopReadReal(unittest.IsolatedAsyncioTestCase):
    async def test_streaming_includes_deltas_and_tool_blocks(self) -> None:
        # Real-network tests can be flaky when relying on the model to follow
        # streaming + tool instructions. Allow a few attempts before failing.
        for attempt in range(3):
            with TemporaryDirectory() as td:
                root = Path(td)
                token = f"STREAM_TOKEN_{uuid.uuid4().hex}"
                (root / "a.txt").write_text(f"token:{token}\n", encoding="utf-8")

                opts0 = make_options(root, allowed_tools=["Read"])
                opts = replace(opts0, include_partial_messages=True, max_steps=10)
                prompt = (
                    "Output exactly the single word PREFACE first.\n"
                    "Then call the Read tool on ./a.txt.\n"
                    "After receiving the tool result, reply with exactly: STREAM_TOOL_OK.\n"
                    "Do not guess.\n"
                    f"(attempt={attempt + 1})\n"
                )

                saw_delta = False
                saw_tool_use = False
                saw_tool_result = False
                saw_token_in_tool_result = False
                saw_result = False

                async for msg in query_messages(prompt=prompt, options=opts):
                    if isinstance(msg, StreamEvent) and msg.event.get("type") == "text_delta":
                        saw_delta = True
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, ToolUseBlock) and block.name == "Read":
                                saw_tool_use = True
                            if isinstance(block, ToolResultBlock) and block.tool_use_id and block.is_error is False:
                                saw_tool_result = True
                                if isinstance(block.content, str) and token in block.content:
                                    saw_token_in_tool_result = True
                    if isinstance(msg, ResultMessage):
                        saw_result = True

                if saw_delta and saw_tool_use and saw_tool_result and saw_token_in_tool_result and saw_result:
                    return

        self.fail("streaming+tool blocks did not appear after 3 attempts")


if __name__ == "__main__":
    unittest.main()
