from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EToolsTodoWritePersistsReal(unittest.IsolatedAsyncioTestCase):
    async def test_todowrite_persists_todos_json_under_session_dir(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"TODO_TOKEN_{uuid.uuid4().hex}"
            todo_id = f"todo_{uuid.uuid4().hex}"

            opts = make_options(root, allowed_tools=["TodoWrite"])
            prompt = (
                "You MUST call the TodoWrite tool.\n"
                "Create a single todo item using this exact JSON shape:\n"
                "{\n"
                '  "todos": [\n'
                "    {\n"
                f'      "content": "{token}",\n'
                '      "status": "completed",\n'
                '      "priority": "high",\n'
                f'      "id": "{todo_id}"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "After the tool succeeds, reply with exactly: TODO_OK.\n"
                "Do not guess; use tools."
            )

            r = await openagentic_sdk.run(prompt=prompt, options=opts)
            self.assertTrue(r.session_id)
            todos_path = root / "sessions" / r.session_id / "todos.json"
            self.assertTrue(todos_path.exists())
            obj = json.loads(todos_path.read_text(encoding="utf-8", errors="replace"))
            self.assertIsInstance(obj, dict)
            todos = obj.get("todos")
            self.assertIsInstance(todos, list)
            if not any(isinstance(t, dict) and token in str(t.get("content") or "") for t in todos):
                self.fail(f"expected todos.json to contain token content. obj={obj!r}")


if __name__ == "__main__":
    unittest.main()
