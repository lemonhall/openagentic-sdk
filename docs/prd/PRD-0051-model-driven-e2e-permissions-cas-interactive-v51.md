# PRD-0051 — Model-Driven E2E (Permissions: CAS + Interactive v51)（模型驱动 E2E：权限 CAS + 交互审批 v51）

## Vision

把 PermissionGate 的两个关键分支补齐真网络 no-injection 证据：

- `can_use_tool`（CAS 风格）：允许/拒绝/改写 tool_input 的行为必须可回归
- `interactive=True` 的交互审批：在无需真实 TTY 的前提下，用可控 `InteractiveApprover` 覆盖允许/拒绝路径

目标：权限门的“全谱系”不再只有 prompt/callback 的证据，CAS 与 interactive 分支也必须守住底线（不静默放行、不落盘、错误可断言）。

## Non-Goals

- 不扩大到 Gateway/MCP。
- 不触碰 PTY/ConPTY（另一个同学负责）。
- 不做真实终端交互 E2E（用 stub input_fn 代替）。

## Requirements

### REQ-0051-001 — CAS allows with updated_input rewrites Write target

新增真网络、no-injection E2E：

- 设置 `PermissionGate(can_use_tool=...)` 返回 `PermissionResultAllow(updated_input=...)`
- 模型尝试 `Write ./a.txt`
- 断言：实际落盘到 `./b.txt`（`a.txt` 不存在，`b.txt` 含 token）

### REQ-0051-002 — CAS deny returns PermissionDenied with message and no user.question

新增真网络、no-injection E2E：

- `can_use_tool` 返回 `PermissionResultDeny(message="...")`
- 模型尝试 `Write`
- 断言：
  - `tool.result`：`error_type="PermissionDenied"` 且 `error_message` 包含 deny message
  - 不产生 `user.question`
  - 不落盘

### REQ-0051-003 — interactive prompt deny: no user.question, PermissionDenied, no disk write

新增真网络、no-injection E2E：

- `permission_mode="prompt"` + `interactive=True` + `interactive_approver=input_fn -> "no"`
- 模型尝试 `Write`
- 断言：
  - 不产生 `user.question`（interactive 分支）
  - `tool.result`：`error_type="PermissionDenied"`
  - 不落盘

### REQ-0051-004 — interactive prompt allow: write succeeds without user.question

新增真网络、no-injection E2E：

- `permission_mode="prompt"` + `interactive=True` + `interactive_approver=input_fn -> "yes"`
- 模型尝试 `Write`
- 断言：
  - 不产生 `user.question`
  - 写入成功且文件含 token

### REQ-0051-005 — Suite + Evidence

- 更新 `e2e_tests/core_flows_hil.py` 纳入 REQ-0051-001..004
- 按塔山 DoD 跑真网络 gate 并落证据到 plan 文档：
  - `python -m unittest -v e2e_tests.core_flows_hil`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1`

## Acceptance (DoD)

必须全部满足：

- REQ-0051-001..005 全部达成
- 证据写入 `docs/plan/v51-model-driven-e2e-permissions-cas-interactive.md`

