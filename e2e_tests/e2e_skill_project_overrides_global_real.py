from __future__ import annotations

import os
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


class TestE2ESkillProjectOverridesGlobalReal(unittest.IsolatedAsyncioTestCase):
    async def test_project_skill_overrides_global_skill(self) -> None:
        with TemporaryDirectory() as td, TemporaryDirectory() as global_td:
            root = Path(td)
            global_root = Path(global_td)

            name = "demo-skill"
            global_token = f"GLOBAL_{uuid.uuid4().hex}"
            project_token = f"PROJECT_{uuid.uuid4().hex}"

            (global_root / "skills" / name).mkdir(parents=True)
            (global_root / "skills" / name / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: global\n---\n\nTOKEN: {global_token}\n",
                encoding="utf-8",
            )

            project_skill_dir = root / ".claude" / "skills" / name
            project_skill_dir.mkdir(parents=True)
            (project_skill_dir / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: project\n---\n\nTOKEN: {project_token}\n",
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
                        action="inject_skill",
                        override_tool_output=ModelOutput(
                            assistant_text=None,
                            tool_calls=[ToolCall(tool_use_id="call-skill-1", name="Skill", arguments={"name": name})],
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
                            assistant_text="SKILL_OVERRIDE_OK",
                            tool_calls=[],
                            usage=usage if isinstance(usage, dict) else None,
                            response_id=rid if isinstance(rid, str) else None,
                            provider_metadata=pm if isinstance(pm, dict) else None,
                        ),
                    )

                return HookDecision()

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-skill", tool_name_pattern="*", hook=inject_skill_then_finish)])
            opts0 = make_options(root, allowed_tools=["Skill"], hooks=hooks)
            opts = replace(opts0, max_steps=5)

            old_home = os.environ.get("OPENAGENTIC_SDK_HOME")
            os.environ["OPENAGENTIC_SDK_HOME"] = str(global_root)
            try:
                events: list[object] = []
                async for ev in openagentic_sdk.query(prompt="Load demo skill", options=opts):
                    events.append(ev)
            finally:
                if old_home is None:
                    os.environ.pop("OPENAGENTIC_SDK_HOME", None)
                else:
                    os.environ["OPENAGENTIC_SDK_HOME"] = old_home

            outputs = [
                getattr(e, "output", None)
                for e in events
                if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", None) == "call-skill-1"
            ]
            self.assertTrue(outputs)
            out = outputs[-1]
            self.assertIsInstance(out, dict)
            self.assertIn(project_token, str(out.get("output") or ""))
            self.assertNotIn(global_token, str(out.get("output") or ""))
            self.assertIn(str(project_skill_dir / "SKILL.md"), str(out.get("path") or ""))


if __name__ == "__main__":
    unittest.main()

