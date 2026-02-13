# v53 Index

## Vision

离线 E2E 从“主干 smoke”提升为“硬不变量密度足够的回归门禁”：当离线 E2E 红时，优先按 **SDK 行为回归** 处理。

## Milestones

- **M1: Offline E2E hard-invariants density** — 25–40 tests + deterministic scripted providers
  - Plan: `docs/plan/v53-offline-e2e-hard-invariants-density.md`
  - PRD: `docs/prd/PRD-0053-offline-e2e-hard-invariants-density-v53.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0053-001 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/`（数量门禁）→ Evidence in plan
- REQ-0053-002 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_allowed_tools_tool_not_allowed.py` → Evidence in plan
- REQ-0053-003 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_permissions_prompt_no_answerer_denies.py` → Evidence in plan
- REQ-0053-004 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_permissions_callback_approver_raises_denies.py` → Evidence in plan
- REQ-0053-005 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_permissions_default_safe_read_no_prompt.py` → Evidence in plan
- REQ-0053-005 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_permissions_default_write_denied_no_side_effect.py` → Evidence in plan
- REQ-0053-005 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_permissions_accept_edits_allows_write_no_prompt.py` → Evidence in plan
- REQ-0053-006 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_permissions_can_use_tool_rewrite_input.py` → Evidence in plan
- REQ-0053-007 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_hooks_pre_tool_use_rewrite_read_target_injected.py` → Evidence in plan
- REQ-0053-007 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_hooks_pre_tool_use_block_write.py` → Evidence in plan
- REQ-0053-008 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_sessions_events_jsonl_excludes_assistant_delta.py` → Evidence in plan
- REQ-0053-009 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_security_path_traversal_write_blocked.py` → Evidence in plan
- REQ-0053-009 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_security_abs_path_outside_rejected.py` → Evidence in plan
- REQ-0053-009 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_windows_posix_path_mnt_data_maps_to_project.py` → Evidence in plan
- REQ-0053-009 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_windows_posix_unknown_abs_path_rejected.py` → Evidence in plan
- REQ-0053-010 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_tool_write_overwrite_false_raises.py` → Evidence in plan
- REQ-0053-010 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_tool_write_content_non_string_errors.py` → Evidence in plan
- REQ-0053-010 → `docs/plan/v53-offline-e2e-hard-invariants-density.md` → `e2e_tests_offline/e2e_tool_read_offset_limit_numbered.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- ✅ 已达成：离线 E2E 扩充到 28 tests（落在 25–40 区间）
- ✅ 已达成：新增 allowed_tools / permissions / hooks / sessions / path-security / tool-edge 的确定性离线回归用例（见追溯矩阵）
