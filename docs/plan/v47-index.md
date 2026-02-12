# v47 Index

## Vision

把核心模块的负路径（permissions/hooks/sessions）做硬：拒绝/越界/膨胀风险都必须有真网络 no-injection 的回归证据。

## Milestones

- **M1: core negative paths v47**
  - Plan: `docs/plan/v47-model-driven-e2e-core-negative-paths.md`
  - PRD: `docs/prd/PRD-0047-model-driven-e2e-core-negative-paths-v47.md`
  - DoD：
    - `python -m unittest -v e2e_tests.core_flows_sessions`
    - `python -m unittest -v e2e_tests.core_flows_hil`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
  - Status: done (2026-02-12)

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0047-001 → `docs/plan/v47-model-driven-e2e-core-negative-paths.md` → `e2e_tests/e2e_flow_perm_default_write_denied_real_no_injection.py` → Evidence in plan
- REQ-0047-002 → `docs/plan/v47-model-driven-e2e-core-negative-paths.md` → `e2e_tests/e2e_flow_hooks_pre_tool_use_rewrite_write_traversal_blocked_real_no_injection.py` → Evidence in plan
- REQ-0047-003 → `docs/plan/v47-model-driven-e2e-core-negative-paths.md` → `e2e_tests/e2e_flow_sessions_events_exclude_assistant_delta_real_no_injection.py` → Evidence in plan
- REQ-0047-004 → `docs/plan/v47-model-driven-e2e-core-negative-paths.md` → `e2e_tests/core_flows_hil.py` + `e2e_tests/core_flows_sessions.py` + `.openagentic_e2e_reports/...` → Evidence in plan

## ECN

- None
