# v51 Plan — Model-Driven E2E (Permissions: CAS + Interactive)（模型驱动 E2E：权限 CAS + 交互审批）

## Goal

补齐 PermissionGate 两个关键分支的真网络 no-injection 回归证据：

- CAS（can_use_tool）：allow + updated_input / deny + message
- interactive prompt：deny / allow（无 user.question）

## PRD Trace

- REQ-0051-001..005（见 PRD-0051）

## Scope

做：

- 新增 4 条 `e2e_flow_*.py`（真实网络、no injection、硬证据断言）
- 更新 `core_flows_hil` suite
- 实跑 DoD 并写回 Evidence

不做：

- 不动 PTY/ConPTY
- 不扩大到 Gateway/MCP

## Acceptance (DoD)

必须全部满足：

- `python -m unittest -v e2e_tests.core_flows_hil` exit code=0
- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-13
- Env: Windows + PowerShell, real-network provider via `e2e_tests/_harness.py`（dotenv supported）
- Commands + Results:
  - `python -m unittest -v e2e_tests.core_flows_hil` → exit code=0
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1 --include-history`
    - Verdict: pass (Pass rate=1.000, Gate>=0.800)
    - Report:
      - `.openagentic_e2e_reports/20260213T020227Z-e2e_tests.core_flows_hil-pid45776/run_report.md`
      - `.openagentic_e2e_reports/20260213T020227Z-e2e_tests.core_flows_hil-pid45776/run_report.json`
- Reports:
  - `.openagentic_e2e_reports/20260213T020227Z-e2e_tests.core_flows_hil-pid45776/`
