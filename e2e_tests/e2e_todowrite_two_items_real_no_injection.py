from __future__ import annotations

import json
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2ETodoWriteTwoItemsRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_todowrite_persists_two_items(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token1 = f"TODO1_{uuid.uuid4().hex}"
            token2 = f"TODO2_{uuid.uuid4().hex}"
            id1 = f"todo_{uuid.uuid4().hex}"
            id2 = f"todo_{uuid.uuid4().hex}"

            for attempt in range(3):
                opts0 = make_options(root, allowed_tools=["TodoWrite"])
                opts = replace(opts0, max_steps=10)
                prompt = (
                    "You MUST call the TodoWrite tool.\n"
                    "Create exactly two todo items using this JSON shape:\n"
                    "{\n"
                    '  "todos": [\n'
                    "    {\n"
                    f'      "content": "{token1}",\n'
                    '      "status": "completed",\n'
                    '      "priority": "high",\n'
                    f'      "id": "{id1}"\n'
                    "    },\n"
                    "    {\n"
                    f'      "content": "{token2}",\n'
                    '      "status": "pending",\n'
                    '      "priority": "low",\n'
                    f'      "id": "{id2}"\n'
                    "    }\n"
                    "  ]\n"
                    "}\n"
                    "After the tool succeeds, reply with exactly: TODO2_OK.\n"
                    f"(attempt={attempt + 1})\n"
                )

                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                self.assertTrue(r.session_id)
                todos_path = root / "sessions" / r.session_id / "todos.json"
                if not todos_path.exists():
                    continue
                obj = json.loads(todos_path.read_text(encoding="utf-8", errors="replace"))
                todos = obj.get("todos") if isinstance(obj, dict) else None
                ok = (
                    isinstance(todos, list)
                    and any(isinstance(t, dict) and token1 in str(t.get("content") or "") for t in todos)
                    and any(isinstance(t, dict) and token2 in str(t.get("content") or "") for t in todos)
                    and (r.final_text or "").strip() == "TODO2_OK"
                )
                if ok:
                    return

            self.fail("TodoWrite did not persist two todos after 3 attempts")


if __name__ == "__main__":
    unittest.main()

