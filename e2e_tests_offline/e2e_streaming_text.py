from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline


class _StreamingProvider:
    name = "offline-streaming"

    async def stream(self, *, model: str, input, **kwargs):  # noqa: A002
        _ = model, input, kwargs
        from openagentic_sdk.providers.stream_events import DoneEvent, TextDeltaEvent

        yield TextDeltaEvent(delta="E2E_OFFLINE_")
        yield TextDeltaEvent(delta="STREAM_OK")
        yield DoneEvent(response_id="resp-stream-1", usage={"protocol": "offline"})


class TestE2EOfflineStreamingText(unittest.IsolatedAsyncioTestCase):
    async def test_streaming_provider_text_is_accumulated(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            opts = make_options_offline(root, provider=_StreamingProvider(), allowed_tools=[])
            r = await openagentic_sdk.run(prompt="stream something", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_STREAM_OK")
            self.assertTrue(r.session_id)


if __name__ == "__main__":
    unittest.main()

