from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk

from e2e_tests_offline._harness import make_options_offline


class _SkillToolProvider:
    name = "offline-skill-tool"

    def __init__(self) -> None:
        self._n = 0

    async def complete(self, *, model: str, input, **kwargs):  # noqa: A002
        _ = model, kwargs
        from openagentic_sdk.providers.base import ModelOutput, ToolCall

        items = list(input)
        self._n += 1

        if self._n == 1:
            return ModelOutput(
                assistant_text=None,
                tool_calls=[ToolCall(tool_use_id="call-skill-1", name="Skill", arguments={"name": "demo-skill"})],
                response_id="resp-skill-1",
                provider_metadata={"protocol": "responses"},
            )

        if self._n == 2:
            out = next((x for x in items if isinstance(x, dict) and x.get("type") == "function_call_output"), None)
            if not isinstance(out, dict) or out.get("call_id") != "call-skill-1":
                raise AssertionError("expected function_call_output for call-skill-1")
            payload = out.get("output")
            if not isinstance(payload, str) or not payload:
                raise AssertionError("expected string JSON tool output")
            obj = json.loads(payload)
            if obj.get("name") != "demo-skill":
                raise AssertionError(f"unexpected skill name: {obj.get('name')!r}")
            if "SKILL.md" not in str(obj.get("path") or ""):
                raise AssertionError(f"unexpected skill path: {obj.get('path')!r}")

            return ModelOutput(
                assistant_text="E2E_OFFLINE_SKILL_OK",
                tool_calls=(),
                response_id="resp-skill-2",
                provider_metadata={"protocol": "responses"},
            )

        raise AssertionError(f"unexpected provider call count: {self._n}")


class TestE2EOfflineSkillTool(unittest.IsolatedAsyncioTestCase):
    async def test_skill_tool_loads_skill_and_returns_output(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            p = root / ".claude" / "skills" / "demo-skill"
            p.mkdir(parents=True)
            (p / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: demo\n---\n\n# Demo Skill\n\nSummary.\n",
                encoding="utf-8",
            )

            provider = _SkillToolProvider()
            opts = make_options_offline(root, provider=provider, allowed_tools=["Skill"])
            r = await openagentic_sdk.run(prompt="load skill", options=opts)
            self.assertEqual(r.final_text.strip(), "E2E_OFFLINE_SKILL_OK")
            self.assertTrue(r.session_id)


if __name__ == "__main__":
    unittest.main()

