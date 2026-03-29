import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.tools.registry import ToolRegistry
from openagentic_sdk.tools.web_fetch import WebFetchTool


class WebFetchPromptProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = (model, tools, api_key)
        self.calls += 1
        if self.calls == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="call_1",
                        name="WebFetch",
                        arguments={"url": "https://example.com", "prompt": "Summarize"},
                    )
                ],
            )
        if self.calls == 2:
            # Internal summarization call triggered by runtime.
            return ModelOutput(assistant_text="SUMMARY", tool_calls=[])

        tool_msg = next(m for m in messages if m.get("role") == "tool")
        data = json.loads(tool_msg.get("content") or "{}")
        return ModelOutput(assistant_text=f"final:{data.get('response')}", tool_calls=[])


class TestWebFetchPrompt(unittest.IsolatedAsyncioTestCase):
    async def test_web_fetch_prompt_generates_response(self) -> None:
        os.environ["TAVILY_API_KEY"] = "test"

        def extract_transport(url, headers, payload):
            _ = (url, headers, payload)
            return {"results": [{"url": "https://example.com", "raw_content": "hello world"}]}

        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)
            tools = ToolRegistry([WebFetchTool(extract_transport=extract_transport, allow_private_networks=True)])
            options = OpenAgenticOptions(
                provider=WebFetchPromptProvider(),
                model="m",
                api_key="x",
                cwd=str(root),
                session_store=store,
                tools=tools,
                allowed_tools=["WebFetch"],
                permission_gate=PermissionGate(permission_mode="bypass"),
            )
            import openagentic_sdk

            r = await openagentic_sdk.run(prompt="hi", options=options)
            self.assertEqual(r.final_text, "final:SUMMARY")


if __name__ == "__main__":
    unittest.main()
