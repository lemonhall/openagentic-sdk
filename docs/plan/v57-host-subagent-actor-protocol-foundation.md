# v57 Plan — Host/Subagent Actor Protocol Foundation

## Goal

为 host ↔ subagent 建立 actor foundation 的第一层本地基座：M1 把 local subagent 真正落到 execution / mailbox / envelope 语义上，并补齐顶层 API 的 host-authoritative 可观测入口；remote 侧在 M1 只保留兼容字段，不要求已经进入同一 transport / mailbox 语义。M1 不做 supervisor restart，也不做远程 replay。

## PRD Trace

- REQ-0057-001
- REQ-0057-002
- REQ-0057-003
- REQ-0057-007
- REQ-0057-008
- REQ-0057-009
- REQ-0057-010

## Scope

做：

- 新增 actor envelope、mailbox store、execution registry 的核心数据结构
- 新增统一的 `ActorTransport` 接口
- 实现 local actor transport
- 让 transport 层真正兑现 mailbox 的顺序与去重 contract，而不是只在 store 层“记账”
- 让本地 `Task` child runtime 接到 actor foundation
- 保持现有 `Task` 外层 tool 语义不变

不做：

- 不做 remote HTTP replay / reconnect
- 不做 remote transport actor 化；remote 只保留与 execution_id 相关的兼容元数据入口
- 不做 supervisor restart policy
- 不做 cluster chat bridge 改造
- 不做 group / pool / scheduler

## Implementation Notes

- actor foundation 的第一主键必须是 `execution_id`，不是 `session_id`。
- M1 的 mailbox store 可以先落在内存 + append-only event 结构，但语义上必须明确有 inbox / outbox / seq。
- 兼容层要放在 host runtime / `Task` 执行层，而不是让 CLI / trace 先知道 actor internals。
- 本地 child runtime 现在直接是 generator 风格；M1 要把它包进 local transport，而不是继续裸连 generator。
- `openagentic_sdk.query()` / `run()` 这类顶层入口也必须保留 host-authoritative 可观测性；第一版通过显式的 `OpenAgenticOptions.runtime_state` 暴露 runtime / actor registry / mailbox store，而不是要求调用方自己直接 new `AgentRuntime`。

## Acceptance (DoD)

必须全部满足：

1. `python -m unittest -q tests.test_actor_protocol tests.test_actor_mailbox_store tests.test_actor_local_transport tests.test_subagent_task`
2. `ruff check openagentic_sdk/subagents openagentic_sdk/runtime_core/tool_task.py tests/test_actor_protocol.py tests/test_actor_mailbox_store.py tests/test_actor_local_transport.py tests/test_subagent_task.py --config ruff.toml`
3. 反作弊条款：
   - 不允许只新增 dataclass，却不让本地 `Task` 真正走 actor transport
   - 不允许 execution registry 只是日志输出，没有可查询状态

## Files

- Create: `openagentic_sdk/subagents/actor_protocol.py`
- Create: `openagentic_sdk/subagents/actor_mailbox.py`
- Create: `openagentic_sdk/subagents/actor_registry.py`
- Create: `openagentic_sdk/subagents/actor_transport.py`
- Create: `openagentic_sdk/subagents/actor_local_transport.py`
- Modify: `openagentic_sdk/subagents/remote_types.py`
- Modify: `openagentic_sdk/options.py`
- Modify: `openagentic_sdk/__init__.py`
- Modify: `openagentic_sdk/runtime_core/agent_runtime.py`
- Modify: `openagentic_sdk/runtime_core/tool_task.py`
- Modify: `tests/test_subagent_task.py`
- Create: `tests/test_actor_protocol.py`
- Create: `tests/test_actor_mailbox_store.py`
- Create: `tests/test_actor_local_transport.py`

## Test Contract

### Contract A — actor envelope 有稳定 contract

`tests.test_actor_protocol` 至少覆盖：

- envelope 必填字段齐全
- `message_id` / `execution_id` / `seq` 的序列化与反序列化稳定
- 非法 `kind` / 缺字段明确失败

### Contract B — mailbox 有序、可去重、可查询

`tests.test_actor_mailbox_store` 至少覆盖：

- 同一 mailbox 内按 `seq` 有序追加
- duplicate `message_id` 不会被重复接收
- execution registry 能基于 `execution_id` 看到当前 mailbox head 与状态

### Contract C — local child 真正走 actor transport

`tests.test_actor_local_transport` 至少覆盖：

- host 通过 local transport `spawn` child execution
- child 事件通过 actor envelope 回流
- host 能看到 `execution_id`、state transition、最终退出态

### Contract D — `Task` 兼容层不退化

`tests.test_subagent_task` 至少覆盖：

- 本地 `Task` 仍能回流 child events
- 最终 `tool.result` 仍保留 child session 信息
- actor foundation 接入后，模型侧 `Task(agent=..., prompt=...)` 用法不变
- 顶层 `openagentic_sdk.query()` / `run()` 入口仍能把 host runtime state 暴露给调用方，确保 execution registry 在不直接持有 `AgentRuntime` 时依然可查

## Steps

1. Analysis
   - 读清当前 `tool_task.py` / `remote_types.py` / `subagent task` 测试现状

2. TDD Red：actor envelope
   - 先写 `tests/test_actor_protocol.py`
   - 运行到红：`python -m unittest -v tests.test_actor_protocol`

3. TDD Green：协议核心
   - 新增 actor envelope / mailbox / registry / transport interface
   - 跑到绿：`python -m unittest -v tests.test_actor_protocol tests.test_actor_mailbox_store`

4. TDD Red：local transport
   - 先写 `tests/test_actor_local_transport.py`
   - 运行到红：`python -m unittest -v tests.test_actor_local_transport`

5. TDD Green：本地 actor transport
   - 实现 local spawn / send / receive / close
   - 跑到绿：`python -m unittest -v tests.test_actor_local_transport`

6. TDD Red：`Task` 兼容层
   - 先让 `tests.test_subagent_task` 证明当前本地 `Task` 还没接 actor foundation

7. TDD Green：兼容接入
   - 修改 `tool_task.py` / `remote_types.py`
   - 跑到绿：`python -m unittest -v tests.test_subagent_task`

8. Review
   - 更新 `docs/plan/v57-index.md`
   - 确认未触碰 cluster chat bridge

## Evidence

- Date: 2026-03-29
- Env: Windows 11 + PowerShell 7.x
- Verification:
  - `python -m unittest -q tests.test_actor_protocol tests.test_actor_mailbox_store tests.test_actor_local_transport tests.test_subagent_task`
  - `ruff check openagentic_sdk/subagents openagentic_sdk/runtime_core/tool_task.py tests/test_actor_protocol.py tests/test_actor_mailbox_store.py tests/test_actor_local_transport.py tests/test_subagent_task.py --config ruff.toml`
- Status: implemented；verified locally
