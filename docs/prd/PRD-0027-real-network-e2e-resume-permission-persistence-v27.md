# PRD-0027 — Real-Network E2E (Resume + Permission Persistence v27)（真实网络 E2E：Resume + 权限持久化 v27）

## Vision

把一个真实用户会遇到的核心流程做成**可回归证据**：

- 第 1 次运行：触发 `PermissionGate` 询问并允许（`user.question` → answer yes）→ `Write` 成功落盘
- 第 2 次运行：使用同一个 `resume` session 继续 → `Read` 读回并回复 token
- 断言口径优先：**磁盘落盘 + events.jsonl + tool/use/result**，而不是纯 final text

## Non-Goals

- 不测试 Gateway / MCP。
- 不测试 CLI PTY / ConPTY（另有人负责）。
- 不追求覆盖所有 permission mode，只覆盖最常用的 `default`（prompt→allow）与 resume 组合。

## Requirements

### REQ-0027-001 — Resume keeps permission prompt event persisted

在 `permission_mode=default` 下，首次运行触发的 `user.question` 必须写入 `events.jsonl`，且可在后续 `resume` run 中继续追加事件。

### REQ-0027-002 — Resume continues conversation after permission-gated write

首次运行完成 permission-gated `Write` 后，第二次运行 `resume` 同一 session，能通过 `Read` 工具读回写入内容并回复（不猜测）。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.e2e_sessions_resume_permission_prompt_write_then_read_real_no_injection` exit code=0
2) `python -m unittest -v e2e_tests.smoke_core` exit code=0（smoke 覆盖该用例）

