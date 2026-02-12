# v22 Index

## Vision

继续把核心模块真实网络 E2E 的“真度”拉高：

- `no_injection` 用例占比 ≥ 30%（更像真实用户流程）；
- 断言尽量落在“磁盘/事件”上，减少仅靠 final text 的软断言；
- 聚焦核心：`runtime_core/tools/skills/hooks/permissions/sessions`（不碰 MCP/Gateway/CLI-PTY）。

## Milestones

- **M1: Real-network E2E (core non-injection ratio v22)** — raise non-injection ratio + hard assertions
  - Plan: `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md`
  - PRD: `docs/prd/PRD-0022-real-network-e2e-core-noninjection-ratio-v22.md`
  - DoD：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-11）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0022-002 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_tool_loop_recover_read_missing_real_no_injection.py` → Evidence in plan
- REQ-0022-003 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_tool_loop_recover_edit_old_not_found_real_no_injection.py` → Evidence in plan
- REQ-0022-004 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_perm_default_prompt_write_real_no_injection.py` → Evidence in plan
- REQ-0022-005 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_perm_prompt_deny_then_allow_write_real_no_injection.py` → Evidence in plan
- REQ-0022-006 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_sessions_resume_two_turns_append_real_no_injection.py` → Evidence in plan
- REQ-0022-007 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_sessions_events_seq_monotonic_real_no_injection.py` → Evidence in plan
- REQ-0022-008 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_hooks_pre_tool_use_rewrite_read_real_no_injection.py` → Evidence in plan
- REQ-0022-009 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_write_overwrite_false_real_no_injection.py` → Evidence in plan
- REQ-0022-010 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_glob_read_write_summary_real_no_injection.py` → Evidence in plan
- REQ-0022-011 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_grep_edit_single_target_real_no_injection.py` → Evidence in plan
- REQ-0022-012 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_sessions_events_jsonl_excludes_deltas_real_no_injection.py` → Evidence in plan
- REQ-0022-013 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_todowrite_two_items_real_no_injection.py` → Evidence in plan
- REQ-0022-014 → `docs/plan/v22-real-network-e2e-core-noninjection-ratio.md` → `e2e_tests/e2e_perm_callback_deny_escape_write_real_no_injection.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- “NotebookEdit 非注入”在真实网络下不稳定（模型经常不触发该工具），因此本版改为用 **sessions/events.jsonl 不落 delta** 作为硬约束的非注入证据（与核心 resume 目标一致）。
