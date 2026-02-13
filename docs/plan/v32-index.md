# v32 Index

## Vision

让 model-driven runner 更像“智能门禁助手”：失败时自动 rerun 失败项，区分 flake vs persistent，提升 triage 与回归信号质量。

## Milestones

- **M1: Model-driven e2e runner rerun v32**
  - Plan: `docs/plan/v32-model-driven-e2e-runner-rerun.md`
  - PRD: `docs/prd/PRD-0032-model-driven-e2e-runner-rerun-v32.md`
  - DoD：
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 1`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0032-001 → `docs/plan/v32-model-driven-e2e-runner-rerun.md` → `scripts/model_driven_e2e.py` → Evidence in plan
- REQ-0032-002 → `docs/plan/v32-model-driven-e2e-runner-rerun.md` → `scripts/model_driven_e2e.py` → Evidence in plan

## ECN

- None
