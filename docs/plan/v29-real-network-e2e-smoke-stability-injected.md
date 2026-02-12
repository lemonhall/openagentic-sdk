# v29 Plan — Real-Network E2E (Smoke Stability via Injected Toolcalls)（真实网络 E2E：注入 toolcalls 提升 smoke 稳定性）

## Goal

把 smoke 集里最依赖“模型自觉按步骤走”的 2 条用例，替换为 injected toolcalls 版本：仍走真网络 provider，但让工具链与权限/错误恢复链路更稳定、回归信号更纯。

## PRD Trace

- REQ-0029-001
- REQ-0029-002

## Scope

做：

- 新增 2 条 injected 版 e2e（仍真网络）：
  - deny→allow（permission prompt）
  - read-missing→write→read（error recovery）
- 更新 `e2e_tests/smoke_core.py`：smoke 引用 injected 版本
- 实跑 smoke + model-driven runner，并写回 Evidence

不做：

- 不删除原来的 model-driven 用例（全量回归仍保留）
- 不动 CLI PTY/ConPTY
- 不动 MCP/Gateway

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.smoke_core` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- `python -m unittest -v e2e_tests.smoke_core` → OK（11 tests, 97.119s）
- `python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0` → OK（Runs=3, Passes=3, pass_rate=1.000）
- Report dir: `.openagentic_e2e_reports/20260212T031259Z/`

## Steps（Strict）

1) Red：写 PRD/Plan，明确替换范围与 DoD
2) Green：新增 injected 版用例并接入 smoke
3) Verify：Windows/PowerShell 实跑 smoke 与 runner，并写回 Evidence
