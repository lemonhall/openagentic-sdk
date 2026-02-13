# v33 Plan — Model-Driven E2E (Metamorphic / Relation Assertions)（模型驱动 E2E：变形测试/关系断言）

## Goal

把 `core_flows` 的随机层测试做得“更聪明”而不是“更死”：

- 增加 1 条 metamorphic 用例：同一意图不同 prompt 变体 → 断言硬证据关系成立
- runner 输出 gate budget，并支持可选 history 趋势

## PRD Trace

- REQ-0033-001
- REQ-0033-002

## Scope

做：

- 新增 `e2e_tests/e2e_metamorphic_ask_user_write_read_variants_real_no_injection.py`
- `e2e_tests/core_flows.py` 引用该模块
- runner：输出 required_passes/allowed_failures；可选 history（最近 N 次同 suite）
- 更新 skill 文档（metamorphic 模板说明）
- 实跑并写回 Evidence

不做：

- 不把用例改 injected
- 不改变 smoke_core 门禁口径

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.e2e_metamorphic_ask_user_write_read_variants_real_no_injection` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 1` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- `python -m unittest -v e2e_tests.e2e_metamorphic_ask_user_write_read_variants_real_no_injection` → OK（1 test, 22.645s）
- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 1` → OK（Runs=5, Passes=5, pass_rate=1.000）
- Report dir: `.openagentic_e2e_reports/20260212T050442Z-e2e_tests.core_flows-pid44260/`
