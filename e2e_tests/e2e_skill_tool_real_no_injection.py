from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2ESkillToolRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_model_loads_skill_without_injection(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"SKILL_TOKEN_{uuid.uuid4().hex}"

            skill_dir = root / ".claude" / "skills" / "demo-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: demo\n---\n\n# Demo Skill\n\nTOKEN: " + token + "\n",
                encoding="utf-8",
            )

            # Best-effort: real-network tests can be flaky when relying on the model to choose tools.
            for attempt in range(3):
                opts0 = make_options(root, allowed_tools=["Skill"])
                opts = replace(opts0, max_steps=8)
                prompt = (
                    "You are graded by tool usage and the final reply.\n"
                    "Step 1: Call the Skill tool with name=demo-skill.\n"
                    "Step 2: Reply with exactly the token found in the skill output.\n"
                    "Do not guess.\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                skill_uses = [
                    e
                    for e in r.events
                    if getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Skill"
                ]
                tool_use_id = getattr(skill_uses[-1], "tool_use_id", None) if skill_uses else None
                outs = [
                    getattr(e, "output", None)
                    for e in r.events
                    if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", None) == tool_use_id
                ]
                out_text = "\n".join([str(o) for o in outs if o is not None])
                if tool_use_id and token in out_text and token in (r.final_text or ""):
                    return

            self.fail("model did not load Skill and return the expected token after 3 attempts")


if __name__ == "__main__":
    unittest.main()
