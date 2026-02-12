# v38 Plan — Model-Driven E2E (Core Flows Expansion)（模型驱动 E2E：核心流程扩容）

## Goal

扩容随机层 `core_flows`，用更多“用户任务型流程”覆盖核心模块，同时保持断言口径偏硬（tool/result + 落盘证据），并通过 model-driven gate 吸收抖动。

## PRD Trace

- REQ-0038-001..003（见 PRD-0038）

## Scope

做：

- 新增 ≥10 条 `e2e_flow_*.py`（真实网络、no injection）
- 更新 `e2e_tests/core_flows.py` 纳入新增用例
- 实跑 DoD 命令并写回 Evidence

不做：

- 不动 PTY/ConPTY
- 不扩大到 Gateway/MCP

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.core_flows` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 2` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- Env: Windows + PowerShell, real-network provider via `e2e_tests/_harness.py`（dotenv supported）
- Command 1: `python -m unittest -v e2e_tests.core_flows`
- Command 2: `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 2`
- Result:
  - `python -m unittest -v e2e_tests.core_flows` → OK（17 tests, 186.486s）
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 2` → pass（Runs=5, Passes=5, pass_rate=1.000）
- Report dir: `.openagentic_e2e_reports/20260212T070158Z-e2e_tests.core_flows-pid36852/`

## Steps（Strict）

1) Red：写新增 core_flows 用例（多用关系断言/磁盘产物，少依赖唯一 final_text）
2) Green：根据失败归因（network/model/regression）调整 prompt/断言
3) Verify：跑 DoD 并写回 Evidence
