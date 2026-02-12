# v25 Index

## Vision

把核心 SDK 的“非注入负路径”固化为真 e2e 证据：

- 输入错误 → tool.result error
- 权限策略（acceptEdits） → 不打断用户流程
- 安全边界（越界绝对路径） → 必须拒绝且不泄露

## Milestones

- **M1: Real-network E2E (core non-injection negative paths v25)**
  - Plan: `docs/plan/v25-real-network-e2e-core-noninjection-negative-paths.md`
  - PRD: `docs/prd/PRD-0025-real-network-e2e-core-noninjection-negative-paths-v25.md`
  - DoD：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-11）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0025-001 → `docs/plan/v25-real-network-e2e-core-noninjection-negative-paths.md` → `e2e_tests/e2e_read_invalid_offset_recover_real_no_injection.py` → Evidence in plan
- REQ-0025-002 → `docs/plan/v25-real-network-e2e-core-noninjection-negative-paths.md` → `e2e_tests/e2e_perm_accept_edits_write_real_no_injection.py` → Evidence in plan
- REQ-0025-003 → `docs/plan/v25-real-network-e2e-core-noninjection-negative-paths.md` → `e2e_tests/e2e_perm_accept_edits_edit_real_no_injection.py` → Evidence in plan
- REQ-0025-004 → `docs/plan/v25-real-network-e2e-core-noninjection-negative-paths.md` → `e2e_tests/e2e_security_abs_path_rejected_real_no_injection.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- None

