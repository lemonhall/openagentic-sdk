# v42 Index

## Vision

继续加厚随机层的“组合流程”覆盖面：围绕 resume×hooks×permissions 添加 no-injection 用户流程证据，并分别守住 sessions/hil 两条 suite 的统计门禁。

## Milestones

- **M1: resume×hooks×permissions v42**
  - Plan: `docs/plan/v42-model-driven-e2e-resume-hooks-permissions.md`
  - PRD: `docs/prd/PRD-0042-model-driven-e2e-resume-hooks-permissions-v42.md`
  - DoD：
    - `python -m unittest -v e2e_tests.core_flows_sessions`
    - `python -m unittest -v e2e_tests.core_flows_hil`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
  - Status: done (2026-02-12)

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0042-001 → `docs/plan/v42-model-driven-e2e-resume-hooks-permissions.md` → `e2e_tests/e2e_flow_resume_accept_edits_edit_then_read_real_no_injection.py` → Evidence in plan
- REQ-0042-002 → `docs/plan/v42-model-driven-e2e-resume-hooks-permissions.md` → `e2e_tests/e2e_flow_resume_post_tool_use_override_read_redacted_real_no_injection.py` → Evidence in plan
- REQ-0042-003 → `docs/plan/v42-model-driven-e2e-resume-hooks-permissions.md` → `e2e_tests/e2e_flow_hooks_pre_tool_use_rewrite_write_path_real_no_injection.py` → Evidence in plan
- REQ-0042-004 → `docs/plan/v42-model-driven-e2e-resume-hooks-permissions.md` → `e2e_tests/e2e_flow_perm_default_read_no_prompt_real_no_injection.py` → Evidence in plan
- REQ-0042-005 → `docs/plan/v42-model-driven-e2e-resume-hooks-permissions.md` → `e2e_tests/core_flows_sessions.py` + `e2e_tests/core_flows_hil.py` + `.openagentic_e2e_reports/...` → Evidence in plan

## ECN

- None
