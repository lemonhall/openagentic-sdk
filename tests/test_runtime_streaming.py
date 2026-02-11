import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.sessions.store import FileSessionStore


class FakeStreamingProvider:
    name = "fake-stream"

    async def stream(self, *, model, input, tools=(), api_key=None, previous_response_id=None, store=True):
        _ = (model, input, tools, api_key, previous_response_id, store)
        yield {"type": "text_delta", "delta": "he"}
        yield {"type": "text_delta", "delta": "llo"}
        yield {"type": "done", "response_id": "resp_1", "usage": {"total_tokens": 3}}


class TestRuntimeStreaming(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_emits_assistant_delta(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)
            options = OpenAgenticOptions(
                provider=FakeStreamingProvider(),
                model="m",
                api_key="x",
                cwd=str(root),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                include_partial_messages=True,
            )
            import openagentic_sdk

            types = []
            result_response_id = None
            async for e in openagentic_sdk.query(prompt="hi", options=options):
                types.append(getattr(e, "type", None))
                if getattr(e, "type", None) == "result":
                    result_response_id = getattr(e, "response_id", None)
            self.assertIn("assistant.delta", types)
            self.assertIn("assistant.message", types)
            self.assertIn("result", types)
            self.assertEqual(result_response_id, "resp_1")


if __name__ == "__main__":
    unittest.main()
