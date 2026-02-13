# PRD-0016 — Real-Network E2E (Core Hardening v16)（真实网络 E2E：核心加固 v16）

## Vision

继续用真实网络 E2E 夯实核心模块的“可回归、可机读、可观测”：
- `runtime_core`：stream + tool loop、prune、resume、一致性与 fallback 路径；
- `permissions`：prompt 模式的 allow 主路径；
- `hooks`：生命周期 hook 点（session_start/end/stop/compacting）的可观测性；
- `tools`：补齐至少一个“非注入版”Edit happy-path，用于验证模型自主选择工具的链路。

## Non-Goals

- 不测试 MCP / Gateway。
- 不追求每个用例都完全依赖模型自由发挥：对“系统语义/事件序列”优先使用硬断言（event / tool.result / 落盘产物）。

## Requirements

### REQ-0016-001 — Streaming + tool loop event order（真实网络）

新增 E2E：在 `query_messages(include_partial_messages=True)` 下，强制产生：
- `StreamEvent(text_delta)` 至少一次；
- `ToolUse(Read)` 与 `ToolResult(Read)`；
- 最终 `ResultMessage`；
并断言顺序与内容合理（Read 结果包含 token）。

### REQ-0016-002 — Compaction prune marks old tool outputs（真实网络）

新增 E2E：在 `supports_previous_response_id=False` 的恢复会话中触发 `_maybe_prune_tool_outputs`：
- 出现 `tool.output_compacted`；
- 随后的 provider input 中，旧 tool.output 被替换为 placeholder（`[Old tool result content cleared]`）。

### REQ-0016-003 — Resume after fallback does not thread previous_response_id（真实网络）

新增 E2E：先触发 supports_previous_response_id 回退为 False，再 resume 同 session：
- provider 调用不得再带 `previous_response_id`；
- provider input 使用 `rebuild_responses_input`（function_call / function_call_output）而非 chat `role=tool`。

### REQ-0016-004 — Permission prompt allow path emits user.question and runs tool（真实网络）

新增 E2E：PermissionGate `prompt` + `user_answerer=yes`：
- 必须产生 `user.question`；
- 随后工具执行成功（`tool.result is_error=False`）。

### REQ-0016-005 — Hook lifecycle hook.event observability（真实网络）

新增 E2E：为 `session_start/session_end/stop/session_compacting` 注册 hooks：
- 必须产生对应 `hook.event`，且 `hook_point` 值正确。

### REQ-0016-006 — Non-injected Edit happy-path（真实网络）

新增 E2E：不使用 after_model_call 注入 tool_calls，让模型自主调用 `Edit`：
- 磁盘文件内容确实变更；
- 出现 `tool.use(name="Edit")`。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0016-001..006

