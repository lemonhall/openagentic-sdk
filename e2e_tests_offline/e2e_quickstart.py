from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline


class _QuickstartProvider:
    name = "offline-quickstart"

    async def complete(self, *, model: str, input, **kwargs):  # noqa: A002
        _ = model, input, kwargs
        from openagentic_sdk.providers.base import ModelOutput

        return ModelOutput(
            assistant_text="E2E_OFFLINE_QUICKSTART_OK",
            tool_calls=(),
            response_id="resp-quickstart-1",
            provider_metadata={"protocol": "responses"},
        )


class TestE2EOfflineQuickstart(unittest.IsolatedAsyncioTestCase):
    async def test_run_returns_final_text_and_session(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            opts = make_options_offline(root, provider=_QuickstartProvider(), allowed_tools=[])
            r = await openagentic_sdk.run(prompt="Reply with exactly: E2E_OFFLINE_QUICKSTART_OK", options=opts)
            self.assertTrue(r.session_id)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_QUICKSTART_OK")


if __name__ == "__main__":
    unittest.main()

