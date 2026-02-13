from __future__ import annotations

import unittest


_FLOW_MODULES: tuple[str, ...] = (
    # Human-in-the-loop: ask user → use answer → persist to disk.
    "e2e_tests.e2e_ask_user_write_read_pipeline_real_no_injection",
    # Metamorphic: prompt variants preserve ask→write→read evidence.
    "e2e_tests.e2e_metamorphic_ask_user_write_read_variants_real_no_injection",
    # Skills: skill-defined workflow across multiple tools.
    "e2e_tests.e2e_workflow_skill_write_glob_grep_edit_read_real_no_injection",
    # Skill: missing then existing.
    "e2e_tests.e2e_flow_skill_missing_then_exists_real_no_injection",
    # Permissions: default prompts then allows edit.
    "e2e_tests.e2e_permissions_default_prompts_edit_real_no_injection",
    # Permissions(prompt): allow write.
    "e2e_tests.e2e_flow_permission_prompt_allow_write_real_no_injection",
    # Ask user + permission prompt + write.
    "e2e_tests.e2e_flow_ask_user_with_permission_prompt_write_real_no_injection",
    # Hooks: tool rewrite behavior with real-network provider.
    "e2e_tests.e2e_hooks_pre_tool_use_rewrite_read_real_no_injection",
    # v40: post_tool_use output override user-flow (no injection).
    "e2e_tests.e2e_flow_hooks_post_tool_use_override_read_output_real_no_injection",
    # v42: pre_tool_use rewrites Write path (user-flow).
    "e2e_tests.e2e_flow_hooks_pre_tool_use_rewrite_write_path_real_no_injection",
    # v42: default permission safe Read no prompt (no injection).
    "e2e_tests.e2e_flow_perm_default_read_no_prompt_real_no_injection",
    # v47: default permission denies Write (no disk write).
    "e2e_tests.e2e_flow_perm_default_write_denied_real_no_injection",
    # v47: hook rewrite cannot escape project root (Write traversal blocked).
    "e2e_tests.e2e_flow_hooks_pre_tool_use_rewrite_write_traversal_blocked_real_no_injection",
    # v50: permissions negative paths (prompt/callback).
    "e2e_tests.e2e_flow_permissions_prompt_no_answerer_denies_real_no_injection",
    "e2e_tests.e2e_flow_permissions_callback_approver_raises_denies_real_no_injection",
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:  # noqa: ARG001
    suite = unittest.TestSuite()
    for mod in _FLOW_MODULES:
        suite.addTests(loader.loadTestsFromName(mod))
    return suite
