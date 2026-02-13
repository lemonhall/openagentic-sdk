# v53 Plan — Offline E2E Hard-Invariants Density（离线 E2E：硬不变量密度提升）

## Goal

在 `e2e_tests_offline/` 扩充一批“脚本化 provider”的离线 E2E，用确定性断言覆盖 runtime/tool-loop/sessions/permissions/hooks/path-security 的关键硬不变量，并把离线 E2E 用例数量提升到 **25–40** 区间。

## PRD Trace

- REQ-0053-001
- REQ-0053-002
- REQ-0053-003
- REQ-0053-004
- REQ-0053-005
- REQ-0053-006
- REQ-0053-007
- REQ-0053-008
- REQ-0053-009
- REQ-0053-010

## Scope

做：
- 新增一批离线 E2E（`e2e_tests_offline/e2e_*.py`），以 scripted provider 注入 `ToolCall` 序列
- 必要时新增极小的测试辅助函数（仅用于解析 `function_call_output`）

不做：
- 不新增第三方依赖
- 不扩展真实网络 E2E（`e2e_tests/`）
- 不覆盖 CLI E2E

## Acceptance (DoD)

必须全部满足：

1) Windows：`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v` exit code=0
2) 测试数量：`Ran N tests` 中 `N` ∈ [25, 40]
3) 离线约束：不读取 `RIGHTCODE_*`、不发真实网络请求

## Evidence（填写为可复现证据）

- Date: 2026-02-13
- Windows：`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v` → OK（28 tests）

## Steps（Strict）

1) Red：为每个硬不变量新增 1 个离线 E2E（provider 先做强断言，确保失败可诊断）
2) Green：补齐最小 fake provider / hooks / permission gate / fixtures，使断言通过
3) Verify：运行离线 E2E discover 并确认测试数量落在 25–40
4) 写回 Evidence，并更新 `docs/plan/v53-index.md` 的状态与差异
