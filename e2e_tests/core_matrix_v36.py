from __future__ import annotations

import unittest


_CORE_MATRIX_V36_MODULES: tuple[str, ...] = (
    # v35: core matrix expansion
    "e2e_tests.e2e_tools_list_tree_output_real_injected",
    "e2e_tests.e2e_security_list_abs_path_rejected_real_injected",
    "e2e_tests.e2e_runtime_allowed_tools_gate_tool_not_allowed_real_injected",
    "e2e_tests.e2e_permissions_callback_deny_then_allow_write_real_injected",
    "e2e_tests.e2e_hooks_post_tool_use_block_real_injected",
    # v36: more hard-invariants density
    "e2e_tests.e2e_tools_list_truncated_limit_real_injected",
    "e2e_tests.e2e_tools_list_ignores_junk_dirs_real_injected",
    "e2e_tests.e2e_tools_edit_old_not_found_errors_real_injected",
    "e2e_tests.e2e_tools_write_content_non_string_errors_real_injected",
    "e2e_tests.e2e_permissions_default_safe_tools_no_prompt_real_injected",
    "e2e_tests.e2e_permissions_accept_edits_prompts_webfetch_real_injected",
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:  # noqa: ARG001
    suite = unittest.TestSuite()
    for mod in _CORE_MATRIX_V36_MODULES:
        suite.addTests(loader.loadTestsFromName(mod))
    return suite

