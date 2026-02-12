# PRD-0035 — Core E2E Coverage Matrix + Expansion v35（核心 E2E 覆盖矩阵 + 扩容 v35）

## Vision

用“覆盖矩阵（capability → test → evidence）”驱动核心模块的真网络 E2E 扩容，先把**用例密度**堆上去，再讨论更抽象的范式。

核心模块范围（不变）：

- Tools（Read/Write/Edit/Glob/Grep/List/TodoWrite/NotebookEdit/Skill/SlashCommand/AskUserQuestion）
- Runtime Core（tool loop / allowed_tools gate / tool plumbing）
- Sessions + Resume（events.jsonl 落盘与恢复；禁止落 delta）
- Permissions（default/prompt/acceptEdits/callback）
- Hooks（before/after model call；pre/post tool use；block/override）

## Non-Goals

- 不扩大到 Gateway/MCP 的覆盖（边缘模块）。
- 不触碰 PTY/ConPTY（另一个同学负责）。
- 不把随机层 `core_flows` 全部“写死”成 injected（只补硬不变量缺口）。

## Requirements

### REQ-0035-001 — Coverage matrix doc

新增覆盖矩阵文档，列出核心能力点、现有 E2E 映射与缺口：

- `docs/guides/core-e2e-coverage-matrix.md`

### REQ-0035-002 — Tool: `List` basic behavior

新增真网络 E2E，验证 `List` 工具：

- 能列出目录树输出（`tool.result.output` / `count` / `path`）
- 断言以 `tool.use/tool.result` + 输出字符串包含预期文件名为主

### REQ-0035-003 — Tool security: `List` path boundary

`List` 工具必须遵守工具路径边界规则（与 Read/Write/Edit 一致）：

- 绝对路径指向 project root 外时必须报错（不允许列出外部目录）
- 断言 `tool.result.is_error=True` 且错误信息不泄露外部目录内容

### REQ-0035-004 — Runtime Core: `allowed_tools` gate

新增 deterministic 真网络 E2E，验证 `allowed_tools` gate：

- 当模型输出（或 hook 注入）不被允许的 tool call 时：
  - 必须返回 `ToolNotAllowed`
  - 必须无磁盘副作用（例如不应创建文件）

### REQ-0035-005 — Permissions: `callback` gate deterministic flow

新增 deterministic 真网络 E2E，验证 `permission_mode="callback"`：

- 第一次写入被 callback 拒绝（tool.result PermissionDenied）
- 第二次写入被允许（tool.result ok，磁盘出现 token）

### REQ-0035-006 — Hooks: post-tool-use block semantics

新增真网络 E2E，验证 `post_tool_use` 的 `block` 语义：

- tool 先运行成功产出 output，但 post hook block 后：
  - tool.result 必须为 error
  - 错误原因应可归因为 hook block（`error_message` 包含 block reason）

### REQ-0035-007 — Suite + evidence

新增一个小型稳定套件（全 injected / hard invariants）：

- `e2e_tests/core_matrix.py`

并用两种方式产出证据：

1) `python -m unittest -v e2e_tests.core_matrix` exit code=0  
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix --runs 3 --min-pass-rate 1.0` exit code=0（报告落盘到 `.openagentic_e2e_reports/`）

## Acceptance (DoD)

必须全部满足：

1) 以上 REQ 对应的代码/文档均落地
2) `python -m unittest -v e2e_tests.core_matrix` exit code=0
3) `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix --runs 3 --min-pass-rate 1.0` exit code=0

