from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EFlowSkillMissingThenExistsRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_skill_missing_errors_then_existing_skill_loads(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".claude" / "skills" / "exists").mkdir(parents=True)
            (root / ".claude" / "skills" / "exists" / "SKILL.md").write_text(
                "---\nname: exists\ndescription: ok\n---\n\n# Exists\n\nReply with EXISTS_SKILL.\n",
                encoding="utf-8",
            )

            for attempt in range(5):
                opts0 = make_options(root, allowed_tools=["Skill"])
                opts = replace(opts0, max_steps=14)
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 2 succeeds.\n"
                    "Step 1: Call Skill with name='missing' (this MUST error).\n"
                    "Step 2: Call Skill with name='exists' (this MUST succeed).\n"
                    "After Step 2 succeeds, reply with exactly: SKILL_FLOW_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_missing = any(
                    getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", False) is True
                    and getattr(e, "error_type", None) == "FileNotFoundError"
                    for e in r.events
                )
                saw_exists = any(
                    getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", True) is False
                    and isinstance(getattr(e, "output", None), dict)
                    and getattr(e, "output", {}).get("name") == "exists"
                    for e in r.events
                )
                if saw_missing and saw_exists and (r.final_text or "").strip() == "SKILL_FLOW_OK":
                    return

            self.fail("Skill missing→exists flow did not complete after 5 attempts")


if __name__ == "__main__":
    unittest.main()

