# v28 Index

## Vision

把“模型驱动 E2E”（多次运行 + 统计门禁 + 失败归因）固化为核心 smoke 的标准工作流，让真网络回归更智能、更可解释。

## Milestones

- **M1: Model-driven e2e runner (core smoke gate v28)**
  - Plan: `docs/plan/v28-model-driven-e2e-runner-core-smoke-gate.md`
  - PRD: `docs/prd/PRD-0028-model-driven-e2e-runner-v28.md`
  - DoD：
    - `python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0028-001 → `docs/plan/v28-model-driven-e2e-runner-core-smoke-gate.md` → `scripts/model_driven_e2e.py` → Evidence in plan
- REQ-0028-002 → `docs/plan/v28-model-driven-e2e-runner-core-smoke-gate.md` → `scripts/model_driven_e2e.py` → Evidence in plan
- REQ-0028-003 → `docs/plan/v28-model-driven-e2e-runner-core-smoke-gate.md` → `AGENTS.md` / `skills/model-driven-e2e/SKILL.md` → Evidence in plan

## ECN

- None
