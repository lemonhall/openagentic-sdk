# PRD-0053 — Offline E2E Hard-Invariants Density v53（离线 E2E：硬不变量密度提升）

## Vision

把 `e2e_tests_offline/` 从“最小可用的离线 smoke”升级为“**高信噪比的硬不变量回归门禁**”：

- 用 **脚本化 provider（直接返回 ToolCall 序列）** 替代“依赖模型听话的提示词剧本”，让离线 E2E 的失败更接近 **SDK 行为回归**。
- 将离线 E2E 的用例数量提升到一个可量化的区间（**25–40 个**），覆盖 runtime/tool-loop/sessions/permissions/hooks/path-security 的关键边界。

## Background / Motivation

当前离线 E2E（`e2e_tests_offline/`）已覆盖 Core/Tool-loop/Streaming/Resume/Skill/SlashCommand/PermissionGate/Compaction（legacy overflow）等主干路径，但在以下“硬不变量”上覆盖密度偏低：

- `allowed_tools` gate（ToolNotAllowed）是否正确阻断并可被 provider 观察到
- PermissionGate（prompt/default/acceptEdits/callback/can_use_tool）各分支是否输出可诊断的拒绝/改写行为，且拒绝时无副作用
- HookEngine（pre_tool_use rewrite/block）是否对 tool input/执行有决定性影响
- Sessions：开启 streaming 时，`assistant.delta` 是否 **绝不**落盘到 `events.jsonl`
- Path 安全：path traversal / abs outside / Windows POSIX-like path 的映射/拒绝是否正确
- 工具边界：Overwrite=false / Read offset+limit（行号输出）/ 输入类型校验等错误是否能序列化为 provider 可见的 `function_call_output`

## Non-Goals

- 不替代真实网络 E2E（`e2e_tests/`），也不追求“模型是否按自然语言指令规划工具”。
- 不引入第三方依赖。
- 不新增 CLI 相关的 E2E（本 PRD 只关注核心模块离线 E2E）。

## Requirements

### REQ-0053-001 — 离线 E2E 规模（量化指标）

离线 E2E 总体数量（`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v`）达到 **25–40 个测试用例**，并全部通过。

### REQ-0053-002 — allowed_tools gate：ToolNotAllowed 可观察且无副作用

新增至少 1 个离线 E2E 覆盖：

- provider 请求不在 `allowed_tools` 的 tool
- runtime 产出 `ToolNotAllowed` 的 `tool.result`（`is_error=true`）
- provider 在下一次调用中能通过 `function_call_output` 观察到 `ToolNotAllowed`
- 磁盘无副作用（相关文件未被创建/修改）

### REQ-0053-003 — PermissionGate(prompt)：无 user_answerer 时必须拒绝并发出 user.question

新增至少 1 个离线 E2E 覆盖：

- `permission_mode="prompt"` 且 `interactive=False` 且 `user_answerer=None`
- runtime 必须发出 `user.question`
- tool 必须以 `PermissionDenied` 拒绝，且 provider 可观察到拒绝输出

### REQ-0053-004 — PermissionGate(callback)：回调异常的 deny_message 必须透出

新增至少 1 个离线 E2E 覆盖：

- `permission_mode="callback"` 且 `approver` 抛异常
- tool.result 为 `PermissionDenied`，且 `error_message` 包含可诊断的回调错误信息

### REQ-0053-005 — PermissionGate(default/acceptEdits)：安全工具免询问，写入按规则允许/拒绝

新增离线 E2E 覆盖：

- `default`：Read/Glob/Grep/Skill/SlashCommand/AskUserQuestion 等安全工具应直接允许（无 `user.question`）
- `default`：Write/Edit 等应进入 prompt 分支，并在回答 no 时拒绝且无副作用
- `acceptEdits`：Write/Edit 应直接允许（无 `user.question`）

### REQ-0053-006 — PermissionGate(can_use_tool)：updated_input 改写必须生效

新增至少 1 个离线 E2E 覆盖：

- `can_use_tool` 返回 `PermissionResultAllow(updated_input=...)`
- runtime 必须使用 `updated_input` 执行 tool（例如改写写入目标路径）

### REQ-0053-007 — Hooks：PreToolUse rewrite/block 必须决定性生效

新增离线 E2E 覆盖：

- `pre_tool_use` rewrite Read/Write 输入并改变实际执行目标
- `pre_tool_use` block 必须阻断 tool 执行并返回 `HookBlocked`（无副作用）

### REQ-0053-008 — Sessions：assistant.delta 不落盘

新增至少 1 个离线 E2E 覆盖：

- 开启 `include_partial_messages=True` 并出现 `assistant.delta`
- `events.jsonl` 中 **不应**出现 `assistant.delta`，但最终文本应可追溯

### REQ-0053-009 — Path 安全与 Windows POSIX-like 兼容映射

新增离线 E2E 覆盖：

- `../` traversal 必须被拒绝（ValueError），且不写到项目外
- 绝对路径在项目外必须被拒绝（ValueError），且不泄露内容
- Windows 下对 `/mnt/data/...` 等路径进行保守映射（映射到 project root 下），未知 POSIX abs 仍需拒绝

### REQ-0053-010 — 工具边界：错误序列化与关键行为断言

新增离线 E2E 覆盖：

- `overwrite=false` 的 FileExistsError
- Write `content` 非 string 的 ValueError
- Read `offset/limit` 触发“行号输出”格式（CAS 兼容）
- 上述错误均能通过 `function_call_output` 被 provider 观察到（包含 `is_error/error_type/error_message`）

## Acceptance (DoD)

必须全部满足：

1) Windows：`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v` exit code=0
2) 离线约束：不读取 `RIGHTCODE_*`、不发真实网络请求（允许对 `localhost` 等做阻断校验，但不应成功发起公网 fetch）
3) 用例数量：离线 E2E 测试用例数在 **25–40** 区间内

