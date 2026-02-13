# PRD-0050 — Model-Driven E2E (Permissions Negative Paths v50)（模型驱动 E2E：权限负路径 v50）

## Vision

把权限门（PermissionGate）的关键“拒绝/异常”路径做成真网络 no-injection 回归证据，确保不会出现：

- prompt 模式未配置 answerer 却静默继续；
- callback approver 抛错导致不确定行为；
- acceptEdits 误放行非编辑类工具。

聚焦核心中的核心：human-in-the-loop 权限门 + tool-loop 的拒绝路径。

## Non-Goals

- 不扩大到 Gateway/MCP。
- 不触碰 PTY/ConPTY（另一个同学负责）。
- 不做需要修改业务语义的权限策略变更（只补证据/必要的小修）。

## Requirements

### REQ-0050-001 — prompt mode without user_answerer denies safely

新增真网络、no-injection E2E：

- `permission_mode="prompt"` 且 `interactive=False` 且 `user_answerer=None`
- 模型尝试 `Write`
- 断言：
  - 出现 `user.question`
  - 出现 `tool.result`：`is_error=True` 且 `error_type="PermissionDenied"`
  - 目标文件不落盘

### REQ-0050-002 — callback approver raises -> deny safely (PermissionDenied)

新增真网络、no-injection E2E：

- `permission_mode="callback"`，approver 抛异常
- 模型尝试 `Write`
- 断言：
  - 不落盘
  - 结果为明确失败（推荐：捕获异常并转为 `PermissionDenied`）

### REQ-0050-003 — acceptEdits allows Edit/Write but still prompts on non-edit tools

新增真网络、no-injection E2E：

- `permission_mode="acceptEdits"` + `user_answerer=deny`
- 模型尝试 `Read`（safe? 但 acceptEdits 会降级为 prompt）
- 断言：
  - 出现 `user.question`
  - `Read` 被拒绝（PermissionDenied）

### REQ-0050-004 — Suites + Evidence

- 更新 `e2e_tests/core_flows_hil.py`（新增 2 条权限负路径）
- 更新 `e2e_tests/core_flows_sessions.py`（新增 1 条 acceptEdits 边界）
- 按塔山 DoD 跑真网络 gate 并落证据到 plan 文档：
  - `python -m unittest -v e2e_tests.core_flows_hil`
  - `python -m unittest -v e2e_tests.core_flows_sessions`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1`

## Acceptance (DoD)

必须全部满足：

- REQ-0050-001..004 全部达成
- 证据写入 `docs/plan/v50-model-driven-e2e-permissions-negative-paths.md`

