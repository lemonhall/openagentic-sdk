# PRD-0006 — Offline E2E More Core Tooling（离线 E2E：更多核心 Tool/Core 覆盖）

## Vision

把离线 E2E 从“覆盖主干”推进到“覆盖关键边界”：对 **AskUserQuestion / SlashCommand（tool 模式）/ tool error serialization** 提供端到端回归保护，避免 runtime/Tool plumbing 重构时出现隐性行为漂移。

## Background / Motivation

当前离线 E2E 已覆盖 Core/Tool/Streaming/Resume/Skill/SlashDirect/PermissionGate/Compaction（legacy overflow），但仍缺少以下链路的端到端验证：

- AskUserQuestion：模型发起询问 → runtime 发出 `user.question` → `user_answerer` 回答 → tool output 回传模型
- SlashCommand（tool 调用模式）：模型请求 `SlashCommand` tool → runtime 渲染模板（含 `@file` 注入、file url 编码、parts）→ 回传模型
- tool error serialization：tool 执行失败时，runtime 仍要把 `is_error/error_type/error_message` 序列化进 provider 可见的 output（否则模型只看到 null）

## Non-Goals

- 不覆盖真实网络 e2e（`e2e_tests/`）和费用路径。
- 不把离线 E2E 纳入默认 `python -m unittest -q` 自动发现（仍显式 discover）。
- 不做 CLI 子进程 E2E（避免平台输出差异导致脆弱）。

## Requirements

### REQ-0006-001 — 离线 E2E：AskUserQuestion 完整链路

新增至少 1 个用例覆盖：
- provider 返回 `ToolCall(name="AskUserQuestion")`
- runtime 发出 `user.question` 事件，并通过 `permission_gate.user_answerer` 得到答复
- provider 在第二次调用中收到 `function_call_output`，其中包含 answers

### REQ-0006-002 — 离线 E2E：SlashCommand tool 链路（parts + file url 编码）

新增至少 1 个用例覆盖：
- provider 返回 `ToolCall(name="SlashCommand", arguments={"name": "...", "args": "..."})`
- runtime 返回 tool output（包含 `content` 和 `parts`）
- `parts` 中 file url 使用 `Path.as_uri()`（例如 `#` 被编码为 `%23`）

### REQ-0006-003 — 离线 E2E：tool error serialization

新增至少 1 个用例覆盖：
- provider 请求一个会失败的 tool（例如 Read missing file）
- provider 在下一次调用中收到 `function_call_output.output`，其中包含 `is_error: true` 且有 `error_type/error_message`

## Acceptance (DoD)

必须全部满足：

1) WSL2：`wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` exit code=0
2) Windows：`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v` exit code=0
3) 新增离线 E2E 覆盖 REQ-0006-001..003，且不读取 `RIGHTCODE_*`

