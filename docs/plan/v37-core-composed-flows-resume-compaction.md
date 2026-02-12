# v37 Plan — Core Composed Flows (Resume + Compaction)（核心组合流程：恢复 + 压缩修剪）

## Goal

补齐“组合流程”的 hard-invariants 真网络 E2E：

- resume × permissions(prompt)：deny → allow
- resume × hooks(post_tool_use block)：block → unblock
- prune × resume × tools：prune 后仍可继续 Read

并把这些用例与既有 hard-invariants 一起收敛到 `core_matrix_v37` 稳定套件。

## PRD Trace

- REQ-0037-001..004（见 PRD-0037）

## Scope

做：

- 新增 3 条 injected 真网络 E2E（组合流程、硬断言）
- 新增 `e2e_tests/core_matrix_v37.py` 聚合套件（包含 v36 + v37）
- 更新覆盖矩阵映射
- 跑 DoD 命令并记录证据

不做：

- 不动 PTY/ConPTY
- 不扩大到 Gateway/MCP

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.core_matrix_v37` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix_v37 --runs 3 --min-pass-rate 1.0` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- Env: Windows + PowerShell, real-network provider via `e2e_tests/_harness.py`（dotenv supported）
- Command 1: `python -m unittest -v e2e_tests.core_matrix_v37`
- Command 2: `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix_v37 --runs 3 --min-pass-rate 1.0`
- Result:
  - `python -m unittest -v e2e_tests.core_matrix_v37` → OK（14 tests, 145.244s）
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix_v37 --runs 3 --min-pass-rate 1.0` → pass（Runs=3, Passes=3, pass_rate=1.000）
- Report dir: `.openagentic_e2e_reports/20260212T063421Z-e2e_tests.core_matrix_v37-pid43048/`

## Steps（Strict）

1) Red：写 3 条组合流程 injected E2E（以 events.jsonl + tool.result + 磁盘产物做硬断言）
2) Green：必要时修复 resume/compaction 的行为 bug
3) Verify：跑 DoD 并写回 Evidence
