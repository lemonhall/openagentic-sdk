# v50 Index

## Vision

把权限门（prompt/callback/acceptEdits）的负路径组合做成真网络 no-injection 回归证据，防止静默放行/异常漂移。

## Milestones

- **M1: permissions negative paths v50**
  - Plan: `docs/plan/v50-model-driven-e2e-permissions-negative-paths.md`
  - PRD: `docs/prd/PRD-0050-model-driven-e2e-permissions-negative-paths-v50.md`
  - DoD：
    - `python -m unittest -v e2e_tests.core_flows_hil`
    - `python -m unittest -v e2e_tests.core_flows_sessions`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
  - Status: done (2026-02-13)

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0050-001 → `docs/plan/v50-model-driven-e2e-permissions-negative-paths.md` → `e2e_tests/e2e_flow_permissions_prompt_no_answerer_denies_real_no_injection.py` → Evidence in plan
- REQ-0050-002 → `docs/plan/v50-model-driven-e2e-permissions-negative-paths.md` → `openagentic_sdk/permissions/gate.py` + `e2e_tests/e2e_flow_permissions_callback_approver_raises_denies_real_no_injection.py` → Evidence in plan
- REQ-0050-003 → `docs/plan/v50-model-driven-e2e-permissions-negative-paths.md` → `e2e_tests/e2e_flow_permissions_accept_edits_read_prompts_and_denies_real_no_injection.py` → Evidence in plan
- REQ-0050-004 → `docs/plan/v50-model-driven-e2e-permissions-negative-paths.md` → `e2e_tests/core_flows_hil.py` + `e2e_tests/core_flows_sessions.py` + `.openagentic_e2e_reports/...` → Evidence in plan

## ECN

- None
