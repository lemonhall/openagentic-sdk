# v31 Plan — Model-Driven E2E (Core Flows Stability)（模型驱动 E2E：核心流程稳定性收敛）

## Goal

继续压低 `core_flows` 的噪声：不把用例写死，但把断言锚到更强证据，并让 runner triage 更可用。

## PRD Trace

- REQ-0031-001
- REQ-0031-002

## Scope

做：

- 修改 `e2e_hooks_pre_tool_use_rewrite_read_real_no_injection`：从 `final_text` 改为断言 Read 的 `tool.result.output`
- 增强 runner triage：补充常见“未触发/未重写/未按步骤”类失败关键字归为 `model`
- 实跑单测 + runner，并写回 Evidence

不做：

- 不把 `core_flows` 的用例改 injected
- 不改 smoke_core 的门禁口径

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.e2e_hooks_pre_tool_use_rewrite_read_real_no_injection` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- `python -m unittest -v e2e_tests.e2e_hooks_pre_tool_use_rewrite_read_real_no_injection` → OK（1 test, 36.623s）
- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8` → OK（Runs=5, Passes=5, pass_rate=1.000）
- Report dir: `.openagentic_e2e_reports/20260212T040109Z-e2e_tests.core_flows-pid32600/`
