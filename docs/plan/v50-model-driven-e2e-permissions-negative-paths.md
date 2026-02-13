# v50 Plan — Model-Driven E2E (Permissions Negative Paths)（模型驱动 E2E：权限负路径）

## Goal

补齐 PermissionGate 的关键负路径组合真网络回归证据（no injection）：

- prompt 模式缺少 user_answerer：必须 prompt + 拒绝 + 不落盘
- callback approver 抛错：必须拒绝且行为稳定
- acceptEdits 边界：非编辑工具仍需 prompt，可被拒绝

## PRD Trace

- REQ-0050-001..004（见 PRD-0050）

## Scope

做：

- 新增 3 条 `e2e_flow_*.py`（真实网络、no injection、硬证据断言）
- 必要时对 PermissionGate 做最小修正（让 callback 抛错也转为拒绝）
- 更新 `core_flows_hil` / `core_flows_sessions` suite
- 实跑 DoD 并写回 Evidence

不做：

- 不动 PTY/ConPTY
- 不扩大到 Gateway/MCP

## Acceptance (DoD)

必须全部满足：

- `python -m unittest -v e2e_tests.core_flows_hil` exit code=0
- `python -m unittest -v e2e_tests.core_flows_sessions` exit code=0
- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1` exit code=0
- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-13
- Env: Windows + PowerShell, real-network provider via `e2e_tests/_harness.py`（dotenv supported）
- Commands + Results:
  - `python -m unittest -v e2e_tests.core_flows_hil` → exit code=0
  - `python -m unittest -v e2e_tests.core_flows_sessions` → exit code=0
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1 --include-history`
    - Verdict: pass (Pass rate=1.000, Gate>=0.800)
    - Report:
      - `.openagentic_e2e_reports/20260213T014108Z-e2e_tests.core_flows_hil-pid43764/run_report.md`
      - `.openagentic_e2e_reports/20260213T014108Z-e2e_tests.core_flows_hil-pid43764/run_report.json`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1 --include-history`
    - Verdict: pass (Pass rate=1.000, Gate>=0.800)
    - Report:
      - `.openagentic_e2e_reports/20260213T014108Z-e2e_tests.core_flows_sessions-pid57568/run_report.md`
      - `.openagentic_e2e_reports/20260213T014108Z-e2e_tests.core_flows_sessions-pid57568/run_report.json`
- Reports:
  - `.openagentic_e2e_reports/20260213T014108Z-e2e_tests.core_flows_hil-pid43764/`
  - `.openagentic_e2e_reports/20260213T014108Z-e2e_tests.core_flows_sessions-pid57568/`
