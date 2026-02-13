# v47 Plan — Model-Driven E2E (Core Negative Paths)（模型驱动 E2E：核心负路径）

## Goal

补齐核心模块的负路径真网络回归证据（no injection）：

- permissions：default 下 Write 被拒绝，不得落盘
- hooks：pre_tool_use 恶意/误改路径不得越界写盘
- sessions：`events.jsonl` 永不落 `assistant.delta`，避免会话膨胀

## PRD Trace

- REQ-0047-001..004（见 PRD-0047）

## Scope

做：

- 新增 3 条 `e2e_flow_*.py`（真实网络、no injection、硬证据断言）
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
      - `.openagentic_e2e_reports/20260212T112210Z-e2e_tests.core_flows_sessions-pid42964/run_report.md`
      - `.openagentic_e2e_reports/20260212T112210Z-e2e_tests.core_flows_sessions-pid42964/run_report.json`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1 --include-history`
    - Verdict: pass (Pass rate=1.000, Gate>=0.800)
    - Report:
      - `.openagentic_e2e_reports/20260212T112749Z-e2e_tests.core_flows_hil-pid45276/run_report.md`
      - `.openagentic_e2e_reports/20260212T112749Z-e2e_tests.core_flows_hil-pid45276/run_report.json`
- Reports:
  - `.openagentic_e2e_reports/20260212T112210Z-e2e_tests.core_flows_sessions-pid42964/`
  - `.openagentic_e2e_reports/20260212T112749Z-e2e_tests.core_flows_hil-pid45276/`
