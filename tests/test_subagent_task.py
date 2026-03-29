from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.options import AgentDefinition, OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.runtime_core.agent_runtime import AgentRuntime
from openagentic_sdk.sessions.store import FileSessionStore
from openagentic_sdk.tools.registry import ToolRegistry


class TaskProvider:
    name = "fake"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        user_text = next((m.get("content") for m in messages if m.get("role") == "user"), "")

        # Parent: request a Task tool call.
        if isinstance(user_text, str) and user_text.startswith("PARENT:") and not any(m.get("role") == "tool" for m in messages):
            return ModelOutput(
                assistant_text=None,
                tool_calls=[ToolCall(tool_use_id="call_task", name="Task", arguments={"agent": "worker", "prompt": "Do child work"})],
                usage=None,
                raw=None,
            )

        # Child: just return a final message.
        if isinstance(user_text, str) and user_text.startswith("CHILD_DEF:"):
            return ModelOutput(assistant_text="child ok", tool_calls=[], usage=None, raw=None)

        # Parent after Task completes
        if any(m.get("role") == "tool" for m in messages):
            return ModelOutput(assistant_text="parent ok", tool_calls=[], usage=None, raw=None)

        return ModelOutput(assistant_text="unexpected", tool_calls=[], usage=None, raw=None)


class TaskNoOutputProvider:
    name = "fake-no-output"

    async def complete(self, *, model, messages, tools=(), api_key=None):
        _ = model
        _ = tools
        _ = api_key
        user_text = next((m.get("content") for m in messages if m.get("role") == "user"), "")

        if isinstance(user_text, str) and user_text.startswith("PARENT_NO_OUTPUT:") and not any(m.get("role") == "tool" for m in messages):
            return ModelOutput(
                assistant_text=None,
                tool_calls=[ToolCall(tool_use_id="call_task", name="Task", arguments={"agent": "worker", "prompt": "Do child work"})],
                usage=None,
                raw=None,
            )

        if isinstance(user_text, str) and user_text.startswith("CHILD_EMPTY:"):
            return ModelOutput(assistant_text=None, tool_calls=[], usage=None, raw=None)

        if any(m.get("role") == "tool" for m in messages):
            tool_payload = next((m.get("content") for m in reversed(messages) if m.get("role") == "tool"), "")
            tool_obj = json.loads(tool_payload) if isinstance(tool_payload, str) and tool_payload else {}
            if isinstance(tool_obj, dict) and tool_obj.get("is_error") is True:
                return ModelOutput(assistant_text="parent saw task failure", tool_calls=[], usage=None, raw=None)
            return ModelOutput(assistant_text="parent unexpectedly saw success", tool_calls=[], usage=None, raw=None)

        return ModelOutput(assistant_text="unexpected", tool_calls=[], usage=None, raw=None)


class TestSubagentTask(unittest.IsolatedAsyncioTestCase):
    async def test_task_spawns_child_and_streams_events(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)

            options = OpenAgenticOptions(
                provider=TaskProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={
                    "worker": AgentDefinition(
                        description="child",
                        prompt="CHILD_DEF: do the work",
                        tools=(),
                    )
                },
            )

            import openagentic_sdk

            events = []
            async for e in openagentic_sdk.query(prompt="PARENT: delegate", options=options):
                events.append(e)

            child_events = [e for e in events if getattr(e, "agent_name", None) == "worker"]
            self.assertTrue(child_events, "expected child events in parent stream")
            self.assertTrue(all(getattr(e, "parent_tool_use_id", None) == "call_task" for e in child_events))

            task_results = [e for e in events if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", None) == "call_task"]
            self.assertTrue(task_results)
            self.assertFalse(task_results[-1].is_error)
            out = task_results[-1].output
            self.assertEqual(out["final_text"], "child ok")

    async def test_task_surfaces_child_no_output_as_error(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)

            options = OpenAgenticOptions(
                provider=TaskNoOutputProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={
                    "worker": AgentDefinition(
                        description="child",
                        prompt="CHILD_EMPTY: gather but do not answer",
                        tools=(),
                    )
                },
            )

            import openagentic_sdk

            events = []
            async for e in openagentic_sdk.query(prompt="PARENT_NO_OUTPUT: delegate", options=options):
                events.append(e)

            task_results = [e for e in events if getattr(e, "type", None) == "tool.result" and getattr(e, "tool_use_id", None) == "call_task"]
            self.assertTrue(task_results)
            task_result = task_results[-1]
            self.assertTrue(task_result.is_error)
            self.assertEqual(task_result.error_type, "SubagentNoOutput")
            self.assertEqual(task_result.output["dispatch_mode"], "local")
            self.assertEqual(task_result.output["child_stop_reason"], "no_output")
            self.assertEqual(getattr(events[-1], "final_text", None), "parent saw task failure")

    async def test_run_returns_parent_session_id_instead_of_child_session_id(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)

            options = OpenAgenticOptions(
                provider=TaskProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={
                    "worker": AgentDefinition(
                        description="child",
                        prompt="CHILD_DEF: do the work",
                        tools=(),
                    )
                },
            )

            import openagentic_sdk

            result = await openagentic_sdk.run(prompt="PARENT: delegate", options=options)
            self.assertTrue(result.session_id)
            self.assertEqual(result.session_id, result.events[0].session_id)

            task_result = next(
                event
                for event in result.events
                if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
            )
            self.assertNotEqual(result.session_id, task_result.output["child_session_id"])

    async def test_local_task_records_execution_metadata(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)

            options = OpenAgenticOptions(
                provider=TaskProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={
                    "worker": AgentDefinition(
                        description="child",
                        prompt="CHILD_DEF: do the work",
                        tools=(),
                    )
                },
            )

            import openagentic_sdk

            events = []
            async for e in openagentic_sdk.query(prompt="PARENT: delegate", options=options):
                events.append(e)

            task_result = next(
                event
                for event in events
                if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
            )
            output = task_result.output
            child_meta = store.read_metadata(output["child_session_id"])

            self.assertEqual(output["dispatch_mode"], "local")
            self.assertTrue(isinstance(output.get("execution_id"), str) and output["execution_id"])
            self.assertEqual(child_meta.get("dispatch_mode"), "local")
            self.assertEqual(child_meta.get("execution_id"), output["execution_id"])

    async def test_runtime_registry_tracks_local_execution(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)

            options = OpenAgenticOptions(
                provider=TaskProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={
                    "worker": AgentDefinition(
                        description="child",
                        prompt="CHILD_DEF: do the work",
                        tools=(),
                    )
                },
            )

            runtime = AgentRuntime(options)
            events = []
            async for event in runtime.query("PARENT: delegate"):
                events.append(event)

            task_result = next(
                event
                for event in events
                if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
            )
            child_events = [event for event in events if getattr(event, "agent_name", None) == "worker"]
            execution_id = task_result.output["execution_id"]
            record = runtime.actor_registry.get(execution_id)

            self.assertEqual(record.execution_id, execution_id)
            self.assertEqual(record.agent_name, "worker")
            self.assertEqual(record.dispatch_mode, "local")
            self.assertEqual(record.state, "exited")
            self.assertEqual(record.mailbox_heads["child_events"], len(child_events))

    async def test_api_query_exposes_runtime_state_for_local_execution(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)

            options = OpenAgenticOptions(
                provider=TaskProvider(),
                model="fake",
                api_key="x",
                cwd=str(root),
                tools=ToolRegistry([]),
                permission_gate=PermissionGate(permission_mode="bypass"),
                session_store=store,
                agents={
                    "worker": AgentDefinition(
                        description="child",
                        prompt="CHILD_DEF: do the work",
                        tools=(),
                    )
                },
            )

            import openagentic_sdk

            events = []
            async for event in openagentic_sdk.query(prompt="PARENT: delegate", options=options):
                events.append(event)

            task_result = next(
                event
                for event in events
                if getattr(event, "type", None) == "tool.result" and getattr(event, "tool_use_id", None) == "call_task"
            )
            execution_id = task_result.output["execution_id"]

            self.assertIsNotNone(options.runtime_state.runtime)
            self.assertIs(options.runtime_state.actor_registry, options.runtime_state.runtime.actor_registry)
            self.assertIs(options.runtime_state.actor_mailbox_store, options.runtime_state.runtime.actor_mailbox_store)
            self.assertEqual(options.runtime_state.actor_registry.get(execution_id).state, "exited")


if __name__ == "__main__":
    unittest.main()

