from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher
from openagentic_sdk.options import AgentDefinition
from openagentic_sdk.providers.base import ModelOutput, ToolCall

from e2e_tests._harness import make_options


class TestE2ETaskSubagent(unittest.IsolatedAsyncioTestCase):
    async def test_task_spawns_child_agent_and_reads_token(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            fixture = f"PUBLIC_FIXTURE_{uuid.uuid4().hex}"
            (root / "fixture.txt").write_text(fixture, encoding="utf-8")

            injected = False

            async def inject_reader_tool_call(payload: Mapping[str, Any]) -> HookDecision:
                nonlocal injected
                ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
                if ctx.get("agent_name") != "reader" or injected:
                    return HookDecision()
                injected = True

                out = payload.get("output")
                rid = getattr(out, "response_id", None) if out is not None else None
                usage = getattr(out, "usage", None) if out is not None else None
                pm = getattr(out, "provider_metadata", None) if out is not None else None

                return HookDecision(
                    action="inject_reader_read",
                    override_tool_output=ModelOutput(
                        assistant_text=None,
                        tool_calls=[
                            ToolCall(
                                tool_use_id="call-read-1",
                                name="Read",
                                arguments={"file_path": "./fixture.txt"},
                            )
                        ],
                        usage=usage if isinstance(usage, dict) else None,
                        response_id=rid if isinstance(rid, str) else None,
                        provider_metadata=pm if isinstance(pm, dict) else None,
                    ),
                )

            agents = {
                "reader": AgentDefinition(
                    description="Read a non-secret fixture file",
                    prompt=(
                        "You are a file reader.\n"
                        "The file you need is a non-secret test fixture in the current working directory.\n"
                        "Use Read on ./fixture.txt.\n"
                        "After reading, reply with exactly: READ_OK"
                    ),
                    tools=["Read"],
                    model=None,
                )
            }

            hooks = HookEngine(after_model_call=[HookMatcher(name="inject-reader-read", tool_name_pattern="*", hook=inject_reader_tool_call)])

            opts0 = make_options(root, allowed_tools=["Task"], hooks=hooks)
            opts = replace(opts0, agents=agents)
            prompt = (
                "Use the Task tool with agent='reader'.\n"
                "In the Task prompt, tell the agent to read ./fixture.txt and then reply with exactly: READ_OK.\n"
                "Do not use Read directly in the parent."
            )

            events: list[object] = []
            async for ev in openagentic_sdk.query(prompt=prompt, options=opts):
                events.append(ev)

            saw_task = any(
                getattr(e, "type", None) == "tool.use" and getattr(e, "name", None) == "Task" for e in events
            )
            child_read_ids = {
                getattr(e, "tool_use_id", "")
                for e in events
                if getattr(e, "type", None) == "tool.use"
                and getattr(e, "name", None) == "Read"
                and getattr(e, "parent_tool_use_id", None) is not None
            }
            child_read_outputs = [
                getattr(e, "output", None)
                for e in events
                if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", "") in child_read_ids
            ]
            saw_fixture_in_tool_output = any(
                isinstance(out, dict) and isinstance(out.get("content"), str) and fixture in out.get("content", "")
                for out in child_read_outputs
            )

            self.assertTrue(saw_task)
            self.assertTrue(child_read_ids)
            self.assertTrue(saw_fixture_in_tool_output)


if __name__ == "__main__":
    unittest.main()
