import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.message_query import query_messages
from openagentic_sdk.messages import AssistantMessage, ResultMessage, ToolResultBlock, ToolUseBlock
from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.tools.read import ReadTool
from openagentic_sdk.tools.registry import ToolRegistry


class _ToolLoopProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def complete(
        self,
        *,
        model,  # noqa: ANN001
        input,  # noqa: ANN001
        tools=(),
        api_key=None,
        previous_response_id=None,
        store=True,
        include=(),
    ):
        _ = (model, tools, api_key, store, include)
        items = list(input)
        self.calls.append(items)

        if previous_response_id is None:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[ToolCall(tool_use_id="call_1", name="Read", arguments={"file_path": "a.txt"})],
                response_id="resp_1",
            )

        tool_item = next(i for i in items if isinstance(i, dict) and i.get("type") == "function_call_output")
        data = json.loads(tool_item.get("output") or "{}")
        return ModelOutput(
            assistant_text=f"OK: {data.get('content','')}",
            tool_calls=[],
            response_id="resp_2",
        )


class TestQueryMessagesToolLoopBlocks(unittest.IsolatedAsyncioTestCase):
    async def test_query_messages_emits_tool_use_and_tool_result_blocks(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.txt").write_text("hello", encoding="utf-8")

            store = FileSessionStore(root_dir=root / "sessions")
            tools = ToolRegistry([ReadTool()])
            provider = _ToolLoopProvider()
            options = OpenAgenticOptions(
                provider=provider,
                model="fake",
                api_key="x",
                cwd=str(root),
                tools=tools,
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
            )

            out = []
            async for m in query_messages(prompt="read file", options=options):
                out.append(m)

            tool_uses = [
                b
                for m in out
                if isinstance(m, AssistantMessage)
                for b in (m.content or [])
                if isinstance(b, ToolUseBlock) and b.name == "Read"
            ]
            self.assertTrue(tool_uses)

            tool_results = [
                b
                for m in out
                if isinstance(m, AssistantMessage)
                for b in (m.content or [])
                if isinstance(b, ToolResultBlock) and (b.content or "").find("hello") >= 0
            ]
            self.assertTrue(tool_results)

            self.assertTrue(any(isinstance(m, ResultMessage) and (m.result or "").find("OK: hello") >= 0 for m in out))


if __name__ == "__main__":
    unittest.main()

