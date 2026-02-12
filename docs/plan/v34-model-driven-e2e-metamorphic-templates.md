# v34 Plan — Model-Driven E2E (Metamorphic Templates)（模型驱动 E2E：关系断言模板）

## Goal

把 `core_flows` 中 2 条核心用例改造成 metamorphic/关系断言模板：同一意图多 prompt 变体 → 断言同一组硬证据成立，以降低脆弱性。

## PRD Trace

- REQ-0034-001
- REQ-0034-002

## Scope

做：

- 新增：
  - `e2e_tests/e2e_metamorphic_edit_variants_real_no_injection.py`
  - `e2e_tests/e2e_metamorphic_perm_default_edit_variants_real_no_injection.py`
- 更新 `e2e_tests/core_flows.py`：用上述 2 条替换原 `tools_edit_roundtrip` 与 `permissions_default_prompts_edit`
- 更新 `skills/model-driven-e2e/SKILL.md`：增加模板指引与示例引用
- 实跑并写回 Evidence

不做：

- 不改变 `smoke_core` 的 hard gate 口径
- 不把 core_flows 变 injected

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.core_flows` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 1` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- `python -m unittest -v e2e_tests.core_flows` → OK（7 tests, 119.995s）
- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 1` → OK（Runs=5, Passes=5, pass_rate=1.000）
- Report dir: `.openagentic_e2e_reports/20260212T052125Z-e2e_tests.core_flows-pid26640/`
