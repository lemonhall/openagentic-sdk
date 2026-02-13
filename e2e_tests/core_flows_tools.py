from __future__ import annotations

import unittest


_FLOW_MODULES: tuple[str, ...] = (
    # Tools: edit roundtrip on disk.
    "e2e_tests.e2e_tools_edit_roundtrip_real_no_injection",
    # User-task flows (tools).
    "e2e_tests.e2e_flow_glob_grep_edit_read_real_no_injection",
    "e2e_tests.e2e_flow_list_then_read_real_no_injection",
    "e2e_tests.e2e_flow_webfetch_example_domain_real_no_injection",
    "e2e_tests.e2e_flow_webfetch_blocks_localhost_then_example_real_no_injection",
    "e2e_tests.e2e_flow_todowrite_then_read_todos_json_real_no_injection",
    "e2e_tests.e2e_flow_read_offset_limit_numbered_real_no_injection",
    # v48: negative paths (tools/hook/tool-loop).
    "e2e_tests.e2e_flow_tools_write_outside_project_root_denied_real_no_injection",
    "e2e_tests.e2e_flow_hooks_pre_tool_use_block_write_hook_blocked_real_no_injection",
    "e2e_tests.e2e_flow_tools_read_missing_file_real_no_injection",
    "e2e_tests.e2e_flow_tools_edit_old_mismatch_real_no_injection",
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:  # noqa: ARG001
    suite = unittest.TestSuite()
    for mod in _FLOW_MODULES:
        suite.addTests(loader.loadTestsFromName(mod))
    return suite
