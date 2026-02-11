from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher
from openagentic_sdk.providers.base import ModelOutput

from e2e_tests._harness import make_options


class TestE2EHooksAfterModelCallOverrideReal(unittest.IsolatedAsyncioTestCase):
    async def test_after_model_call_can_override_output(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"HOOK_AFTER_TOKEN_{uuid.uuid4().hex}"

            async def override(payload: Mapping[str, Any]) -> HookDecision:
                _ = payload
                return HookDecision(override_tool_output=ModelOutput(assistant_text=token, tool_calls=()))

            hooks = HookEngine(after_model_call=[HookMatcher(name="override-out", tool_name_pattern="*", hook=override)])

            opts0 = make_options(root, allowed_tools=[])
            opts = replace(opts0, hooks=hooks, max_steps=5)

            r = await openagentic_sdk.run(prompt="Write anything.", options=opts)
            self.assertEqual((r.final_text or "").strip(), token)
            self.assertTrue(any(getattr(e, "type", "") == "hook.event" and getattr(e, "hook_point", "") == "AfterModelCall" for e in r.events))


if __name__ == "__main__":
    unittest.main()

