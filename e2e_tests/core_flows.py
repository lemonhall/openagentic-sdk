from __future__ import annotations

import unittest


_FLOW_SUITES: tuple[str, ...] = (
    "e2e_tests.core_flows_tools",
    "e2e_tests.core_flows_sessions",
    "e2e_tests.core_flows_hil",
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:  # noqa: ARG001
    suite = unittest.TestSuite()
    for mod in _FLOW_SUITES:
        suite.addTests(loader.loadTestsFromName(mod))
    return suite
