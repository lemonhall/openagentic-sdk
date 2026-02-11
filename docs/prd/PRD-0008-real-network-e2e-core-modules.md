# PRD-0008 — Real-Network E2E (Core Modules)（真实网络 E2E：核心模块夯实）

## Vision

用“需要网络的真实 E2E”把核心模块夯实：`hooks`、`skill/commands`、`runtime_core`、`tools`、人类交互（PermissionGate/user_answerer）这些链路必须有稳定的端到端回归保护。

## Background / Motivation

离线 E2E 可重复但无法覆盖真实网关/模型行为；真实网络 E2E 才能验证：
- tool schema→模型 tool call→runtime 执行→function_call_output→继续对话
- hooks 在真实调用链上的时序与生效点（before/after model call）
- skill/command 加载是否被模型真实使用
- 人类交互（AskUserQuestion → user.question → user_answerer）在真实 provider 下是否正确串起来

## Non-Goals

- 不优先测 Gateway/MCP（除非用户明确要求）。
- 不做需要大量 token/费用的长流程。
- 不做高度不确定的“模型必须自己发明工具调用”的测试；尽量用“随机 token 只能通过 tool/hook 得到”来硬化断言。

## Requirements

### REQ-0008-001 — Skill tool（真实网络）

新增 E2E：模型必须调用 `Skill` tool 才能获得随机 token，并最终回复该 token。

### REQ-0008-002 — AskUserQuestion（真实网络 + 人类交互）

新增 E2E：模型调用 `AskUserQuestion`，runtime 发出 `user.question`，`user_answerer` 返回随机 token，模型最终回复该 token。

### REQ-0008-003 — SlashCommand tool（真实网络，parts/url 编码）

新增 E2E：模型调用 `SlashCommand` tool，tool 输出包含 `parts`（file url 用 `Path.as_uri()`，`#` 编码为 `%23`），并通过 rendered content 中的随机 token 做黑盒断言。

### REQ-0008-004 — Hooks BeforeModelCall rewrite（真实网络）

新增 E2E：`HookEngine.before_model_call` 在真实网络调用链中重写 messages，使最终输出为随机 token（token 不在原始 prompt 中）。

### REQ-0008-005 — Hooks AfterModelCall override（真实网络）

新增 E2E：`HookEngine.after_model_call` 覆盖模型输出为随机 token（证明 after hook 生效点与类型契约）。

### REQ-0008-006 — README/运行说明

更新 `e2e_tests/README.md`：说明支持根目录 `.env` + `OPENAI_API_KEY/OPENAI_BASE_URL` 作为别名配置。

## Acceptance (DoD)

必须全部满足：

1) 配好 `.env` 或环境变量后运行：
   - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
   exit code=0
2) 新增用例覆盖 REQ-0008-001..005

