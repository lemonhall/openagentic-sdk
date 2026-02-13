from __future__ import annotations

import os
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline
from e2e_tests_offline._util import get_function_call_output_payload


class _ReadPosixMntDataProvider:
    name = "offline-windows-posix-mnt-data"

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
                tool_calls=[ToolCall(tool_use_id="call-read-1", name="Read", arguments={"file_path": "/mnt/data/a.txt"})],
                response_id="resp-mnt-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            payload = get_function_call_output_payload(items, call_id="call-read-1")
            if payload.get("is_error") is True:
                raise AssertionError(f"expected mapped read success, got: {payload!r}")
            if self.token not in str(payload.get("content") or ""):
                raise AssertionError(f"expected token in content, got: {payload!r}")
            return ModelOutput(
                assistant_text="E2E_OFFLINE_MNT_DATA_MAP_OK",
                tool_calls=(),
                response_id="resp-mnt-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineWindowsPosixPathMntDataMapsToProject(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(os.name == "nt", "Windows-only POSIX-like path mapping test")
    async def test_posix_mnt_data_maps_under_project_root(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"MNT_{uuid.uuid4().hex}"
            (root / "a.txt").write_text(token, encoding="utf-8")

            opts0 = make_options_offline(root, provider=_ReadPosixMntDataProvider(token=token), allowed_tools=["Read"])
            opts = replace(opts0, max_steps=6)

            r = await openagentic_sdk.run(prompt="read posix path", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_MNT_DATA_MAP_OK")


if __name__ == "__main__":
    unittest.main()

