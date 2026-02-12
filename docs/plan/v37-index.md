# v37 Index

## Vision

把“组合流程”（resume×permissions/hooks、prune×resume）变成可回归的 hard-invariants 真网络 E2E，并收敛到 `core_matrix_v37` 稳定套件。

## Milestones

- **M1: Core composed flows (resume + compaction) v37**
  - Plan: `docs/plan/v37-core-composed-flows-resume-compaction.md`
  - PRD: `docs/prd/PRD-0037-core-composed-flows-resume-compaction-v37.md`
  - DoD：
    - `python -m unittest -v e2e_tests.core_matrix_v37`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix_v37 --runs 3 --min-pass-rate 1.0`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0037-001 → `docs/plan/v37-core-composed-flows-resume-compaction.md` → `e2e_tests/e2e_sessions_resume_permission_prompt_deny_then_allow_write_real_injected.py` → Evidence in plan
- REQ-0037-002 → `docs/plan/v37-core-composed-flows-resume-compaction.md` → `e2e_tests/e2e_sessions_resume_post_tool_use_block_then_unblock_read_real_injected.py` → Evidence in plan
- REQ-0037-003 → `docs/plan/v37-core-composed-flows-resume-compaction.md` → `e2e_tests/e2e_compaction_prune_then_resume_read_still_works_real_injected.py` → Evidence in plan
- REQ-0037-004 → `docs/plan/v37-core-composed-flows-resume-compaction.md` → `e2e_tests/core_matrix_v37.py` + `.openagentic_e2e_reports/...` → Evidence in plan

## ECN

- None
