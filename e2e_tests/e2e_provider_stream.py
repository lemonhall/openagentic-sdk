from __future__ import annotations

import os
import unittest

from openagentic_sdk.providers.stream_events import DoneEvent, TextDeltaEvent

from e2e_tests._harness import make_provider, require_env


class TestE2EProviderStream(unittest.IsolatedAsyncioTestCase):
    async def test_provider_stream_emits_deltas_and_done(self) -> None:
        api_key = require_env("RIGHTCODE_API_KEY")
        provider = make_provider()
        model = os.environ.get("RIGHTCODE_MODEL") or "gpt-5.2"

        saw_delta = False
        done: DoneEvent | None = None
        async for ev in provider.stream(
            model=model,
            input=[{"role": "user", "content": "Reply with exactly: E2E_PROVIDER_STREAM_OK"}],
            api_key=api_key,
        ):
            if isinstance(ev, TextDeltaEvent) and ev.delta:
                saw_delta = True
            if isinstance(ev, DoneEvent):
                done = ev
                break

        self.assertTrue(saw_delta)
        self.assertIsNotNone(done)
        self.assertTrue((done.response_id or "").strip())


if __name__ == "__main__":
    unittest.main()
