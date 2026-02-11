from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EToolLoopFilesystem(unittest.IsolatedAsyncioTestCase):
    async def test_read_tool_is_used_for_unknown_token_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            fixture = f"PUBLIC_FIXTURE_{uuid.uuid4().hex}"
            p = (root / "fixture.txt").resolve()
            p.write_text(fixture, encoding="utf-8")
            abs_path = str(p)

            opts = make_options(root, allowed_tools=["Read"])
            prompt = (
                f"Use the Read tool to read this exact file path:\n{abs_path}\n"
                "After reading, reply with exactly: READ_OK\n"
                "Do not guess."
            )

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt=prompt, options=opts):
                events.append(ev)

            read_ids = {
                getattr(e, "tool_use_id", "")
                for e in events
                if getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Read"
            }
            outputs = [
                getattr(e, "output", None)
                for e in events
                if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", "") in read_ids
            ]
            saw_fixture = any(
                isinstance(out, dict) and isinstance(out.get("content"), str) and fixture in out.get("content", "")
                for out in outputs
            )

            self.assertTrue(read_ids)
            if not saw_fixture:
                self.fail(f"Read tool ran but fixture not found in outputs: {outputs}")

    async def test_write_tool_creates_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"WROTE_{uuid.uuid4().hex}"
            target = root / "created.txt"

            opts = make_options(root, allowed_tools=["Write"])
            prompt = (
                "Use the Write tool to create created.txt with exactly this content:\n"
                f"{token}\n"
                "After writing, reply with exactly: WROTE_OK"
            )

            async for _ev in openagentic_sdk.query(prompt=prompt, options=opts):
                pass

            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8", errors="replace").strip(), token)


if __name__ == "__main__":
    unittest.main()
