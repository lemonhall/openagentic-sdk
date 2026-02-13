from __future__ import annotations

import json
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options


class TestE2EToolsNotebookEditRoundtripReal(unittest.IsolatedAsyncioTestCase):
    async def test_notebook_edit_replaces_first_cell_source(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"NB_TOKEN_{uuid.uuid4().hex}"
            nb_path = root / "n.ipynb"
            nb = {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": ["OLD\n"],
                        "id": "c1",
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
            nb_path.write_text(json.dumps(nb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            injected = False

            async def inject_tool_calls(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                if injected:
                    return HookDecision()
                injected = True
                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                return HookDecision(
                    action="inject_notebookedit_read",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[
                            ToolCall(
                                tool_use_id="call-nb-1",
                                name="NotebookEdit",
                                arguments={"notebook_path": "./n.ipynb", "new_source": token},
                            ),
                            ToolCall(
                                tool_use_id="call-read-nb-1",
                                name="Read",
                                arguments={"file_path": "./n.ipynb"},
                            ),
                        ],
                        usage=usage if isinstance(usage, dict) else None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            hooks = HookEngine(
                after_model_call=[HookMatcher(name="inject-nbedit-read", tool_name_pattern="*", hook=inject_tool_calls)]
            )

            opts0 = make_options(root, allowed_tools=["NotebookEdit", "Read"])
            opts = replace(opts0, hooks=hooks, max_steps=10)
            prompt = (
                "You are graded by whether the notebook JSON actually changes on disk.\n"
                "After you receive tool results, reply with exactly: NOTEBOOK_OK."
            )

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt=prompt, options=opts):
                events.append(ev)

            nb2 = json.loads(nb_path.read_text(encoding="utf-8", errors="replace"))
            cells = nb2.get("cells")
            self.assertIsInstance(cells, list)
            self.assertTrue(cells)
            cell0 = cells[0]
            self.assertIsInstance(cell0, dict)
            src = cell0.get("source")
            self.assertIsInstance(src, list)
            if not any(token in str(x) for x in src):
                tool_uses = [getattr(e, "name", None) for e in events if getattr(e, "type", None) == "tool.use"]
                final_texts = [getattr(e, "final_text", "") for e in events if getattr(e, "type", None) == "result"]
                self.fail(f"expected notebook cell source to include token. tools={tool_uses!r} final={final_texts[-1:]!r} src={src!r}")
            saw_tool = any(getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "NotebookEdit" for e in events)
            self.assertTrue(saw_tool)


if __name__ == "__main__":
    unittest.main()
