from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.events import AssistantMessage, Result, UserMessage
from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput
from openagentic_sdk.sessions.store import FileSessionStore


class _RecordingResponsesProvider:
    name = "recording-responses"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def complete(self, *, model, input, tools=(), api_key=None, previous_response_id=None, store=True):  # noqa: ANN001
        _ = (model, tools, api_key, store)
        self.calls.append(
            {
                "input": list(input),
                "previous_response_id": previous_response_id,
            }
        )
        return ModelOutput(assistant_text="ok", tool_calls=[], response_id="resp_new")


class TestSessionEditResumeReset(unittest.IsolatedAsyncioTestCase):
    async def test_edit_message_text_clears_previous_response_id_for_resumed_run(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)
            sid = store.create_session(metadata={})
            store.append_event(sid, UserMessage(text="old user"))
            store.append_event(sid, AssistantMessage(text="old assistant"))
            store.append_event(
                sid,
                Result(
                    final_text="done",
                    session_id=sid,
                    response_id="resp_prev",
                    provider_metadata={"protocol": "responses", "supports_previous_response_id": True},
                ),
            )

            changed = store.edit_message_text(sid, seq=1, new_text="edited user")
            self.assertTrue(changed)

            provider = _RecordingResponsesProvider()
            options = OpenAgenticOptions(
                provider=provider,
                model="m",
                api_key="x",
                cwd=str(root),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                resume=sid,
            )

            import openagentic_sdk

            async for _ in openagentic_sdk.query(prompt="continue", options=options):
                pass

            self.assertEqual(len(provider.calls), 1)
            self.assertIsNone(provider.calls[0]["previous_response_id"])
            rendered = provider.calls[0]["input"]
            self.assertIsInstance(rendered, list)
            self.assertTrue(any(isinstance(item, dict) and item.get("content") == "edited user" for item in rendered))
            self.assertFalse(any(isinstance(item, dict) and item.get("content") == "old user" for item in rendered))


if __name__ == "__main__":
    unittest.main()
