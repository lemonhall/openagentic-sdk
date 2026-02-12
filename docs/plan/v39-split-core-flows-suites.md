# v39 Plan — Split core_flows Suites（拆分随机层 core_flows 套件）

## Goal

把随机层 `core_flows` 拆成 3 个主题套件：

- `core_flows_tools`：工具链/网络工具的用户任务型流程
- `core_flows_sessions`：resume/session 的用户流程
- `core_flows_hil`：human-in-the-loop（permissions/hooks/skills/ask_user）

每个套件独立 gate、独立报告；同时保留 `core_flows` 作为聚合入口（向后兼容）。

## PRD Trace

- REQ-0039-001..003（见 PRD-0039）

## Scope

做：

- 新增 `e2e_tests/core_flows_tools.py|core_flows_sessions.py|core_flows_hil.py`
- 更新 `e2e_tests/core_flows.py` 为 umbrella
- 实跑 DoD 并写回证据

不做：

- 不改动任何核心 SDK 行为
- 不动 PTY/ConPTY

## Acceptance (DoD)

必须全部满足：

- `python -m unittest -v e2e_tests.core_flows_tools` exit code=0
- `python -m unittest -v e2e_tests.core_flows_sessions` exit code=0
- `python -m unittest -v e2e_tests.core_flows_hil` exit code=0
- 3 个 suite 的 model-driven gate 均通过（runs=3, min-pass=0.8, rerun-failures=1）

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- Env: Windows + PowerShell, real-network provider via `e2e_tests/_harness.py`（dotenv supported）
- Commands + Results:
  - `python -m unittest -v e2e_tests.core_flows_tools` → OK（7 tests, 67.448s）
  - `python -m unittest -v e2e_tests.core_flows_sessions` → OK（2 tests, 28.790s）
  - `python -m unittest -v e2e_tests.core_flows_hil` → OK（8 tests, 103.751s）
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_tools --runs 3 --min-pass-rate 0.8 --rerun-failures 1` → pass（Runs=3, Passes=3）
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1` → pass（Runs=3, Passes=3）
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1` → pass（Runs=3, Passes=3）
- Reports:
  - `.openagentic_e2e_reports/20260212T073017Z-e2e_tests.core_flows_tools-pid11160/`
  - `.openagentic_e2e_reports/20260212T073343Z-e2e_tests.core_flows_sessions-pid25968/`
  - `.openagentic_e2e_reports/20260212T073500Z-e2e_tests.core_flows_hil-pid32692/`
