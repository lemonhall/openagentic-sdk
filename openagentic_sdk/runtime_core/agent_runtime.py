from __future__ import annotations

from .provider_input import ProviderInputMixin
from .slash_command import SlashCommandMixin
from .query_loop import QueryLoopMixin
from .tool_ask_user_question import AskUserQuestionMixin
from .tool_task import TaskToolMixin
from .tool_webfetch import WebFetchPromptMixin
from .tool_todowrite import TodoWriteMixin
from .tool_runner import ToolRunnerMixin

class AgentRuntime(
    ProviderInputMixin,
    SlashCommandMixin,
    AskUserQuestionMixin,
    TaskToolMixin,
    WebFetchPromptMixin,
    TodoWriteMixin,
    ToolRunnerMixin,
    QueryLoopMixin,
):
    def __init__(self, options: OpenAgenticOptions, *, agent_name: str | None = None, parent_tool_use_id: str | None = None):
        self._options = options
        self._agent_name = agent_name
        self._parent_tool_use_id = parent_tool_use_id

