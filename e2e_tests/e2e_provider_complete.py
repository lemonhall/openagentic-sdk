from __future__ import annotations

import os
import unittest

from e2e_tests._harness import make_provider, require_env


class TestE2EProviderComplete(unittest.IsolatedAsyncioTestCase):
    async def test_provider_complete_returns_text_and_response_id(self) -> None:
        api_key = require_env("RIGHTCODE_API_KEY")
        provider = make_provider()
        model = os.environ.get("RIGHTCODE_MODEL") or "gpt-5.2"

        out = await provider.complete(
            model=model,
            input=[{"role": "user", "content": "Reply with exactly: E2E_PROVIDER_COMPLETE_OK"}],
            api_key=api_key,
        )
        self.assertTrue((out.assistant_text or "").strip())
        self.assertIsInstance(out.response_id, str)
        self.assertTrue(out.response_id)


if __name__ == "__main__":
    unittest.main()
