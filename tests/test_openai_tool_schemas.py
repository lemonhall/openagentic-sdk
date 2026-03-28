import unittest
from pathlib import Path

from openagentic_sdk.options import (
    AgentDefinition,
    AgentExecutorDefinition,
    AgentWorkspaceDefinition,
)
from openagentic_sdk.tools.openai import tool_schemas_for_openai


class TestOpenAiToolSchemas(unittest.TestCase):
    def test_websearch_array_items_present(self) -> None:
        schemas = tool_schemas_for_openai(["WebSearch"])
        self.assertEqual(len(schemas), 1)
        params = schemas[0]["function"]["parameters"]
        props = params["properties"]
        self.assertEqual(props["allowed_domains"]["type"], "array")
        self.assertEqual(props["allowed_domains"]["items"]["type"], "string")
        self.assertEqual(props["blocked_domains"]["type"], "array")
        self.assertEqual(props["blocked_domains"]["items"]["type"], "string")
        self.assertNotIn("fallback, not the default first step", schemas[0]["function"]["description"])

    def test_ask_user_question_items_present(self) -> None:
        schemas = tool_schemas_for_openai(["AskUserQuestion"])
        params = schemas[0]["function"]["parameters"]
        props = params["properties"]
        self.assertEqual(props["questions"]["type"], "array")
        self.assertEqual(props["questions"]["items"]["type"], "object")

    def test_skill_schema_exists(self) -> None:
        schemas = tool_schemas_for_openai(["Skill"])
        self.assertEqual(len(schemas), 1)
        fn = schemas[0]["function"]
        self.assertEqual(fn["name"], "Skill")

    def test_skill_schema_lists_available_skills_in_description(self) -> None:
        project_dir = Path(__file__).resolve().parents[1] / "example"
        schemas = tool_schemas_for_openai(["Skill"], context={"project_dir": str(project_dir)})
        desc = schemas[0]["function"]["description"]
        self.assertIn("Only the skills listed here are available", desc)
        self.assertIn("main-process", desc)
        self.assertIn("drawing", desc)
        name_desc = schemas[0]["function"]["parameters"]["properties"]["name"]["description"]
        self.assertIn("available_skills", name_desc)
        self.assertIn("e.g.", name_desc)

    def test_task_schema_lists_named_agents_and_uses_agent_field_name(self) -> None:
        schemas = tool_schemas_for_openai(
            ["Task"],
            context={
                "agents": {
                    "research": AgentDefinition(
                        description="Research worker",
                        prompt="RESEARCH_DEF",
                        tools=("Read", "WebSearch"),
                        executor=AgentExecutorDefinition(kind="k3s", node_name="node-a"),
                        workspace=AgentWorkspaceDefinition(mode="readonly"),
                    ),
                    "writer": AgentDefinition(
                        description="Writer worker",
                        prompt="WRITER_DEF",
                        tools=("Read",),
                        executor=AgentExecutorDefinition(kind="k3s", node_name="node-b"),
                        workspace=AgentWorkspaceDefinition(mode="readonly"),
                    ),
                }
            },
        )
        self.assertEqual(len(schemas), 1)
        desc = schemas[0]["function"]["description"]
        self.assertIn("research", desc)
        self.assertIn("Research worker", desc)
        self.assertIn("node-a", desc)
        self.assertIn("writer", desc)
        self.assertIn("agent", desc)
        self.assertNotIn("subagent_type", desc)
        self.assertNotIn("host-side WebSearch/WebFetch", desc)

if __name__ == "__main__":
    unittest.main()
