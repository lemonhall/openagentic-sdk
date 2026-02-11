from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EWorkflowSkillWriteGlobGrepEditReadRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_long_workflow_persists_to_disk(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"WF_TOKEN_{uuid.uuid4().hex}"

            skill_dir = root / ".claude" / "skills" / "workflow"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                (
                    "---\nname: workflow\ndescription: long workflow\n---\n\n"
                    "# Workflow\n\n"
                    "Use tools to do the following:\n"
                    "1) Write ./d/target.txt with content containing a line PLACEHOLDER.\n"
                    "2) Glob for *.txt under ./d.\n"
                    "3) Grep for PLACEHOLDER to confirm which file contains it.\n"
                    "4) Edit that file to replace PLACEHOLDER with the requested token.\n"
                    "5) Read the file to verify the token is present.\n"
                    "Finally reply with exactly: WORKFLOW_OK\n"
                ),
                encoding="utf-8",
            )

            target = root / "d" / "target.txt"
            (root / "d").mkdir()

            for attempt in range(3):
                if target.exists():
                    target.unlink()
                opts0 = make_options(root, allowed_tools=["Skill", "Write", "Glob", "Grep", "Edit", "Read"])
                opts = replace(opts0, max_steps=25)
                prompt = (
                    "You are graded by whether ./d/target.txt actually changes on disk.\n"
                    "Step 1: Call Skill(name=workflow) and follow it.\n"
                    "Step 2: Use this exact token for replacement: "
                    + token
                    + "\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_edit = any(
                    getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Edit" for e in r.events
                )
                text = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
                if saw_edit and token in text and (r.final_text or "").strip() == "WORKFLOW_OK":
                    return

            self.fail("model did not complete the long Skill-driven workflow after 3 attempts")


if __name__ == "__main__":
    unittest.main()

