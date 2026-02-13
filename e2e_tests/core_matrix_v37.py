from __future__ import annotations

import unittest


_CORE_MATRIX_V37_MODULES: tuple[str, ...] = (
    # v36 stable base
    "e2e_tests.core_matrix_v36",
    # v37: composed flows
    "e2e_tests.e2e_sessions_resume_permission_prompt_deny_then_allow_write_real_injected",
    "e2e_tests.e2e_sessions_resume_post_tool_use_block_then_unblock_read_real_injected",
    "e2e_tests.e2e_compaction_prune_then_resume_read_still_works_real_injected",
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:  # noqa: ARG001
    suite = unittest.TestSuite()
    for mod in _CORE_MATRIX_V37_MODULES:
        suite.addTests(loader.loadTestsFromName(mod))
    return suite

