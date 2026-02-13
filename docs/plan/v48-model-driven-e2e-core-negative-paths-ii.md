# v48 Plan — Model-Driven E2E (Core Negative Paths II)（模型驱动 E2E：核心负路径 II）

## Goal

补齐核心模块 tools/hooks/tool-loop 的负路径真网络回归证据（no injection）：

- `allowed_tools` 拒绝时：ToolNotAllowed，且不落盘
- hook block 时：HookBlocked，且不落盘
- `Read` missing：FileNotFoundError
- `Edit` old mismatch：ValueError + 文件不变

## PRD Trace

- REQ-0048-001..005（见 PRD-0048）

## Scope

做：

- 新增 4 条 `e2e_flow_*.py`（真实网络、no injection、硬证据断言）
- 更新 `core_flows_tools` suite
- 实跑 DoD 并写回 Evidence

不做：

- 不动 PTY/ConPTY
- 不扩大到 Gateway/MCP
- 不做 resume 坏日志/截断恢复（下一版）

## Acceptance (DoD)

必须全部满足：

- `python -m unittest -v e2e_tests.core_flows_tools` exit code=0
- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_tools --runs 3 --min-pass-rate 0.8 --rerun-failures 1` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-13
- Env: Windows + PowerShell, real-network provider via `e2e_tests/_harness.py`（dotenv supported）
- Commands + Results:
  - `python -m unittest -v e2e_tests.core_flows_tools` → exit code=0
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_tools --runs 3 --min-pass-rate 0.8 --rerun-failures 1 --include-history`
    - Verdict: pass (Pass rate=1.000, Gate>=0.800)
    - Report:
      - `.openagentic_e2e_reports/20260213T003501Z-e2e_tests.core_flows_tools-pid4248/run_report.md`
      - `.openagentic_e2e_reports/20260213T003501Z-e2e_tests.core_flows_tools-pid4248/run_report.json`
- Reports:
  - `.openagentic_e2e_reports/20260213T003501Z-e2e_tests.core_flows_tools-pid4248/`
