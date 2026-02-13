# v33 Index

## Vision

继续夯实随机层 `core_flows`：引入 metamorphic/关系断言用例，减少对唯一文本输出的依赖；同时让 runner 报告包含 gate budget 与可选历史趋势。

## Milestones

- **M1: Model-driven e2e metamorphic v33**
  - Plan: `docs/plan/v33-model-driven-e2e-metamorphic.md`
  - PRD: `docs/prd/PRD-0033-model-driven-e2e-metamorphic-v33.md`
  - DoD：
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 1`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0033-001 → `docs/plan/v33-model-driven-e2e-metamorphic.md` → `e2e_tests/e2e_metamorphic_ask_user_write_read_variants_real_no_injection.py` → Evidence in plan
- REQ-0033-002 → `docs/plan/v33-model-driven-e2e-metamorphic.md` → `scripts/model_driven_e2e.py` → Evidence in plan

## ECN

- None
