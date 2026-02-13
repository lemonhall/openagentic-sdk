# v31 Index

## Vision

进一步夯实 `core_flows` 随机层：把断言尽量锚到 tool 证据，并让 runner triage 更贴近实际。

## Milestones

- **M1: Model-driven e2e core flows stability v31**
  - Plan: `docs/plan/v31-model-driven-e2e-core-flows-stability.md`
  - PRD: `docs/prd/PRD-0031-model-driven-e2e-core-flows-stability-v31.md`
  - DoD：
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0031-001 → `docs/plan/v31-model-driven-e2e-core-flows-stability.md` → `e2e_tests/e2e_hooks_pre_tool_use_rewrite_read_real_no_injection.py` → Evidence in plan
- REQ-0031-002 → `docs/plan/v31-model-driven-e2e-core-flows-stability.md` → `scripts/model_driven_e2e.py` → Evidence in plan

## ECN

- None
