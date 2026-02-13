# v51 Index

## Vision

补齐 PermissionGate 的 CAS（can_use_tool）与 interactive 分支真网络 no-injection 回归证据，形成 permissions 全谱系覆盖。

## Milestones

- **M1: permissions CAS + interactive v51**
  - Plan: `docs/plan/v51-model-driven-e2e-permissions-cas-interactive.md`
  - PRD: `docs/prd/PRD-0051-model-driven-e2e-permissions-cas-interactive-v51.md`
  - DoD：
    - `python -m unittest -v e2e_tests.core_flows_hil`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
  - Status: done (2026-02-13)

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0051-001 → `docs/plan/v51-model-driven-e2e-permissions-cas-interactive.md` → `e2e_tests/e2e_flow_permissions_cas_rewrite_write_target_real_no_injection.py` → Evidence in plan
- REQ-0051-002 → `docs/plan/v51-model-driven-e2e-permissions-cas-interactive.md` → `e2e_tests/e2e_flow_permissions_cas_deny_message_real_no_injection.py` → Evidence in plan
- REQ-0051-003 → `docs/plan/v51-model-driven-e2e-permissions-cas-interactive.md` → `e2e_tests/e2e_flow_permissions_prompt_interactive_denies_real_no_injection.py` → Evidence in plan
- REQ-0051-004 → `docs/plan/v51-model-driven-e2e-permissions-cas-interactive.md` → `e2e_tests/e2e_flow_permissions_prompt_interactive_allows_write_real_no_injection.py` → Evidence in plan
- REQ-0051-005 → `docs/plan/v51-model-driven-e2e-permissions-cas-interactive.md` → `e2e_tests/core_flows_hil.py` + `.openagentic_e2e_reports/...` → Evidence in plan

## ECN

- None
