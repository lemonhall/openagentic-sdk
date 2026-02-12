# v38 Index

## Vision

继续推进“随机层不写死”：扩容 `core_flows` 的真实用户流程覆盖面，让核心模块在真网络抖动下也能被持续回归。

## Milestones

- **M1: Model-driven core_flows expansion v38**
  - Plan: `docs/plan/v38-model-driven-e2e-core-flows-expansion.md`
  - PRD: `docs/prd/PRD-0038-model-driven-e2e-core-flows-expansion-v38.md`
  - DoD：
    - `python -m unittest -v e2e_tests.core_flows`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 2`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0038-001 → `docs/plan/v38-model-driven-e2e-core-flows-expansion.md` → `e2e_tests/e2e_flow_*.py` → Evidence in plan
- REQ-0038-002 → `docs/plan/v38-model-driven-e2e-core-flows-expansion.md` → `e2e_tests/core_flows.py` → Evidence in plan
- REQ-0038-003 → `docs/plan/v38-model-driven-e2e-core-flows-expansion.md` → `.openagentic_e2e_reports/...` → Evidence in plan

## ECN

- None
