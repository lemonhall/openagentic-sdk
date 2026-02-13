# PRD-0003: 进一步拆分 Query Loop（`openagentic_sdk/runtime_core/query_loop.py`）

## Vision

把 `openagentic_sdk/runtime_core/query_loop.py`（当前约 700+ 行）继续拆成一组**职责单一、可读、可验证**的小模块（目标：单文件 ~100 行上下），并保持：

- 行为不变（tests 作为证据）
- 对外 API 不变（`AgentRuntime.query()` 语义与事件顺序不应改变）
- 后续继续演进时可以“加模块/替换模块”，而不是继续往一坨函数里堆

## Background

`QueryLoopMixin.query()` 当前同时承担：

- MCP tools 注册 + client lifecycle
- session/store 初始化与 resume rebuild
- system prompt 注入与 user prompt 预处理（skills/list-skills、slash command 直执行）
- model call（stream/complete + previous_response_id/fallback）
- tool call plumbing（legacy vs responses-threaded vs responses-fallback）
- compaction overflow 触发与 tool-output pruning glue
- stop/session_end hooks 与 Result 收尾

这导致单函数过大，review 与改动风险高。

## Requirements

### REQ-0003-001 — 引入子目录承载 Query Loop 的步骤模块

- 新增目录：`openagentic_sdk/runtime_core/query_loop_steps/`
- 将 query loop 关键职责拆到多个小模块中
- `openagentic_sdk/runtime_core/query_loop.py` 变为 orchestrator（目标 ~100 行量级）

### REQ-0003-002 — 行为保持不变（证据=测试）

验收以测试为准：

- WSL2：`python3 -m unittest -q` 必须通过
- Windows：本轮影响范围内的范围回归必须通过（见 v3 计划）

### REQ-0003-003 — 对外 API 与事件契约保持不变

- `AgentRuntime.query()` 对调用方保持兼容（包括 hooks、session 事件落盘、tool loop、compaction）
- 事件顺序与字段语义不应因重构改变（以现有测试为护栏）

### REQ-0003-004 — 拆分边界清晰

至少拆出这些逻辑边界（文件名可调整）：

- MCP setup / teardown glue
- session bootstrap / resume rebuild
- user prompt preprocess（hooks + slash command 直执行）
- model call（stream/complete + retry/fallback）
- tool call plumbing（legacy / responses-threaded / responses-fallback）
- finalize / hooks / Result

## Non-Goals

- 不改功能、不改协议、不引入新依赖
- 不做 ruff 全量修复（避免跑偏）

## Risks

- 事件顺序/细节轻微漂移（通过现有 tests 防回归）
- 循环 import（通过依赖方向与小步拆分避免）

