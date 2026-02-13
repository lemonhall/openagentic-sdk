# v36 Plan — Core Hard-Invariants E2E Density（核心硬不变量 E2E 密度提升）

## Goal

继续用 injected + 硬断言堆核心模块的 hard-invariants 覆盖面，避免“光抽象不落地”。

本轮聚焦：

- Tools：`List` 的 limit/truncated 与 ignore；`Edit` old-not-found；`Write` content 类型校验
- Permissions：`default` safe tools 不 prompt；`acceptEdits` 对非 edit 工具 prompt 且 deny 生效

并产出稳定聚合套件 `core_matrix_v36`。

## PRD Trace

- REQ-0036-001..007（见 PRD-0036）

## Scope

做：

- 新增 6 条 injected 真网络 E2E（硬断言）
- 新增 `e2e_tests/core_matrix_v36.py` 聚合套件（包含 v35 + v36）
- 更新覆盖矩阵映射
- 跑 DoD 命令并记录证据

不做：

- 不动 PTY/ConPTY
- 不扩大到 Gateway/MCP

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.core_matrix_v36` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix_v36 --runs 3 --min-pass-rate 1.0` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- Env: Windows + PowerShell, real-network provider via `e2e_tests/_harness.py`（dotenv supported）
- Command 1: `python -m unittest -v e2e_tests.core_matrix_v36`
- Command 2: `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix_v36 --runs 3 --min-pass-rate 1.0`
- Result:
  - `python -m unittest -v e2e_tests.core_matrix_v36` → OK（11 tests, 91.386s）
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix_v36 --runs 3 --min-pass-rate 1.0` → pass（Runs=3, Passes=3, pass_rate=1.000）
- Report dir: `.openagentic_e2e_reports/20260212T061340Z-e2e_tests.core_matrix_v36-pid38316/`

## Steps（Strict）

1) Red：写 6 条 injected E2E（tool.result + 磁盘产物硬断言）
2) Green：必要时修复工具/权限语义 bug
3) Verify：跑 DoD 并写回 Evidence
