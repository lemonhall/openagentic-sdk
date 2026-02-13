# v48 Index

## Vision

继续把核心模块（tools/hooks/tool-loop）的负路径跑实：工具白名单拒绝、hook block、Read/Edit 常见错误输入都要有真网络 no-injection 证据。

## Milestones

- **M1: core negative paths II v48**
  - Plan: `docs/plan/v48-model-driven-e2e-core-negative-paths-ii.md`
  - PRD: `docs/prd/PRD-0048-model-driven-e2e-core-negative-paths-ii-v48.md`
  - DoD：
    - `python -m unittest -v e2e_tests.core_flows_tools`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_tools --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
  - Status: done (2026-02-13)

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0048-001 → `docs/plan/v48-model-driven-e2e-core-negative-paths-ii.md` → `e2e_tests/e2e_flow_tools_write_outside_project_root_denied_real_no_injection.py` → Evidence in plan
- REQ-0048-002 → `docs/plan/v48-model-driven-e2e-core-negative-paths-ii.md` → `e2e_tests/e2e_flow_hooks_pre_tool_use_block_write_hook_blocked_real_no_injection.py` → Evidence in plan
- REQ-0048-003 → `docs/plan/v48-model-driven-e2e-core-negative-paths-ii.md` → `e2e_tests/e2e_flow_tools_read_missing_file_real_no_injection.py` → Evidence in plan
- REQ-0048-004 → `docs/plan/v48-model-driven-e2e-core-negative-paths-ii.md` → `e2e_tests/e2e_flow_tools_edit_old_mismatch_real_no_injection.py` → Evidence in plan
- REQ-0048-005 → `docs/plan/v48-model-driven-e2e-core-negative-paths-ii.md` → `e2e_tests/core_flows_tools.py` + `.openagentic_e2e_reports/...` → Evidence in plan

## ECN

- None
