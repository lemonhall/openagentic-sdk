from __future__ import annotations

import unittest


_CORE_MATRIX_MODULES: tuple[str, ...] = (
    "e2e_tests.e2e_tools_list_tree_output_real_injected",
    "e2e_tests.e2e_security_list_abs_path_rejected_real_injected",
    "e2e_tests.e2e_runtime_allowed_tools_gate_tool_not_allowed_real_injected",
    "e2e_tests.e2e_permissions_callback_deny_then_allow_write_real_injected",
    "e2e_tests.e2e_hooks_post_tool_use_block_real_injected",
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:  # noqa: ARG001
    suite = unittest.TestSuite()
    for mod in _CORE_MATRIX_MODULES:
        suite.addTests(loader.loadTestsFromName(mod))
    return suite

