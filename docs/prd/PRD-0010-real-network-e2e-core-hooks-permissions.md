# PRD-0010 — Real-Network E2E (Core Hooks + Permissions)（真实网络 E2E：Hooks 与权限门核心链路）

## Vision

用真实网络 E2E 把 `hooks` + `permissions` 两条“人类交互/安全控制”的核心链路做硬回归：
- Hook 能稳定改写 tool 输入/输出并被写入 session（后续模型调用看到的就是改写后的结果）。
- PermissionGate 能稳定阻止工具调用，并产出可机读的错误事件（ToolResult: PermissionDenied）。

## Non-Goals

- 不测试 MCP / Gateway。
- 不要求模型在被拒绝后“聪明地自我修复”；测试只验证 runtime_core 事件与错误语义正确。

## Requirements

### REQ-0010-001 — post_tool_use override (Read) roundtrip（真实网络）

新增 E2E：
- 通过 `HookEngine.post_tool_use` 覆盖 `Read` 的输出内容；
- 测试以 `tool.result` 中的输出被改写为硬断言（并尽量要求最终回复包含改写后的内容）。

### REQ-0010-002 — PermissionDenied is serialized as tool.result（真实网络）

新增 E2E：
- PermissionGate 以 deny 模式拒绝 `Read`；
- 测试断言出现 `tool.result` 且 `is_error=True`、`error_type="PermissionDenied"`。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0010-001..002

