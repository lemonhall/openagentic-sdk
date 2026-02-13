import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk import query
from openagentic_sdk.options import AgentDefinition, OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput, ToolCall
from openagentic_sdk.sessions.store import FileSessionStore


class LegacyProviderAsksSlashCommandOnce:
    name = "legacy-slash"

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def complete(self, *, model: str, messages, tools=(), api_key=None):
        _ = (model, tools, api_key)
        msgs = list(messages)
        self.calls.append(msgs)

        # First call: ask runtime to execute SlashCommand.
        if len(self.calls) == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[ToolCall(tool_use_id="sc_1", name="SlashCommand", arguments={"name": "sub", "args": ""})],
                usage={"total_tokens": 1},
            )

        tool_msgs = [m for m in msgs if isinstance(m, dict) and m.get("role") == "tool"]
        if not tool_msgs:
            raise AssertionError("expected tool message")
        payload = json.loads(tool_msgs[-1].get("content") or "{}")
        parts = payload.get("parts")
        if not isinstance(parts, list) or not parts:
            raise AssertionError("expected non-empty parts")

        # Subtask parity: only a subtask part is returned; file parts are dropped.
        self._assert_equal(parts[0].get("type"), "subtask")
        self._assert_equal(parts[0].get("agent"), "demo")
        if any(isinstance(p, dict) and p.get("type") == "file" for p in parts):
            raise AssertionError("expected no file parts for subtask command")

        content = payload.get("content")
        if not isinstance(content, str):
            raise AssertionError("expected string content")
        if "Called the Read tool" in content:
            raise AssertionError("subtask command should not expand file parts")
        return ModelOutput(assistant_text="ok", tool_calls=(), usage={"total_tokens": 2})

    def _assert_equal(self, a, b) -> None:  # noqa: ANN001
        if a != b:
            raise AssertionError(f"expected {a!r} == {b!r}")


class TestSlashCommandPartsParity(unittest.IsolatedAsyncioTestCase):
    async def test_subtask_drops_file_parts(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            (root / "input.txt").write_text("filedata", encoding="utf-8")

            (root / ".opencode" / "commands").mkdir(parents=True)
            (root / ".opencode" / "commands" / "sub.md").write_text(
                "---\nagent: demo\nsubtask: true\ndescription: run demo\n---\n\nSubtask body @input.txt\n",
                encoding="utf-8",
            )

            store = FileSessionStore(root_dir=root)
            provider = LegacyProviderAsksSlashCommandOnce()
            options = OpenAgenticOptions(
                provider=provider,
                model="fake",
                api_key="x",
                cwd=str(root),
                project_dir=str(root),
                session_store=store,
                permission_gate=PermissionGate(permission_mode="bypass"),
                agents={"demo": AgentDefinition(description="d", prompt="p")},
            )

            async for _ in query(prompt="run cmd", options=options):
                pass

    async def test_agent_ref_emits_agent_part_and_instruction(self) -> None:
        class ProviderAsksAgentRef:
            name = "legacy-slash"

            def __init__(self) -> None:
                self.calls: list[list[dict]] = []

            async def complete(self, *, model: str, messages, tools=(), api_key=None):
                _ = (model, tools, api_key)
                msgs = list(messages)
                self.calls.append(msgs)
                if len(self.calls) == 1:
                    return ModelOutput(
                        assistant_text=None,
                        tool_calls=[ToolCall(tool_use_id="sc_1", name="SlashCommand", arguments={"name": "agentref", "args": ""})],
                        usage={"total_tokens": 1},
                    )

                tool_msgs = [m for m in msgs if isinstance(m, dict) and m.get("role") == "tool"]
                if not tool_msgs:
                    raise AssertionError("expected tool message")
                payload = json.loads(tool_msgs[-1].get("content") or "{}")
                parts = payload.get("parts")
                if not isinstance(parts, list):
                    raise AssertionError("expected parts list")
                if not any(isinstance(p, dict) and p.get("type") == "agent" and p.get("name") == "worker" for p in parts):
                    raise AssertionError("expected agent part for @worker")

                content = payload.get("content")
                if not isinstance(content, str):
                    raise AssertionError("expected string content")
                if "call the Task tool with subagent: worker" in content:
                    raise AssertionError("expected no synthetic task instruction for agent reference")

                return ModelOutput(assistant_text="ok", tool_calls=(), usage={"total_tokens": 2})

        with TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()

            (root / ".opencode" / "commands").mkdir(parents=True)
            (root / ".opencode" / "commands" / "agentref.md").write_text(
                "Agent ref @worker\n",
                encoding="utf-8",
            )

            store = FileSessionStore(root_dir=root)
            provider = ProviderAsksAgentRef()
            options = OpenAgenticOptions(
                provider=provider,
                model="fake",
                api_key="x",
                cwd=str(root),
                project_dir=str(root),
                session_store=store,
                permission_gate=PermissionGate(permission_mode="bypass"),
                agents={"worker": AgentDefinition(description="w", prompt="p")},
            )

            async for _ in query(prompt="run cmd", options=options):
                pass


if __name__ == "__main__":
    unittest.main()
