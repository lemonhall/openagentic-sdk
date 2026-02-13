from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _TraversalWriteProvider:
    name = "offline-security-traversal-write"

    def __init__(self) -> None:
        self._n = 0

    async def complete(self, *, model: str, input, **kwargs):  # noqa: A002
        _ = model, kwargs
        from openagentic_sdk.providers.base import ModelOutput, ToolCall

        items = list(input)
        self._n += 1

        if self._n == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[
                    ToolCall(
                        tool_use_id="call-write-1",
                        name="Write",
                        arguments={"file_path": "../escape.txt", "content": "ESCAPE", "overwrite": True},
                    )
                ],
                response_id="resp-trav-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-write-1")
            if payload.get("is_error") is not True:
                raise AssertionError(f"expected is_error true, got: {payload!r}")
            if payload.get("error_type") != "ValueError":
                raise AssertionError(f"expected ValueError, got: {payload.get('error_type')!r}")
            msg = str(payload.get("error_message") or "")
            if "Tool path must be under project root" not in msg:
                raise AssertionError(f"expected traversal block message, got: {msg!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_TRAVERSAL_BLOCK_OK",
                tool_calls=(),
                response_id="resp-trav-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineSecurityPathTraversalWriteBlocked(unittest.IsolatedAsyncioTestCase):
    async def test_write_path_traversal_is_blocked_and_has_no_side_effect(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            outside = root.parent / "escape.txt"

            if outside.exists():
                outside.unlink()

            opts0 = make_options_offline(root, provider=_TraversalWriteProvider(), allowed_tools=["Write"])
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="traversal write", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_TRAVERSAL_BLOCK_OK")
            self.assertFalse((root / "escape.txt").exists())
            self.assertFalse(outside.exists(), "should not write outside project root")


if __name__ == "__main__":
    unittest.main()

