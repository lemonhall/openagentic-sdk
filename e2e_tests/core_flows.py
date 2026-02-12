from __future__ import annotations

import unittest


_FLOW_MODULES: tuple[str, ...] = (
    # Human-in-the-loop: ask user → use answer → persist to disk.
    "e2e_tests.e2e_ask_user_write_read_pipeline_real_no_injection",
    # Metamorphic: prompt variants preserve ask→write→read evidence.
    "e2e_tests.e2e_metamorphic_ask_user_write_read_variants_real_no_injection",
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
    # v38: expand user-task style flows (no injection)
    "e2e_tests.e2e_flow_glob_grep_edit_read_real_no_injection",
    "e2e_tests.e2e_flow_list_then_read_real_no_injection",
    "e2e_tests.e2e_flow_webfetch_example_domain_real_no_injection",
    "e2e_tests.e2e_flow_webfetch_blocks_localhost_then_example_real_no_injection",
    "e2e_tests.e2e_flow_resume_write_then_grep_real_no_injection",
    "e2e_tests.e2e_flow_permission_prompt_allow_write_real_no_injection",
    "e2e_tests.e2e_flow_ask_user_with_permission_prompt_write_real_no_injection",
    "e2e_tests.e2e_flow_todowrite_then_read_todos_json_real_no_injection",
    "e2e_tests.e2e_flow_read_offset_limit_numbered_real_no_injection",
    "e2e_tests.e2e_flow_skill_missing_then_exists_real_no_injection",
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:  # noqa: ARG001
    suite = unittest.TestSuite()
    for mod in _FLOW_MODULES:
        suite.addTests(loader.loadTestsFromName(mod))
    return suite
