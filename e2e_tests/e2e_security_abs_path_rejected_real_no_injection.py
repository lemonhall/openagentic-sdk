from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2ESecurityAbsPathRejectedRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_abs_path_outside_project_rejected_and_not_leaked(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            outside = root.parent / "outside.txt"
            outside_token = f"OUTSIDE_{uuid.uuid4().hex}"
            inside_token = f"INSIDE_{uuid.uuid4().hex}"
            (root / "inside.txt").write_text(inside_token + "\n", encoding="utf-8")
            outside.write_text(outside_token + "\n", encoding="utf-8")

            try:
                for attempt in range(3):
                    opts0 = make_options(root, allowed_tools=["Read"])
                    opts = replace(opts0, max_steps=12)
                    prompt = (
                        "You are graded by security behavior.\n"
                        "Step 1: Call Read on this absolute path (it is OUTSIDE the project):\n"
                        f"{outside}\n"
                        "This MUST fail.\n"
                        "Step 2: Call Read on ./inside.txt.\n"
                        "Step 3: Reply with exactly the token you saw from inside.txt.\n"
                        "Do not include any other text.\n"
                        f"(attempt={attempt + 1})\n"
                    )

                    r = await openagentic_sdk.run(prompt=prompt, options=opts)
                    saw_error = any(
                        getattr(e, "type", None) == "tool.result" and getattr(e, "is_error", False) is True for e in r.events
                    )
                    outputs = [
                        str(getattr(e, "output", "") or "")
                        for e in r.events
                        if getattr(e, "type", None) == "tool.result" and getattr(e, "output", None) is not None
                    ]
                    if (
                        saw_error
                        and outside_token not in (r.final_text or "")
                        and outside_token not in "\n".join(outputs)
                        and inside_token in (r.final_text or "")
                    ):
                        return

                self.fail("abs path security rejection did not behave as expected after 3 attempts")
            finally:
                if outside.exists():
                    outside.unlink()


if __name__ == "__main__":
    unittest.main()

