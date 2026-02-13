# v40 Index

## Vision

把随机层的薄弱点补厚：继续堆 `core_flows_sessions`（resume×permissions×prune）与 `core_flows_hil`（hooks 真实流程）的用例密度。

## Milestones

- **M1: Model-driven sessions + hooks expansion v40**
  - Plan: `docs/plan/v40-model-driven-e2e-sessions-hooks-expansion.md`
  - PRD: `docs/prd/PRD-0040-model-driven-e2e-sessions-hooks-expansion-v40.md`
  - DoD：
    - `python -m unittest -v e2e_tests.core_flows_sessions`
    - `python -m unittest -v e2e_tests.core_flows_hil`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0040-001 → `docs/plan/v40-model-driven-e2e-sessions-hooks-expansion.md` → `e2e_tests/e2e_flow_resume_prompt_permission_write_then_read_real_no_injection.py` → Evidence in plan
- REQ-0040-002 → `docs/plan/v40-model-driven-e2e-sessions-hooks-expansion.md` → `e2e_tests/e2e_flow_resume_prompt_permission_deny_then_allow_write_real_no_injection.py` → Evidence in plan
- REQ-0040-003 → `docs/plan/v40-model-driven-e2e-sessions-hooks-expansion.md` → `e2e_tests/e2e_flow_prune_then_resume_read_small_real_no_injection.py` → Evidence in plan
- REQ-0040-004 → `docs/plan/v40-model-driven-e2e-sessions-hooks-expansion.md` → `e2e_tests/e2e_flow_hooks_post_tool_use_override_read_output_real_no_injection.py` → Evidence in plan
- REQ-0040-005 → `docs/plan/v40-model-driven-e2e-sessions-hooks-expansion.md` → `e2e_tests/core_flows_sessions.py` + `e2e_tests/core_flows_hil.py` + `.openagentic_e2e_reports/...` → Evidence in plan

## ECN

- None
