from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2ESkillToolReal(unittest.IsolatedAsyncioTestCase):
    async def test_model_uses_skill_tool_to_fetch_secret_token(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"SKILL_TOKEN_{uuid.uuid4().hex}"

            skill_dir = root / ".claude" / "skills" / "demo-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: demo\n---\n\n# Demo Skill\n\nTOKEN: " + token + "\n",
                encoding="utf-8",
            )

            opts = make_options(root, allowed_tools=["Skill"])
            prompt = (
                "You MUST call the Skill tool with name='demo-skill'.\n"
                "After the tool returns, find the line that starts with 'TOKEN:' in the skill body.\n"
                "Reply with exactly the token value (the part after 'TOKEN:').\n"
                "Do not guess."
            )

            r = await openagentic_sdk.run(prompt=prompt, options=opts)
            self.assertIn(token, r.final_text or "")


if __name__ == "__main__":
    unittest.main()

