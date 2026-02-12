from __future__ import annotations

import unittest


_FLOW_MODULES: tuple[str, ...] = (
    # Human-in-the-loop: ask user → use answer → persist to disk.
    "e2e_tests.e2e_ask_user_write_read_pipeline_real_no_injection",
    # Skills: skill-defined workflow across multiple tools.
    "e2e_tests.e2e_workflow_skill_write_glob_grep_edit_read_real_no_injection",
    # Tools: edit roundtrip on disk.
    "e2e_tests.e2e_tools_edit_roundtrip_real_no_injection",
    # Permissions: default prompts then allows edit.
    "e2e_tests.e2e_permissions_default_prompts_edit_real_no_injection",
    # Sessions/resume: write then read on second run.
    "e2e_tests.e2e_sessions_resume_two_turns_append_real_no_injection",
    # Hooks: tool rewrite behavior with real-network provider.
    "e2e_tests.e2e_hooks_pre_tool_use_rewrite_read_real_no_injection",
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:  # noqa: ARG001
    suite = unittest.TestSuite()
    for mod in _FLOW_MODULES:
        suite.addTests(loader.loadTestsFromName(mod))
    return suite

