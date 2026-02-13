# PRD-0009 — Real-Network E2E (Core Tools Workflows)（真实网络 E2E：核心工具用户流程）

## Vision

用真实网络 E2E 把 `tools` + `runtime_core` 的核心用户流程做硬回归：文件写入/精确编辑/Notebook 编辑/Todo 落盘/无 Read 的检索（Glob+Grep）这些必须可端到端验证，且验证结果不依赖“模型猜对”。

## Background / Motivation

现有真实 E2E 已覆盖 hooks/skill/ask_user_question/slash 等核心链路，但对“工具链组合用户流程”的覆盖仍偏少。核心风险在于：
- tool loop 序列化/回灌（function_call_output）在真实网络环境的稳定性
- 工具行为本身（Edit/NotebookEdit/TodoWrite/Glob/Grep）在真实对话中的可用性与可验证性

## Non-Goals

- 不测 Gateway/MCP。
- 不测大输出/大 token 的流程（控制成本）。
- 不做依赖模型自由发挥的工具选择：尽量通过 `allowed_tools` 限制 + 文件状态断言硬化。

## Requirements

### REQ-0009-001 — Edit roundtrip（真实网络）

新增 E2E：通过真实网络调用驱动一次完整 tool loop，使 `Edit` 工具实际修改磁盘文件；测试以“文件内容变更”作为硬断言（黑盒：不以模型文本为准）。

### REQ-0009-002 — NotebookEdit roundtrip（真实网络）

新增 E2E：通过真实网络调用驱动一次完整 tool loop，使 `NotebookEdit` 工具实际修改磁盘上的 `.ipynb`；测试以 notebook JSON 变更作为硬断言。

### REQ-0009-003 — TodoWrite persists todos.json（真实网络）

新增 E2E：模型必须调用 `TodoWrite` 写入 todo，并由测试代码验证 session 目录下 `todos.json` 产生且内容符合预期。

### REQ-0009-004 — Glob + Grep workflow without Read（真实网络）

新增 E2E：限制 `allowed_tools=["Glob","Grep"]`，通过真实网络调用驱动一次完整 tool loop：
- `Glob` 只枚举 `*.txt` 文件；
- `Grep` 只在 `*.txt` 内搜索 `^found:`；
- 测试以 `Grep` 的 `tool.result` 输出包含 token 作为硬断言（避免依赖模型“复述 token”的不稳定性）。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0009-001..004
