from __future__ import annotations

import unittest


_FLOW_MODULES: tuple[str, ...] = (
    # Sessions/resume: write then read on second run.
    "e2e_tests.e2e_sessions_resume_two_turns_append_real_no_injection",
    # User-task flow: resume across runs then grep/read evidence.
    "e2e_tests.e2e_flow_resume_write_then_grep_real_no_injection",
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:  # noqa: ARG001
    suite = unittest.TestSuite()
    for mod in _FLOW_MODULES:
        suite.addTests(loader.loadTestsFromName(mod))
    return suite

