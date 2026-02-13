# v26 Index

## Vision

让核心 SDK 的真实网络回归更“可高频”：

- 一条命令跑 smoke（2–3 分钟）
- 覆盖 core pillars：provider / sessions / permissions / tool loop / security

## Milestones

- **M1: Real-network core smoke set v26**
  - Plan: `docs/plan/v26-real-network-e2e-core-smoke-set.md`
  - PRD: `docs/prd/PRD-0026-real-network-e2e-core-smoke-set-v26.md`
  - DoD：
    - `python -m unittest -v e2e_tests.smoke_core`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0026-001 → `docs/plan/v26-real-network-e2e-core-smoke-set.md` → `e2e_tests/smoke_core.py` → Evidence in plan
- REQ-0026-002 → `docs/plan/v26-real-network-e2e-core-smoke-set.md` → `e2e_tests/smoke_core.py` → Evidence in plan

## Smoke Command（非 full 回归）

- `python -m unittest -v e2e_tests.smoke_core`

## ECN

- None
