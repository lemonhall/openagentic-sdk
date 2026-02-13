# PRD-0029 — Real-Network E2E (Smoke Stability via Injected Toolcalls v29)（真实网络 E2E：通过注入 toolcalls 提升 smoke 稳定性 v29）

## Vision

让核心 smoke 更“像门禁”：

- 仍然是**真网络**（每步仍会调用真实 provider）
- 但对最容易抖的流程（多次 permission prompt、错误恢复链）减少对模型规划的依赖
- 让失败更可解释：更偏“协议/权限/工具循环/落盘”的证据，而不是“模型没按步骤走”

## Non-Goals

- 不替代全量 `e2e_tests`（完整回归仍保留 model-driven 的用户流程测试）。
- 不测试 Gateway/MCP。
- 不测试 CLI PTY/ConPTY（另有人负责）。

## Requirements

### REQ-0029-001 — Stabilize prompt deny→allow smoke path

在 smoke 集中，用 injected toolcalls 的方式稳定验证：

- `PermissionGate(permission_mode="prompt")` 能产生至少 2 次 `user.question`
- 第一次 Write 被拒绝（`tool.result is_error=True` 且 `error_type="PermissionDenied"`）
- 第二次 Write 被允许并落盘（文件存在且包含 token）

### REQ-0029-002 — Stabilize tool-loop error recovery smoke path

在 smoke 集中，用 injected toolcalls 的方式稳定验证：

- 先 Read 一个不存在文件，产生非 PermissionDenied 的错误 tool.result
- 随后 Write 创建文件并 Read 回读
- 断言磁盘状态与关键 tool events

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.smoke_core` exit code=0
2) smoke 中对应两条用例改为 injected 版本（仍真网络）
3) `python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0` exit code=0

