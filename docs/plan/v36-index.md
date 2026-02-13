# v36 Index

## Vision

继续按覆盖矩阵堆核心 hard-invariants 真网络 E2E 的用例密度，并产出稳定聚合套件 `core_matrix_v36` 作为必绿回归门。

## Milestones

- **M1: Core hard-invariants e2e density v36**
  - Plan: `docs/plan/v36-core-hard-invariants-e2e-density.md`
  - PRD: `docs/prd/PRD-0036-core-hard-invariants-e2e-density-v36.md`
  - DoD：
    - `python -m unittest -v e2e_tests.core_matrix_v36`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix_v36 --runs 3 --min-pass-rate 1.0`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0036-001 → `docs/plan/v36-core-hard-invariants-e2e-density.md` → `e2e_tests/e2e_tools_list_truncated_limit_real_injected.py` → Evidence in plan
- REQ-0036-002 → `docs/plan/v36-core-hard-invariants-e2e-density.md` → `e2e_tests/e2e_tools_list_ignores_junk_dirs_real_injected.py` → Evidence in plan
- REQ-0036-003 → `docs/plan/v36-core-hard-invariants-e2e-density.md` → `e2e_tests/e2e_tools_edit_old_not_found_errors_real_injected.py` → Evidence in plan
- REQ-0036-004 → `docs/plan/v36-core-hard-invariants-e2e-density.md` → `e2e_tests/e2e_tools_write_content_non_string_errors_real_injected.py` → Evidence in plan
- REQ-0036-005 → `docs/plan/v36-core-hard-invariants-e2e-density.md` → `e2e_tests/e2e_permissions_default_safe_tools_no_prompt_real_injected.py` → Evidence in plan
- REQ-0036-006 → `docs/plan/v36-core-hard-invariants-e2e-density.md` → `e2e_tests/e2e_permissions_accept_edits_prompts_webfetch_real_injected.py` → Evidence in plan
- REQ-0036-007 → `docs/plan/v36-core-hard-invariants-e2e-density.md` → `e2e_tests/core_matrix_v36.py` + `.openagentic_e2e_reports/...` → Evidence in plan

## ECN

- None
