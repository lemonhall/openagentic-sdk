from __future__ import annotations

import unittest


_FLOW_MODULES: tuple[str, ...] = (
    # Sessions/resume: write then read on second run.
    "e2e_tests.e2e_sessions_resume_two_turns_append_real_no_injection",
    # User-task flow: resume across runs then grep/read evidence.
    "e2e_tests.e2e_flow_resume_write_then_grep_real_no_injection",
    # v40: resume + prompt permission (allow).
    "e2e_tests.e2e_flow_resume_prompt_permission_write_then_read_real_no_injection",
    # v40: resume + prompt permission (deny then allow across runs).
    "e2e_tests.e2e_flow_resume_prompt_permission_deny_then_allow_write_real_no_injection",
    # v40: prune + resume still usable.
    "e2e_tests.e2e_flow_prune_then_resume_read_small_real_no_injection",
    # v42: resume + acceptEdits (no prompt) + edit/read.
    "e2e_tests.e2e_flow_resume_accept_edits_edit_then_read_real_no_injection",
    # v42: resume + post_tool_use override (redaction on second run).
    "e2e_tests.e2e_flow_resume_post_tool_use_override_read_redacted_real_no_injection",
    # v47: events.jsonl never persists assistant.delta (anti-GB guard).
    "e2e_tests.e2e_flow_sessions_events_exclude_assistant_delta_real_no_injection",
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:  # noqa: ARG001
    suite = unittest.TestSuite()
    for mod in _FLOW_MODULES:
        suite.addTests(loader.loadTestsFromName(mod))
    return suite
