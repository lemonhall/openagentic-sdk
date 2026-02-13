from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2ESessionResumeSmoke(unittest.IsolatedAsyncioTestCase):
    async def test_second_run_resumes_same_session_id(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            opts1 = make_options(root, allowed_tools=[])
            r1 = await openagentic_sdk.run(prompt="Reply with exactly: E2E_RESUME_1_OK", options=opts1)
            self.assertTrue(r1.session_id)
            self.assertTrue((r1.final_text or "").strip())

            opts2 = make_options(root, allowed_tools=[])
            opts2 = replace(opts2, resume=r1.session_id)
            r2 = await openagentic_sdk.run(prompt="Reply with exactly: E2E_RESUME_2_OK", options=opts2)
            self.assertEqual(r2.session_id, r1.session_id)
            self.assertTrue((r2.final_text or "").strip())


if __name__ == "__main__":
    unittest.main()

