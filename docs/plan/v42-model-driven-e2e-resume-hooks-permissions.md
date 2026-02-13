# v42 Plan — Model-Driven E2E (Resume × Hooks × Permissions)（模型驱动 E2E：恢复×Hooks×权限）

## Goal

继续加厚随机层 sessions/hil 的组合流程覆盖面（no injection）：

- sessions：resume×acceptEdits、resume×post_tool_use override
- hil：pre_tool_use rewrite Write、default safe Read no prompt

并分别跑 suite gate 留证据。

## PRD Trace

- REQ-0042-001..005（见 PRD-0042）

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
  - `python -m unittest -v e2e_tests.core_flows_sessions` → exit code=0
  - `python -m unittest -v e2e_tests.core_flows_hil` → exit code=0
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1 --include-history`
    - Verdict: pass (Pass rate=1.000, Gate>=0.800)
    - Report:
      - `.openagentic_e2e_reports/20260212T100745Z-e2e_tests.core_flows_sessions-pid21400/run_report.md`
      - `.openagentic_e2e_reports/20260212T100745Z-e2e_tests.core_flows_sessions-pid21400/run_report.json`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1 --include-history`
    - Verdict: pass (Pass rate=1.000, Gate>=0.800)
    - Report:
      - `.openagentic_e2e_reports/20260212T101224Z-e2e_tests.core_flows_hil-pid45436/run_report.md`
      - `.openagentic_e2e_reports/20260212T101224Z-e2e_tests.core_flows_hil-pid45436/run_report.json`
- Reports:
  - `.openagentic_e2e_reports/20260212T100745Z-e2e_tests.core_flows_sessions-pid21400/`
  - `.openagentic_e2e_reports/20260212T101224Z-e2e_tests.core_flows_hil-pid45436/`
