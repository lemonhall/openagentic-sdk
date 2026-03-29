# v57 Plan — Host/Subagent Supervision And Recovery

## Goal

把 child execution 的生命周期从“等结果或抛异常”推进到“有 monitor、有 `down`、有 supervisor decision”的明确 contract，让 host 能结构化地处理正常结束、业务失败、transport 失败和 abort。

## PRD Trace

- REQ-0057-004
- REQ-0057-005
- REQ-0057-008
- REQ-0057-009
- REQ-0057-010

## Scope

做：

- 定义 `down` / `exit` / `abort` 等生命周期事件
- 给 host 默认附加 child monitor
- 引入 supervisor policy 与 failure classification
- 让 `Task` 层消费 supervisor decision，而不是直接裸抛 transport 异常

不做：

- 不做多层 supervisor 树
- 不做无限重试或 backoff engine
- 不做 cluster chat bridge supervision

## Implementation Notes

- `down` 必须是结构化事件，不能只是“最后来一个 error string”。
- supervisor 的输入应是结构化 failure class，例如：
  - `child_exit_normal`
  - `child_exit_error`
  - `transport_lost`
  - `remote_worker_error`
  - `aborted`
- v57 第一版 restart 策略只允许小而硬，不做通用策略语言。

## Acceptance (DoD)

必须全部满足：

1. `python -m unittest -q tests.test_actor_supervision tests.test_actor_local_transport tests.test_subagent_task tests.test_remote_task_dispatch`
2. `ruff check openagentic_sdk/subagents openagentic_sdk/runtime_core/tool_task.py tests/test_actor_supervision.py tests/test_subagent_task.py tests/test_remote_task_dispatch.py --config ruff.toml`
3. 反作弊条款：
   - 不允许用“看到异常字符串就当 down”替代结构化生命周期事件
   - 不允许 supervisor policy 只存在文档，不进入实际决策路径

## Files

- Create: `openagentic_sdk/subagents/actor_supervisor.py`
- Create: `openagentic_sdk/subagents/actor_lifecycle.py`
- Modify: `openagentic_sdk/subagents/actor_registry.py`
- Modify: `openagentic_sdk/runtime_core/tool_task.py`
- Modify: `openagentic_sdk/subagents/remote_types.py`
- Create: `tests/test_actor_supervision.py`
- Modify: `tests/test_subagent_task.py`
- Modify: `tests/test_remote_task_dispatch.py`

## Test Contract

### Contract A — host 默认 monitor child

`tests.test_actor_supervision` 至少覆盖：

- child 正常结束时，host 收到 `down(reason_kind="normal")`
- child 异常结束时，host 收到 `down(reason_kind="child_exit_error")`

### Contract B — supervisor decision 真实驱动 `Task` 结果

`tests.test_remote_task_dispatch` 至少覆盖：

- `transport_lost` 时按 policy 触发 `retry_once_on_transport_loss` 或 `fail_parent_tool_use`
- `child_exit_error` 不会被误当作 transport 失败

### Contract C — abort 有明确收敛

`tests.test_subagent_task` 至少覆盖：

- host abort child 后，child execution 状态进入 `aborted`
- 父侧能看到结构化 `down(reason_kind="aborted")`

## Steps

1. Analysis
   - 读清当前 `ToolResult.is_error`、remote transport failure、abort 现状

2. TDD Red：生命周期事件
   - 先写 `tests/test_actor_supervision.py`
   - 运行到红：`python -m unittest -v tests.test_actor_supervision`

3. TDD Green：monitor / down / supervisor policy
   - 实现 lifecycle 与 policy
   - 跑到绿：`python -m unittest -v tests.test_actor_supervision`

4. TDD Red：`Task` 兼容层
   - 让 `tests.test_subagent_task` / `tests.test_remote_task_dispatch` 先证明还没接 supervisor

5. TDD Green：接入
   - 修改 `tool_task.py`
   - 跑到绿：`python -m unittest -v tests.test_subagent_task tests.test_remote_task_dispatch`

6. Review
   - 更新 `docs/plan/v57-index.md`
   - 确认没有引入 cluster chat bridge 范围漂移

## Evidence

- Date: 2026-03-29
- Env: Windows 11 + PowerShell 7.x
- Status: executed locally
- Verification:
  - `python -m unittest -q tests.test_actor_supervision tests.test_actor_local_transport tests.test_subagent_task tests.test_remote_task_dispatch`
  - `ruff check openagentic_sdk/subagents openagentic_sdk/runtime_core/tool_task.py tests/test_actor_supervision.py tests/test_subagent_task.py tests/test_remote_task_dispatch.py --config ruff.toml`
