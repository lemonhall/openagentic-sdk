# v39 Index

## Vision

把随机层 `core_flows` 拆分成 3 个主题套件（tools / sessions / HIL），让 e2e 更易跑、更易守门、更易定位失败。

## Milestones

- **M1: Split core_flows suites v39**
  - Plan: `docs/plan/v39-split-core-flows-suites.md`
  - PRD: `docs/prd/PRD-0039-split-core-flows-suites-v39.md`
  - DoD：
    - `python -m unittest -v e2e_tests.core_flows_tools`
    - `python -m unittest -v e2e_tests.core_flows_sessions`
    - `python -m unittest -v e2e_tests.core_flows_hil`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_tools --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0039-001 → `docs/plan/v39-split-core-flows-suites.md` → `e2e_tests/core_flows_*.py` → Evidence in plan
- REQ-0039-002 → `docs/plan/v39-split-core-flows-suites.md` → `e2e_tests/core_flows.py` → Evidence in plan
- REQ-0039-003 → `docs/plan/v39-split-core-flows-suites.md` → `.openagentic_e2e_reports/...` → Evidence in plan

## ECN

- None
