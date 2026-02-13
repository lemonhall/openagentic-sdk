from __future__ import annotations

import json
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests._harness import make_options


class TestE2EFlowTodoWriteThenReadTodosJsonRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_todowrite_persists_and_read_can_verify(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"TODO_FLOW_{uuid.uuid4().hex}"

            for attempt in range(5):
                opts0 = make_options(root, allowed_tools=["TodoWrite", "Read"])
                opts = replace(opts0, max_steps=18)
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 2 succeeds.\n"
                    "Step 1: Call TodoWrite to create exactly one todo item whose content includes this token:\n"
                    f"{token}\n"
                    "Step 2: Call Read on the todos file under the current session directory (sessions/<session_id>/todos.json).\n"
                    "After the Read tool, reply with exactly: TODO_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)
                session_id = r.session_id or ""
                if not session_id:
                    continue
                todos_path = root / "sessions" / session_id / "todos.json"
                if not todos_path.exists():
                    continue
                obj = json.loads(todos_path.read_text(encoding="utf-8", errors="replace"))
                todos = obj.get("todos") if isinstance(obj, dict) else None
                if (
                    isinstance(todos, list)
                    and any(isinstance(t, dict) and token in str(t.get("content") or "") for t in todos)
                    and (r.final_text or "").strip() == "TODO_OK"
                ):
                    return

            self.fail("TodoWrite→Read todos.json flow did not complete after 5 attempts")


if __name__ == "__main__":
    unittest.main()

