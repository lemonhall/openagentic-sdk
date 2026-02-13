# v35 Index

## Vision

把“核心模块覆盖矩阵”落地为可执行的真网络 E2E 扩容清单，并用一批稳定（hard invariants）的 injected 用例先把核心模块用例密度堆上去。

## Milestones

- **M1: Core e2e coverage matrix + expansion v35**
  - Plan: `docs/plan/v35-core-e2e-coverage-matrix-and-expansion.md`
  - PRD: `docs/prd/PRD-0035-core-e2e-coverage-matrix-and-expansion-v35.md`
  - DoD：
    - `python -m unittest -v e2e_tests.core_matrix`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix --runs 3 --min-pass-rate 1.0`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0035-001 → `docs/plan/v35-core-e2e-coverage-matrix-and-expansion.md` → `docs/guides/core-e2e-coverage-matrix.md` → Evidence in plan
- REQ-0035-002 → `docs/plan/v35-core-e2e-coverage-matrix-and-expansion.md` → `e2e_tests/e2e_tools_list_tree_output_real_injected.py` → Evidence in plan
- REQ-0035-003 → `docs/plan/v35-core-e2e-coverage-matrix-and-expansion.md` → `openagentic_sdk/tools/list_dir.py` + `e2e_tests/e2e_security_list_abs_path_rejected_real_injected.py` → Evidence in plan
- REQ-0035-004 → `docs/plan/v35-core-e2e-coverage-matrix-and-expansion.md` → `e2e_tests/e2e_runtime_allowed_tools_gate_tool_not_allowed_real_injected.py` → Evidence in plan
- REQ-0035-005 → `docs/plan/v35-core-e2e-coverage-matrix-and-expansion.md` → `e2e_tests/e2e_permissions_callback_deny_then_allow_write_real_injected.py` → Evidence in plan
- REQ-0035-006 → `docs/plan/v35-core-e2e-coverage-matrix-and-expansion.md` → `e2e_tests/e2e_hooks_post_tool_use_block_real_injected.py` → Evidence in plan
- REQ-0035-007 → `docs/plan/v35-core-e2e-coverage-matrix-and-expansion.md` → `e2e_tests/core_matrix.py` + `.openagentic_e2e_reports/...` → Evidence in plan

## ECN

- None
