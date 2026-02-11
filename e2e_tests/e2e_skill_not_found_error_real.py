from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options


class TestE2ESkillNotFoundErrorReal(unittest.IsolatedAsyncioTestCase):
    async def test_missing_skill_yields_filenotfounderror_and_available_list(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".claude" / "skills" / "exists").mkdir(parents=True)
            (root / ".claude" / "skills" / "exists" / "SKILL.md").write_text(
                "---\nname: exists\ndescription: ok\n---\n\n# Exists\n",
                encoding="utf-8",
            )

            injected = False

            async def inject_missing_skill(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                if injected:
                    return HookDecision()
                injected = True
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                return HookDecision(
                    action="inject_missing_skill",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[ToolCall(tool_use_id="call-skill-1", name="Skill", arguments={"name": "missing"})],
                        usage=usage if isinstance(usage, dict) else None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-missing-skill", tool_name_pattern="*", hook=inject_missing_skill)])
            opts0 = make_options(root, allowed_tools=["Skill"], hooks=hooks)
            opts = replace(opts0, max_steps=3)

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt="Load missing skill", options=opts):
                events.append(ev)

            errs = [
                e
                for e in events
                if getattr(e, "type", None) == "tool.result"
                and getattr(e, "tool_use_id", None) == "call-skill-1"
                and getattr(e, "is_error", False) is True
            ]
            self.assertTrue(errs)
            err = errs[-1]
            self.assertEqual(getattr(err, "error_type", None), "FileNotFoundError")
            self.assertIn("Available skills", str(getattr(err, "error_message", "") or ""))
            self.assertIn("exists", str(getattr(err, "error_message", "") or ""))


if __name__ == "__main__":
    unittest.main()

