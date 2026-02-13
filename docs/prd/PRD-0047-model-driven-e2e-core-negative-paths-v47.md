# PRD-0047 — Model-Driven E2E (Core Negative Paths v47)（模型驱动 E2E：核心负路径 v47）

## Vision

在“真网络 + no-injection”的随机层里，把核心模块的负路径（失败分支/防护分支）做实做硬，避免出现：

- 权限拒绝但仍落盘；
- hook 误改输入导致越权写盘；
- streaming delta 被落到 `events.jsonl`，导致会话膨胀到 GB。

聚焦核心中的核心：`tools` / `permissions` / `hooks` / `sessions(resume & persistence)`。

## Non-Goals

- 不扩大到 Gateway/MCP。
- 不触碰 PTY/ConPTY（另一个同学负责）。
- 不把随机层改 injected（硬不变量由 injected matrix 守门）。

## Requirements

### REQ-0047-001 — Permissions: default + Write denied must not write to disk

新增真网络、no-injection E2E：

- `permission_mode="default"` 下尝试 `Write` 必须产生 `user.question`
- user_answerer 返回拒绝（no）
- 断言：
  - 出现 `user.question`
  - 对应 `tool.result` 为 error（`ToolDenied`）
  - 目标文件未写入/不存在

### REQ-0047-002 — Hooks: pre_tool_use rewrite cannot escape project root

新增真网络、no-injection E2E：

- `pre_tool_use` hook 将 `Write` 的 `file_path` 改写为 `../escape.txt`
- 断言：
  - 出现 `hook.event`（PreToolUse）
  - `Write` 的 `tool.result` 为 error（`ValueError`，信息包含 “Tool path must be under project root”）
  - `../escape.txt` 不存在

### REQ-0047-003 — Sessions: never persist assistant.delta to events.jsonl

新增真网络、no-injection E2E：

- `include_partial_messages=True` 运行一次模型输出（确保内存 events 中出现至少一个 `assistant.delta`）
- 断言 `sessions/<sid>/events.jsonl` 中：
  - 不存在任何 `type == "assistant.delta"` 的记录
  - 不包含 `assistant.delta` / `text_delta` 相关字符串

### REQ-0047-004 — Suites + Evidence

- 更新 suites：
  - `e2e_tests/core_flows_hil.py` 增加 REQ-0047-001/002
  - `e2e_tests/core_flows_sessions.py` 增加 REQ-0047-003
- 按塔山 DoD 跑真网络 gate 并落证据到 plan 文档：
  - `python -m unittest -v e2e_tests.core_flows_sessions`
  - `python -m unittest -v e2e_tests.core_flows_hil`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1`

## Acceptance (DoD)

必须全部满足：

- REQ-0047-001..004 全部达成
- 证据写入 `docs/plan/v47-model-driven-e2e-core-negative-paths.md`

