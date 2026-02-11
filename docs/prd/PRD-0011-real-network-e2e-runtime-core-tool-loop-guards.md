# PRD-0011 — Real-Network E2E (runtime_core Tool Loop Guards)（真实网络 E2E：runtime_core 工具环路护栏）

## Vision

用真实网络 E2E 把 `runtime_core` 的“护栏语义”做硬回归，确保在各种拒绝/阻断/错误场景下：
- 事件类型与错误类型可机读（`tool.result.{is_error,error_type}`）；
- 不会把“工具未执行”误报为“工具已执行”；
- 人类交互入口（permission prompt）能产出 `user.question`。

## Non-Goals

- 不测试 MCP/Gateway。
- 不要求模型在被拒绝后给出特定自然语言回复；验证以事件/错误语义为准。

## Requirements

### REQ-0011-001 — ToolNotAllowed is emitted without tool.use（真实网络）

当 `allowed_tools` 不包含某工具时：
- 调用该工具必须直接得到 `tool.result`（`error_type="ToolNotAllowed"`）；
- 不应产生对应的 `tool.use` 事件（因为工具未执行）。

### REQ-0011-002 — HookBlocked blocks tool execution（真实网络）

当 `pre_tool_use` hook 以 block 决策阻断时：
- 必须产生 `tool.use`（表示尝试）；
- 随后产生 `tool.result`（`error_type="HookBlocked"`）。

### REQ-0011-003 — Permission prompt produces user.question + PermissionDenied（真实网络）

当 PermissionGate 为 `prompt` 且无 `user_answerer` 时：
- 必须产生 `user.question`；
- 工具最终必须被拒绝并产生 `tool.result`（`error_type="PermissionDenied"`）。

### REQ-0011-004 — Tool exceptions serialize into tool.result（真实网络）

当工具抛出异常（例如 `Edit` 的 `ValueError`）时：
- 必须产生 `tool.use`；
- 必须产生 `tool.result`（`is_error=True`, `error_type` 为异常类型名）。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0011-001..004

