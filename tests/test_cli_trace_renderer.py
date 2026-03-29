import io
import unittest

from openagentic_sdk.events import AssistantDelta, AssistantMessage, HookEvent, Result, ToolResult, ToolUse


class TestCliTraceRenderer(unittest.TestCase):
    def test_groups_tools_and_summarizes(self) -> None:
        from openagentic_cli.trace import TraceRenderer

        out = io.StringIO()
        r = TraceRenderer(stream=out, color=False)

        r.on_event(ToolUse(tool_use_id="t1", name="Grep", input={"query": "x", "file_glob": "**/*.py"}))
        r.on_event(ToolResult(tool_use_id="t1", output={"total_matches": 2}, is_error=False))

        r.on_event(ToolUse(tool_use_id="t2", name="Bash", input={"command": "pwd"}))
        r.on_event(ToolResult(tool_use_id="t2", output={"exit_code": 0, "output": "/x\n"}, is_error=False))

        s = out.getvalue()
        self.assertIn("• Explored", s)
        self.assertIn("Search", s)
        self.assertIn("• Ran", s)
        self.assertIn("pwd", s)
        self.assertIn("exit_code=0", s)

    def test_write_tool_use_includes_path(self) -> None:
        from openagentic_cli.trace import TraceRenderer

        out = io.StringIO()
        r = TraceRenderer(stream=out, color=False)

        r.on_event(ToolUse(tool_use_id="t1", name="Write", input={"file_path": "out.txt", "content": "x"}))
        r.on_event(ToolResult(tool_use_id="t1", output={"message": "Wrote 1 bytes", "file_path": "/tmp/out.txt"}, is_error=False))

        self.assertIn("Write `out.txt`", out.getvalue())

    def test_rg_help_is_printed_when_missing_pattern(self) -> None:
        from openagentic_cli.trace import TraceRenderer

        out = io.StringIO()
        r = TraceRenderer(stream=out, color=False)
        r.on_event(ToolUse(tool_use_id="t1", name="Bash", input={"command": "rg"}))
        r.on_event(
            ToolResult(
                tool_use_id="t1",
                output={"exit_code": 2, "output": "rg: ripgrep requires at least one pattern to execute a search\n"},
                is_error=False,
            )
        )
        self.assertIn("hint:", out.getvalue())

    def test_rg_help_is_printed_when_rg_missing(self) -> None:
        from openagentic_cli.trace import TraceRenderer

        out = io.StringIO()
        r = TraceRenderer(stream=out, color=False)
        r.on_event(ToolUse(tool_use_id="t1", name="Bash", input={"command": "rg foo"}))
        r.on_event(
            ToolResult(
                tool_use_id="t1",
                output={"exit_code": 127, "output": "bash: rg: command not found\n"},
                is_error=False,
            )
        )
        s = out.getvalue()
        self.assertIn("winget install BurntSushi.ripgrep.MSVC", s)

    def test_streaming_deltas_do_not_duplicate_final(self) -> None:
        from openagentic_cli.trace import TraceRenderer

        out = io.StringIO()
        r = TraceRenderer(stream=out, color=False)
        r.on_event(AssistantDelta(text_delta="hi"))
        r.on_event(AssistantMessage(text="hi"))
        self.assertEqual(out.getvalue(), "hi\n")

    def test_hook_event_is_rendered(self) -> None:
        from openagentic_cli.trace import TraceRenderer

        out = io.StringIO()
        r = TraceRenderer(stream=out, color=False, show_hooks=True)
        r.on_event(HookEvent(hook_point="BeforeModelCall", name="x", matched=True, action="rewrite_messages"))
        self.assertIn("• Hooks", out.getvalue())

    def test_error_message_is_rendered(self) -> None:
        from openagentic_cli.trace import TraceRenderer

        out = io.StringIO()
        r = TraceRenderer(stream=out, color=False)
        r.on_event(ToolUse(tool_use_id="t1", name="Read", input={"file_path": "x"}))
        r.on_event(ToolResult(tool_use_id="t1", output=None, is_error=True, error_message="boom"))
        self.assertIn("ERROR: boom", out.getvalue())

    def test_remote_task_result_renders_dispatch_metadata(self) -> None:
        from openagentic_cli.trace import TraceRenderer

        out = io.StringIO()
        r = TraceRenderer(stream=out, color=False)
        r.on_event(ToolUse(tool_use_id="t1", name="Task", input={"agent": "writer", "prompt": "write a short essay"}))
        r.on_event(
            ToolResult(
                tool_use_id="t1",
                output={
                    "dispatch_mode": "k3s",
                    "target_node": "k3d-v56-openagentic-agent-1",
                    "worker_execution_id": "exec-123",
                },
                is_error=False,
            )
        )

        s = out.getvalue()
        self.assertIn("• Subagents", s)
        self.assertIn("[host] Delegate to `writer`", s)
        self.assertIn("[host] dispatch_mode=k3s", s)
        self.assertIn("target_node=k3d-v56-openagentic-agent-1", s)
        self.assertIn("worker_execution_id=exec-123", s)

    def test_task_use_renders_prompt_preview(self) -> None:
        from openagentic_cli.trace import TraceRenderer

        out = io.StringIO()
        r = TraceRenderer(stream=out, color=False)
        r.on_event(ToolUse(tool_use_id="t1", name="Task", input={"agent": "writer", "prompt": "write a short essay"}))

        s = out.getvalue()
        self.assertIn("[host] Delegate to `writer`", s)
        self.assertIn("[host] prompt: write a short essay", s)

    def test_task_use_truncates_prompt_preview_after_300_chars(self) -> None:
        from openagentic_cli.trace import TraceRenderer

        long_prompt = "a" * 305 + "tail"
        out = io.StringIO()
        r = TraceRenderer(stream=out, color=False)
        r.on_event(ToolUse(tool_use_id="t1", name="Task", input={"agent": "writer", "prompt": long_prompt}))

        s = out.getvalue()
        self.assertIn("[host] prompt: " + ("a" * 300) + "... ...", s)
        self.assertNotIn("tail", s)

    def test_local_task_result_is_marked_as_local(self) -> None:
        from openagentic_cli.trace import TraceRenderer

        out = io.StringIO()
        r = TraceRenderer(stream=out, color=False)
        r.on_event(ToolUse(tool_use_id="t1", name="Task", input={"agent": "writer", "prompt": "write a short essay"}))
        r.on_event(
            ToolResult(
                tool_use_id="t1",
                output={
                    "child_session_id": "abc123",
                    "final_text": "done",
                },
                is_error=False,
            )
        )

        s = out.getvalue()
        self.assertIn("[host] dispatch_mode=local", s)
        self.assertIn("child_session_id=abc123", s)

    def test_child_tool_trace_and_done_lines_include_agent_identity(self) -> None:
        from openagentic_cli.trace import TraceRenderer

        out = io.StringIO()
        r = TraceRenderer(stream=out, color=False)
        r.on_event(
            ToolUse(
                tool_use_id="t1",
                name="WebSearch",
                input={"query": "Iran March 2026"},
                agent_name="research",
                parent_tool_use_id="call_task",
            )
        )
        r.on_event(
            ToolResult(
                tool_use_id="t1",
                output={"query": "Iran March 2026", "results": [], "total_results": 0},
                is_error=False,
                agent_name="research",
                parent_tool_use_id="call_task",
            )
        )
        r.on_event(Result(final_text="", session_id="sid-child", stop_reason="no_output", agent_name="research"))
        r.on_event(Result(final_text="", session_id="sid-parent", stop_reason="end"))

        s = out.getvalue()
        self.assertIn("[research] WebSearch `Iran March 2026`", s)
        self.assertIn("[research] ok", s)
        self.assertIn("• Done agent=research stop_reason=no_output session_id=sid-child", s)
        self.assertIn("• Done agent=host stop_reason=end session_id=sid-parent", s)


if __name__ == "__main__":
    unittest.main()
