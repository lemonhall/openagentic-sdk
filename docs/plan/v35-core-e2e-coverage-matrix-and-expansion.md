# v35 Plan — Core E2E Coverage Matrix + Expansion（核心 E2E 覆盖矩阵 + 扩容）

## Goal

以覆盖矩阵为锚点，新增一批稳定（hard invariants）的真网络 E2E，用 injected + 硬断言把核心模块缺口先补齐一轮：

- Tools：补 `List`（树输出 + 路径边界）
- Runtime Core：补 `allowed_tools` gate（ToolNotAllowed）
- Permissions：补 `callback` deterministic deny→allow
- Hooks：补 post-tool-use block 语义

## PRD Trace

- REQ-0035-001..007（见 PRD-0035）

## Scope

做：

- 新增覆盖矩阵：`docs/guides/core-e2e-coverage-matrix.md`
- 新增稳定套件入口：`e2e_tests/core_matrix.py`
- 新增 5 条 injected 真网络 E2E（硬断言）
- 修复 `List` 工具路径边界（与 `resolve_tool_path` 对齐）

不做：

- 不改动 PTY/ConPTY 相关代码
- 不扩大到 Gateway/MCP
- 不把随机层 `core_flows` 全部 injected

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.core_matrix` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix --runs 3 --min-pass-rate 1.0` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- Env: Windows + PowerShell, real-network provider via `e2e_tests/_harness.py`（dotenv supported）
- Command 1: `python -m unittest -v e2e_tests.core_matrix`
- Command 2: `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix --runs 3 --min-pass-rate 1.0`
- Result:
  - `python -m unittest -v e2e_tests.core_matrix` → OK（5 tests, 41.598s）
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix --runs 3 --min-pass-rate 1.0` → pass（Runs=3, Passes=3, pass_rate=1.000）
- Report dir: `.openagentic_e2e_reports/20260212T055753Z-e2e_tests.core_matrix-pid41184/`

## Steps（Strict）

1) Red：按覆盖矩阵缺口写 injected E2E（每条都以 tool.result + 磁盘产物做硬断言）
2) Green：补齐 `List` 工具路径边界（让 security E2E 通过）
3) Verify：跑 DoD 命令并写回 Evidence
