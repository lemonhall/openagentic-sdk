# v40 Plan — Model-Driven E2E (Sessions + Hooks Expansion)（模型驱动 E2E：会话与 Hooks 扩容）

## Goal

扩容随机层（no injection）的核心组合流程覆盖面：

- `core_flows_sessions`：resume×permissions×prune
- `core_flows_hil`：新增 hooks 真实流程用例（post_tool_use 改写）

并分别跑 suite gate 留证据。

## PRD Trace

- REQ-0040-001..005（见 PRD-0040）

## Scope

做：

- 新增 4 条 `e2e_flow_*.py`（真实网络、no injection）
- 更新 `core_flows_sessions` / `core_flows_hil` suite
- 实跑 DoD 并写回 Evidence

不做：

- 不动 PTY/ConPTY
- 不扩大到 Gateway/MCP

## Acceptance (DoD)

必须全部满足：

- `python -m unittest -v e2e_tests.core_flows_sessions` exit code=0
- `python -m unittest -v e2e_tests.core_flows_hil` exit code=0
- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1` exit code=0
- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- Env: Windows + PowerShell, real-network provider via `e2e_tests/_harness.py`（dotenv supported）
- Commands + Results:
  - `python -m unittest -v e2e_tests.core_flows_sessions` → OK（5 tests, 64.396s）
  - `python -m unittest -v e2e_tests.core_flows_hil` → OK（9 tests, 123.801s）
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1` → pass（Runs=3, Passes=3）
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1` → pass（Runs=3, Passes=3）
- Reports:
  - `.openagentic_e2e_reports/20260212T080720Z-e2e_tests.core_flows_sessions-pid12604/`
  - `.openagentic_e2e_reports/20260212T080720Z-e2e_tests.core_flows_hil-pid41752/`
