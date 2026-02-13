# v30 Index

## Vision

把真网络 E2E 分成“两车道”：

- `smoke_core`：hard invariants 门禁（pass-rate=1.0）
- `core_flows`：随机层用户流程（pass-rate 门禁 + 失败归因）

## Milestones

- **M1: Model-driven e2e core flows suite v30**
  - Plan: `docs/plan/v30-model-driven-e2e-core-flows-suite.md`
  - PRD: `docs/prd/PRD-0030-model-driven-e2e-core-flows-suite-v30.md`
  - DoD：
    - `python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0030-001 → `docs/plan/v30-model-driven-e2e-core-flows-suite.md` → `e2e_tests/core_flows.py` → Evidence in plan
- REQ-0030-002 → `docs/plan/v30-model-driven-e2e-core-flows-suite.md` → `AGENTS.md` / `scripts/model_driven_e2e.py` → Evidence in plan
- REQ-0030-003 → `docs/plan/v30-model-driven-e2e-core-flows-suite.md` → `AGENTS.md` → Evidence in plan

## ECN

- None
