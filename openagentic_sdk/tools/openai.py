from __future__ import annotations

from typing import Any, Mapping, Sequence

from openagentic_sdk.options import AgentDefinition
from openagentic_sdk.skills.index import index_skills
from openagentic_sdk.tool_prompts import render_tool_prompt

from .registry import ToolRegistry


def _render_task_agents(raw_agents: Any) -> str:
    if not isinstance(raw_agents, Mapping) or not raw_agents:
        return "  (none configured)"

    blocks: list[str] = []
    for agent_name, raw_definition in raw_agents.items():
        if not isinstance(agent_name, str) or not agent_name:
            continue
        if not isinstance(raw_definition, AgentDefinition):
            continue
        tools = ", ".join(raw_definition.tools) if raw_definition.tools else "(inherit/default)"
        node_name = raw_definition.executor.node_name or "(none)"
        blocks.append(f'- "{agent_name}": {raw_definition.description}')
        blocks.append(f"  tools: {tools}")
        blocks.append(f"  executor: {raw_definition.executor.kind}")
        blocks.append(f"  node_name: {node_name}")
    return "\n".join(blocks) if blocks else "  (none configured)"


def tool_schemas_for_openai(
    tool_names: Sequence[str],
    *,
    registry: ToolRegistry | None = None,
    context: Mapping[str, Any] | None = None,
) -> list[Mapping[str, Any]]:
    ctx = dict(context or {})
    cwd = ctx.get("cwd")
    directory = cwd if isinstance(cwd, str) and cwd else "(unknown)"
    project_dir = ctx.get("project_dir") if isinstance(ctx.get("project_dir"), str) else None
    if not project_dir and isinstance(directory, str) and directory and directory != "(unknown)":
        project_dir = directory

    bash_max_bytes = 1024 * 1024
    bash_max_lines = 2000
    if registry is not None:
        try:
            bash_tool = registry.get("Bash")
        except KeyError:
            bash_tool = None
        if bash_tool is not None:
            bash_max_bytes = int(getattr(bash_tool, "max_output_bytes", bash_max_bytes))
            bash_max_lines = int(getattr(bash_tool, "max_output_lines", bash_max_lines))

    prompt_vars: dict[str, Any] = {
        "directory": directory,
        "maxBytes": bash_max_bytes,
        "maxLines": bash_max_lines,
        "project_dir": project_dir or "",
        "agents": _render_task_agents(ctx.get("agents")),
    }

    schemas: dict[str, Mapping[str, Any]] = {
        "AskUserQuestion": {
            "type": "function",
            "function": {
                "name": "AskUserQuestion",
                "description": "Ask the user a clarifying question.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        # Preferred shape (multi-question batch):
                        "questions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string"},
                                    "header": {"type": "string"},
                                    "options": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "label": {"type": "string"},
                                                "description": {"type": "string"},
                                            },
                                            "required": ["label"],
                                        },
                                    },
                                    "multiple": {"type": "boolean"},
                                    "multiSelect": {"type": "boolean"},
                                },
                                "required": ["question"],
                            },
                        },
                        # Common single-question calling style (runtime normalizes to `questions=[...]`):
                        "question": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "choices": {"type": "array", "items": {"type": "string"}},
                        "answers": {"type": "object"},
                    },
                },
            },
        },
        "Read": {
            "type": "function",
            "function": {
                "name": "Read",
                "description": "Read a file from disk.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        # CAS / opencode-style aliases:
                        "filePath": {"type": "string"},
                        "offset": {"type": "integer"},
                        "limit": {"type": "integer"},
                    },
                },
            },
        },
        "List": {
            "type": "function",
            "function": {
                "name": "List",
                "description": "List files under a directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "dir": {"type": "string"},
                        "directory": {"type": "string"},
                    },
                },
            },
        },
        "Write": {
            "type": "function",
            "function": {
                "name": "Write",
                "description": "Create or overwrite a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "filePath": {"type": "string"},
                        "content": {"type": "string"},
                        "overwrite": {"type": "boolean"},
                    },
                },
            },
        },
        "Edit": {
            "type": "function",
            "function": {
                "name": "Edit",
                "description": "Apply a precise edit (string replace) to a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "filePath": {"type": "string"},
                        "old": {"type": "string"},
                        "new": {"type": "string"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                        "oldString": {"type": "string"},
                        "newString": {"type": "string"},
                        "count": {"type": "integer"},
                        "replace_all": {"type": "boolean"},
                        "replaceAll": {"type": "boolean"},
                        "before": {"type": "string"},
                        "after": {"type": "string"},
                    },
                },
            },
        },
        "Glob": {
            "type": "function",
            "function": {
                "name": "Glob",
                "description": "Find files by glob pattern.",
                "parameters": {
                    "type": "object",
                    "properties": {"pattern": {"type": "string"}, "root": {"type": "string"}},
                    "required": ["pattern"],
                },
            },
        },
        "Grep": {
            "type": "function",
            "function": {
                "name": "Grep",
                "description": "Search file contents with a regex.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "file_glob": {"type": "string"},
                        "root": {"type": "string"},
                        "case_sensitive": {"type": "boolean"},
                    },
                    "required": ["query"],
                },
            },
        },
        "Bash": {
            "type": "function",
            "function": {
                "name": "Bash",
                "description": "Run a shell command.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout_s": {"type": "number"},
                        # CAS / opencode-style aliases:
                        "timeout": {"type": "integer"},
                        "workdir": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
        },
        "WebFetch": {
            "type": "function",
            "function": {
                "name": "WebFetch",
                "description": "Fetch a public web page via Tavily Extract.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "headers": {"type": "object"},
                        "prompt": {"type": "string"},
                    },
                    "required": ["url"],
                },
            },
        },
        "WebSearch": {
            "type": "function",
            "function": {
                "name": "WebSearch",
                "description": "Search the web (Tavily backend).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer"},
                        "allowed_domains": {"type": "array", "items": {"type": "string"}},
                        "blocked_domains": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["query"],
                },
            },
        },
        "NotebookEdit": {
            "type": "function",
            "function": {
                "name": "NotebookEdit",
                "description": "Edit a Jupyter notebook (.ipynb).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "notebook_path": {"type": "string"},
                        "cell_id": {"type": "string"},
                        "new_source": {"type": "string"},
                        "cell_type": {"type": "string"},
                        "edit_mode": {"type": "string"},
                    },
                    "required": ["notebook_path"],
                },
            },
        },
        "SlashCommand": {
            "type": "function",
            "function": {
                "name": "SlashCommand",
                "description": "Load and render a slash command by name (opencode-compatible).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "args": {"type": "string"},
                        # CAS / legacy aliases:
                        "arguments": {"type": "string"},
                        "project_dir": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
        },
        "Skill": {
            "type": "function",
            "function": {
                "name": "Skill",
                "description": "Load a Skill by name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
        },
        "Task": {
            "type": "function",
            "function": {
                "name": "Task",
                "description": "Run a subagent by name.",
                "parameters": {
                    "type": "object",
                    "properties": {"agent": {"type": "string"}, "prompt": {"type": "string"}},
                    "required": ["agent", "prompt"],
                },
            },
        },
        "TodoWrite": {
            "type": "function",
            "function": {
                "name": "TodoWrite",
                "description": "Write or update a TODO list for the current session.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "todos": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content": {"type": "string"},
                                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                                    "activeForm": {"type": "string"},
                                },
                                "required": ["content", "status", "activeForm"],
                            },
                        }
                    },
                    "required": ["todos"],
                },
            },
        },
    }

    if isinstance(project_dir, str) and project_dir:
        try:
            skills = index_skills(project_dir=project_dir)
        except Exception:  # pragma: no cover
            skills = []
        if skills:
            blocks: list[str] = []
            for s in skills:
                blocks.append("  <skill>")
                blocks.append(f"    <name>{s.name}</name>")
                blocks.append(f"    <description>{s.description}</description>" if s.description else "    <description />")
                blocks.append("  </skill>")
            available_skills = "\n".join(blocks)
            examples = ", ".join([repr(s.name) for s in skills[:3]])
            hint = f" (e.g., {examples}, ...)" if examples else ""
        else:
            available_skills = "  (none found)"
            hint = ""
        schemas["Skill"]["function"]["description"] = render_tool_prompt(
            "skill",
            variables={
                "available_skills": available_skills,
                "project_dir": project_dir,
            },
        )
        schemas["Skill"]["function"]["parameters"]["properties"]["name"]["description"] = (
            "The skill identifier from <available_skills>." + hint
        )
    # Tool prompt injection (opencode-style templates).
    schemas["AskUserQuestion"]["function"]["description"] = render_tool_prompt("question", variables=prompt_vars)
    schemas["Read"]["function"]["description"] = render_tool_prompt("read", variables=prompt_vars)
    schemas["Write"]["function"]["description"] = render_tool_prompt("write", variables=prompt_vars)
    schemas["Edit"]["function"]["description"] = render_tool_prompt("edit", variables=prompt_vars)
    schemas["Glob"]["function"]["description"] = render_tool_prompt("glob", variables=prompt_vars)
    schemas["Grep"]["function"]["description"] = render_tool_prompt("grep", variables=prompt_vars)
    schemas["Bash"]["function"]["description"] = render_tool_prompt("bash", variables=prompt_vars)
    schemas["WebFetch"]["function"]["description"] = render_tool_prompt("webfetch", variables=prompt_vars)
    schemas["WebSearch"]["function"]["description"] = render_tool_prompt("websearch", variables=prompt_vars)
    schemas["Task"]["function"]["description"] = render_tool_prompt("task", variables=prompt_vars)
    schemas["TodoWrite"]["function"]["description"] = render_tool_prompt("todowrite", variables=prompt_vars)

    out: list[Mapping[str, Any]] = []
    for name in tool_names:
        schema = schemas.get(name)
        if schema is not None:
            out.append(schema)
            continue
        if registry is not None:
            try:
                tool = registry.get(name)
            except KeyError:
                continue
            openai_schema = getattr(tool, "openai_schema", None)
            if isinstance(openai_schema, dict):
                out.append(openai_schema)
    return out
