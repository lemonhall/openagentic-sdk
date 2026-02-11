from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2ESkillToolchainEditRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_skill_driven_read_edit_roundtrip_writes_to_disk(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"CHAIN_TOKEN_{uuid.uuid4().hex}"
            p = root / "a.txt"

            skill_dir = root / ".claude" / "skills" / "patch-a"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                (
                    "---\nname: patch-a\ndescription: patch a.txt\n---\n\n"
                    "# Patch A\n\n"
                    "When asked to patch the file, do the following using tools:\n"
                    "1) Read ./a.txt\n"
                    "2) Edit ./a.txt: replace PLACEHOLDER with the requested token\n"
                    "3) Read ./a.txt again to verify\n"
                ),
                encoding="utf-8",
            )

            for attempt in range(3):
                p.write_text("BEGIN\nPLACEHOLDER\nEND\n", encoding="utf-8")
                opts0 = make_options(root, allowed_tools=["Skill", "Read", "Edit"])
                opts = replace(opts0, max_steps=12)
                prompt = (
                    "You are graded by whether ./a.txt actually changes on disk.\n"
                    "Step 1: Call Skill(name=patch-a) and follow its instructions.\n"
                    "Step 2: Replace PLACEHOLDER with this exact token: "
                    + token
                    + "\n"
                    "Step 3: Reply with exactly: PATCH_OK\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                saw_edit = any(
                    getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Edit" for e in r.events
                )
                text = p.read_text(encoding="utf-8", errors="replace")
                if saw_edit and token in text and (r.final_text or "").strip() == "PATCH_OK":
                    return

            self.fail("model did not complete Skill-driven Read/Edit flow after 3 attempts")


if __name__ == "__main__":
    unittest.main()

