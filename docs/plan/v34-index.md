# v34 Index

## Vision

继续推进“随机层不写死”：将 core_flows 的关键用例抽象成 metamorphic/关系断言模板，降低对 prompt/措辞的敏感性。

## Milestones

- **M1: Model-driven e2e metamorphic templates v34**
  - Plan: `docs/plan/v34-model-driven-e2e-metamorphic-templates.md`
  - PRD: `docs/prd/PRD-0034-model-driven-e2e-metamorphic-templates-v34.md`
  - DoD：
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 1`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0034-001 → `docs/plan/v34-model-driven-e2e-metamorphic-templates.md` → `e2e_tests/e2e_metamorphic_edit_variants_real_no_injection.py` → Evidence in plan
- REQ-0034-002 → `docs/plan/v34-model-driven-e2e-metamorphic-templates.md` → `e2e_tests/e2e_metamorphic_perm_default_edit_variants_real_no_injection.py` → Evidence in plan

## ECN

- None
