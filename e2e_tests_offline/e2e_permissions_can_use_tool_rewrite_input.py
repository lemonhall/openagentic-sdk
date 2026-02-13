from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.permissions.cas import PermissionResultAllow
from openagentic_sdk.permissions.gate import PermissionGate

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _WriteRewrittenByCanUseToolProvider:
    name = "offline-permissions-can-use-tool-rewrite"

    def __init__(self, *, token: str) -> None:
        self._n = 0
        self.token = token

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
                        arguments={"file_path": "a.txt", "content": self.token, "overwrite": True},
                    )
                ],
                response_id="resp-can-use-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-write-1")
            if payload.get("is_error") is True:
                raise AssertionError(f"expected write success, got: {payload!r}")
            fp = str(payload.get("file_path") or "")
            if not fp.endswith("rewritten.txt"):
                raise AssertionError(f"expected rewritten file_path to end with rewritten.txt, got: {fp!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_CAN_USE_TOOL_REWRITE_OK",
                tool_calls=(),
                response_id="resp-can-use-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflinePermissionsCanUseToolRewriteInput(unittest.IsolatedAsyncioTestCase):
    async def test_can_use_tool_updated_input_is_applied(self) -> None:
        token = f"REWRITE_{uuid.uuid4().hex}"

        async def _can_use_tool(tool_name, tool_input, _ctx):  # noqa: ANN001
            if tool_name != "Write":
                return PermissionResultAllow()
            updated = dict(tool_input)
            updated["file_path"] = "rewritten.txt"
            return PermissionResultAllow(updated_input=updated)

        with TemporaryDirectory() as td:
            root = Path(td)
            provider = _WriteRewrittenByCanUseToolProvider(token=token)
            opts0 = make_options_offline(root, provider=provider, allowed_tools=["Write"])
            gate = PermissionGate(permission_mode="deny", can_use_tool=_can_use_tool)
            opts = replace(opts0, permission_gate=gate, max_steps=6)

            r = await openagentic_sdk.run(prompt="rewrite via can_use_tool", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_CAN_USE_TOOL_REWRITE_OK")

            self.assertFalse((root / "a.txt").exists(), "original a.txt should not exist when input is rewritten")
            p = root / "rewritten.txt"
            self.assertTrue(p.exists())
            self.assertIn(token, p.read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()

