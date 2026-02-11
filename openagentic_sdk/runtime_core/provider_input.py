from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator, Mapping

from ..compaction import (
    COMPACTION_SYSTEM_PROMPT,
    COMPACTION_USER_INSTRUCTION,
    select_tool_outputs_to_prune,
)
from ..events import (
    AssistantMessage,
    ToolOutputCompacted,
)
from ..options import OpenAgenticOptions
from ..sessions.rebuild import rebuild_messages, rebuild_responses_input
from ..sessions.store import FileSessionStore
from .common import (
    _filter_supported_kwargs,
)


class ProviderInputMixin:
    def _with_base_system(self, items: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        sys_prompt = getattr(self, "_base_system_prompt", None)
        sys_role = getattr(self, "_base_system_role", None) or "system"
        if not isinstance(sys_prompt, str) or not sys_prompt.strip():
            return items
        if items and isinstance(items[0], dict) and items[0].get("role") == sys_role:
            # The runtime keeps the base system prompt stable by rewriting index 0.
            return [{"role": sys_role, "content": sys_prompt}, *items[1:]]
        return [{"role": sys_role, "content": sys_prompt}, *items]


    def _rebuild_provider_input(
        self,
        *,
        store: FileSessionStore,
        session_id: str,
        provider_protocol: str,
        options: OpenAgenticOptions,
    ) -> list[Mapping[str, Any]]:
        events = store.read_events(session_id)
        if provider_protocol == "legacy":
            items = list(
                rebuild_messages(
                    events,
                    max_events=options.resume_max_events,
                    max_bytes=options.resume_max_bytes,
                )
            )
        else:
            items = list(
                rebuild_responses_input(
                    events,
                    max_events=options.resume_max_events,
                    max_bytes=options.resume_max_bytes,
                )
            )
        return self._with_base_system(items)


    async def _maybe_prune_tool_outputs(
        self,
        *,
        store: FileSessionStore,
        session_id: str,
    ) -> AsyncIterator[Any]:
        options = self._options
        if not getattr(options, "compaction", None) or not options.compaction.prune:
            return

        # Append-only marking of old tool results.
        events = store.read_events(session_id)
        to_prune = select_tool_outputs_to_prune(events=events, compaction=options.compaction)
        if not to_prune:
            return
        now = time.time()
        for tid in to_prune:
            ev = ToolOutputCompacted(
                tool_use_id=tid,
                compacted_ts=now,
                parent_tool_use_id=self._parent_tool_use_id,
                agent_name=self._agent_name,
            )
            store.append_event(session_id, ev)
            yield ev


    async def _run_compaction_pass(
        self,
        *,
        store: FileSessionStore,
        session_id: str,
        provider_protocol: str,
    ) -> AsyncIterator[Any]:
        """Run a dedicated, tool-less compaction call and store a summary pivot."""

        options = self._options

        complete_fn: Any = getattr(options.provider, "complete", None)
        if complete_fn is None:
            return

        # Summarize the current post-pivot window. Use rebuild_messages so the
        # compaction model sees a normal chat-style transcript.
        history = list(
            rebuild_messages(
                store.read_events(session_id),
                max_events=options.resume_max_events,
                max_bytes=options.resume_max_bytes,
            )
        )
        if provider_protocol != "legacy":
            # Some OpenAI-compatible Responses gateways accept role/content items
            # but reject ChatCompletions-only fields like `tool_calls` or the
            # `tool` role. For compaction we only need a readable transcript, so
            # we sanitize tool calls/results into plain assistant text.
            def _to_text(v: Any) -> str:
                if isinstance(v, str):
                    return v
                if v is None:
                    return ""
                try:
                    return json.dumps(v, ensure_ascii=False)
                except Exception:  # noqa: BLE001
                    return str(v)

            sanitized: list[Mapping[str, Any]] = []
            for m in history:
                if not isinstance(m, dict):
                    continue
                role = m.get("role")
                if role == "tool":
                    tid = m.get("tool_call_id")
                    tid_s = tid if isinstance(tid, str) and tid else ""
                    content_s = _to_text(m.get("content"))
                    prefix = f"[tool.result {tid_s}]".strip()
                    sanitized.append({"role": "assistant", "content": (prefix + "\n" + content_s).strip()})
                    continue

                if role in ("system", "user", "assistant"):
                    content_s = _to_text(m.get("content"))
                    tc = m.get("tool_calls")
                    tc_lines: list[str] = []
                    if isinstance(tc, list):
                        for item in tc:
                            if not isinstance(item, dict):
                                continue
                            fn = item.get("function")
                            if not isinstance(fn, dict):
                                continue
                            nm = fn.get("name")
                            args = fn.get("arguments")
                            if isinstance(nm, str) and nm:
                                tc_lines.append(f"[tool.call {nm}] {args if isinstance(args, str) else _to_text(args)}".strip())
                    if tc_lines:
                        joined = "\n".join(tc_lines).strip()
                        content_s = (joined + ("\n" + content_s if content_s else "")).strip()
                    sanitized.append({"role": role, "content": content_s})
                    continue

            history = sanitized

        # OpenCode parity: allow plugins to inject compaction context/prompt.
        compacting = {"context": [], "prompt": None}
        out2, hook_events, decision = await options.hooks.run_session_compacting(
            output=compacting,
            context={"session_id": session_id, "agent_name": self._agent_name},
        )
        for he in hook_events:
            store.append_event(session_id, he)
            yield he
        if decision is not None and decision.block:
            return
        compacting2 = out2 if isinstance(out2, dict) else compacting
        ctx_items = compacting2.get("context") if isinstance(compacting2, dict) else None
        ctx_list = [str(x) for x in ctx_items] if isinstance(ctx_items, list) else []
        prompt_override = compacting2.get("prompt") if isinstance(compacting2, dict) else None
        if isinstance(prompt_override, str) and prompt_override.strip():
            prompt_text = prompt_override.strip()
        else:
            prompt_text = "\n\n".join([COMPACTION_USER_INSTRUCTION, *ctx_list]).strip()

        # The compaction marker question is already present in history (rebuild
        # renders UserCompaction as "What did we do so far?").
        compaction_input: list[Mapping[str, Any]] = [
            {"role": "system", "content": COMPACTION_SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": prompt_text},
        ]

        if provider_protocol == "legacy":
            kwargs = {
                "model": options.model,
                "messages": compaction_input,
                "tools": (),
                "api_key": options.api_key,
            }
        else:
            kwargs = {
                "model": options.model,
                "input": compaction_input,
                "tools": (),
                "api_key": options.api_key,
                # Avoid polluting provider-side stored conversations.
                "store": False,
                "previous_response_id": None,
            }

        model_out = await complete_fn(**_filter_supported_kwargs(complete_fn, kwargs))
        summary = model_out.assistant_text or ""
        if not summary.strip():
            return

        msg = AssistantMessage(
            text=summary.strip(),
            is_summary=True,
            parent_tool_use_id=self._parent_tool_use_id,
            agent_name=self._agent_name,
        )
        store.append_event(session_id, msg)
        yield msg


