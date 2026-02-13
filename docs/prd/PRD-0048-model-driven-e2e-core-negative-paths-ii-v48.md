# PRD-0048 — Model-Driven E2E (Core Negative Paths II v48)（模型驱动 E2E：核心负路径 II v48）

## Vision

继续加厚核心模块负路径（失败分支/防护分支）的真网络 no-injection 回归证据，目标是把“工具系统 + hook 系统”的关键拒绝路径跑实：

- 工具白名单（`allowed_tools`）拒绝时不应写盘、且错误类型可识别；
- hook 明确 block 工具时应产生 `HookBlocked`，并且不产生副作用；
- `Read` / `Edit` 在常见错误输入下应返回稳定、可断言的失败。

聚焦核心中的核心：`tools` / `hooks` / `runtime_core(tool loop)`。

## Non-Goals

- 不触碰 PTY/ConPTY（另一个同学负责）。
- 不扩大到 Gateway/MCP。
- 不引入需要修改 SDK 行为的“坏日志恢复/resume 容错”（放到下一版）。

## Requirements

### REQ-0048-001 — Write outside project root is denied (ValueError)

新增真网络、no-injection E2E：

- 断言：
  - 出现 `tool.result`：`is_error=True` 且 `error_type="ValueError"`（信息包含 “Tool path must be under project root”）
  - 目标路径文件未写入/不存在

### REQ-0048-002 — pre_tool_use blocks Write (HookBlocked)

新增真网络、no-injection E2E：

- `pre_tool_use` hook 对 `Write` 直接 `block=True`
- 断言：
  - 出现 `hook.event`（PreToolUse）
  - 出现 `tool.result`：`is_error=True` 且 `error_type="HookBlocked"`
  - 目标文件未写入/不存在

### REQ-0048-003 — Read missing file returns FileNotFoundError

新增真网络、no-injection E2E：

- 模型调用 `Read ./missing.txt`（文件不存在）
- 断言：
  - 出现 `tool.result`：`is_error=True` 且 `error_type="FileNotFoundError"`

### REQ-0048-004 — Edit old mismatch returns ValueError and does not modify file

新增真网络、no-injection E2E：

- 预置 `a.txt` 内容为 token
- 模型调用 `Edit ./a.txt` 且 `old="NOT_PRESENT"`（不在文件中）
- 断言：
  - 出现 `tool.result`：`is_error=True` 且 `error_type="ValueError"`（信息包含 “old” not found）
  - `a.txt` 内容保持不变

### REQ-0048-005 — Suite + Evidence

- 更新 `e2e_tests/core_flows_tools.py` 纳入以上 4 条流程
- 按塔山 DoD 跑真网络 gate 并落证据到 plan 文档：
  - `python -m unittest -v e2e_tests.core_flows_tools`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_tools --runs 3 --min-pass-rate 0.8 --rerun-failures 1`

## Acceptance (DoD)

必须全部满足：

- REQ-0048-001..005 全部达成
- 证据写入 `docs/plan/v48-model-driven-e2e-core-negative-paths-ii.md`
