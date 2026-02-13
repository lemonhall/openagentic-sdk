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
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options


class TestE2ESkillProjectDirArgumentReal(unittest.IsolatedAsyncioTestCase):
    async def test_skill_project_dir_argument_is_resolved_relative_to_project_dir(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            sub = root / "subproj"
            sub.mkdir()

            token = f"PD_{uuid.uuid4().hex}"
            skill_dir = sub / ".claude" / "skills" / "x"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: x\ndescription: demo\n---\n\nTOKEN: {token}\n",
                encoding="utf-8",
            )

            stage = 0

            async def inject_skill_then_finish(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal stage
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                if stage == 0:
                    stage = 1
                    return HookDecision(
                        action="inject_skill_project_dir",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[
                                ToolCall(
                                    tool_use_id="call-skill-1",
                                    name="Skill",
                                    arguments={"name": "x", "project_dir": "subproj"},
                                )
                            ],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                if stage == 1:
                    stage = 2
                    return HookDecision(
                        action="inject_final_text",
                        override_tool_output=ModelOutput(
                            assistant_text="PROJECT_DIR_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-skill-project-dir", tool_name_pattern="*", hook=inject_skill_then_finish)])
            opts0 = make_options(root, allowed_tools=["Skill"], hooks=hooks)
            opts = replace(opts0, max_steps=5)

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt="Load skill with project_dir", options=opts):
                events.append(ev)

            outs = [
                getattr(e, "output", None)
                for e in events
                if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", None) == "call-skill-1"
            ]
            self.assertTrue(outs)
            out = outs[-1]
            self.assertIsInstance(out, dict)
            self.assertIn(token, str(out.get("output") or ""))
            self.assertIn(str(skill_dir / "SKILL.md"), str(out.get("path") or ""))


if __name__ == "__main__":
    unittest.main()

