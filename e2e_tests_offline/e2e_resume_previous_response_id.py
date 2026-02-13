from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline


class _ThreadingProvider:
    name = "offline-threading"

    def __init__(self) -> None:
        self.seen_previous_response_ids: list[str | None] = []
        self._n = 0

    async def complete(
        self,
        *,
        model: str,
        input,  # noqa: ANN001
        previous_response_id: str | None = None,
        **kwargs,
    ):  # noqa: A002
        _ = model, input, kwargs
        from openagentic_sdk.providers.base import ModelOutput

        self.seen_previous_response_ids.append(previous_response_id)
        self._n += 1
        rid = f"resp-thread-{self._n}"
        return ModelOutput(
            assistant_text=f"ok-{self._n}",
            tool_calls=(),
            response_id=rid,
            provider_metadata={"protocol": "responses"},
        )


class TestE2EOfflineResumePreviousResponseId(unittest.IsolatedAsyncioTestCase):
    async def test_resume_passes_previous_response_id(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            provider = _ThreadingProvider()

            opts1 = make_options_offline(root, provider=provider, allowed_tools=[])
            r1 = await openagentic_sdk.run(prompt="first", options=opts1)
            self.assertTrue(r1.session_id)

            opts2 = make_options_offline(root, provider=provider, allowed_tools=[])
            # Resume the same session; runtime should pass previous_response_id from stored response_id.
            opts2 = replace(opts2, resume=r1.session_id)
            r2 = await openagentic_sdk.run(prompt="second", options=opts2)
            self.assertEqual(r1.session_id, r2.session_id)

            # Call 1: no previous_response_id. Call 2: previous_response_id == resp-thread-1.
            self.assertEqual(provider.seen_previous_response_ids[:2], [None, "resp-thread-1"])


if __name__ == "__main__":
    unittest.main()
