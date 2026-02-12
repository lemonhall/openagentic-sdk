from __future__ import annotations

import unittest


_SMOKE_MODULES: tuple[str, ...] = (
    # Provider streaming basics.
    "e2e_tests.e2e_provider_stream",
    # Streaming deltas are emitted to caller when enabled.
    "e2e_tests.e2e_query_emits_deltas",
    # Sessions: deltas must not persist in events.jsonl even when streaming.
    "e2e_tests.e2e_sessions_events_jsonl_excludes_deltas_real_no_injection",
    # Sessions: same resume id works across two runs (append-only).
    "e2e_tests.e2e_sessions_resume_two_turns_append_real_no_injection",
    # Permissions: default mode prompts then allows.
    "e2e_tests.e2e_perm_default_prompt_write_real_no_injection",
    # Permissions: prompt mode deny then allow.
    "e2e_tests.e2e_perm_prompt_deny_then_allow_write_real_no_injection",
    # Permissions: acceptEdits auto-allows Write without prompting.
    "e2e_tests.e2e_perm_accept_edits_write_real_no_injection",
    # Tool loop recovery after an expected tool error.
    "e2e_tests.e2e_tool_loop_recover_read_missing_real_no_injection",
    # Security boundary: reject absolute path outside project.
    "e2e_tests.e2e_security_abs_path_rejected_real_no_injection",
    # Tools: overwrite=false behavior.
    "e2e_tests.e2e_write_overwrite_false_real_no_injection",
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:  # noqa: ARG001
    suite = unittest.TestSuite()
    for mod in _SMOKE_MODULES:
        suite.addTests(loader.loadTestsFromName(mod))
    return suite

