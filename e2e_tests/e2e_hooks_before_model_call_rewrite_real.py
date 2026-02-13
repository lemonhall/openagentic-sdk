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

from e2e_tests._harness import make_options


class TestE2EHooksBeforeModelCallRewriteReal(unittest.IsolatedAsyncioTestCase):
    async def test_before_model_call_can_rewrite_messages(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"HOOK_BEFORE_TOKEN_{uuid.uuid4().hex}"

            async def rewrite(payload: Mapping[str, Any]) -> HookDecision:
                msgs = payload.get("messages")
                if not isinstance(msgs, list) or not msgs:
                    return HookDecision()
                last = dict(msgs[-1]) if isinstance(msgs[-1], dict) else {}
                if last.get("role") != "user":
                    return HookDecision()
                last["content"] = f"Reply with exactly: {token}"
                return HookDecision(override_messages=[*msgs[:-1], last])

            hooks = HookEngine(
                before_model_call=[HookMatcher(name="rewrite-last-user", tool_name_pattern="*", hook=rewrite)],
                enable_message_rewrite_hooks=True,
            )

            opts0 = make_options(root, allowed_tools=[])
            opts = replace(opts0, hooks=hooks, max_steps=5)

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt="hello", options=opts):
                events.append(ev)

            final_texts = [getattr(e, "final_text", "") for e in events if getattr(e, "type", None) == "result"]
            self.assertTrue(final_texts)
            self.assertEqual(final_texts[-1].strip(), token)
            self.assertTrue(any(getattr(e, "type", "") == "hook.event" and getattr(e, "hook_point", "") == "BeforeModelCall" for e in events))


if __name__ == "__main__":
    unittest.main()

