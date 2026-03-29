from __future__ import annotations

from ..options import OpenAgenticOptions
from ..subagents.actor_local_transport import LocalActorTransport
from ..subagents.actor_mailbox import ActorMailboxStore
from ..subagents.actor_registry import ActorExecutionRegistry
from ..subagents.actor_tracing import ensure_actor_tracing
from .provider_input import ProviderInputMixin
from .query_loop import QueryLoopMixin
from .slash_command import SlashCommandMixin
from .tool_ask_user_question import AskUserQuestionMixin
from .tool_runner import ToolRunnerMixin
from .tool_task import TaskToolMixin
from .tool_todowrite import TodoWriteMixin
from .tool_webfetch import WebFetchPromptMixin


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
        self.actor_tracing = ensure_actor_tracing(options)
        self.actor_registry = ActorExecutionRegistry()
        self.actor_mailbox_store = ActorMailboxStore()
        self._local_actor_transport = LocalActorTransport(
            registry=self.actor_registry,
            mailbox_store=self.actor_mailbox_store,
            tracing=self.actor_tracing,
        )
        options.runtime_state.bind_runtime(self)

