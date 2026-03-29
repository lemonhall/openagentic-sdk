# v57 Plan — Host/Subagent HTTP Transport Adapter

## Goal

把现有 remote HTTP worker 链路从“dispatch + NDJSON event stream”升级成 actor transport adapter，让远程 transport 也接入同一套 `execution_id / mailbox / seq / replay / down` 语义。

## PRD Trace

- REQ-0057-003
- REQ-0057-006
- REQ-0057-007
- REQ-0057-008
- REQ-0057-009
- REQ-0057-010

## Scope

做：

- 把 remote HTTP transport 改造成 actor transport adapter
- 引入 remote replay / ack / reconnect contract
- 让 remote worker 对 child lifecycle 产出结构化 `down`
- 保持外层 `Task` 兼容语义

不做：

- 不做独立 broker
- 不做 cluster chat bridge 改造
- 不做跨 host actor routing

## Implementation Notes

- 现有 `RemoteTaskRequest` / `RemoteTaskDispatchHandle` 更像 RPC handle；M3 需要把它们重构成 actor transport 兼容对象，而不是继续堆字段。
- remote replay 的主键必须是 `execution_id + mailbox + seq`。
- ACK 语义应以 host 实际消费到的 mailbox cursor 为准，而不是 transport socket 读到了多少字节。
- remote worker stream 中断后，host 不能丢失“已经收到多少、还缺多少、child 当前是否已结束”的认知。

## Acceptance (DoD)

必须全部满足：

1. `python -m unittest -q tests.test_actor_http_transport tests.test_actor_remote_replay tests.test_remote_http_transport tests.test_remote_task_dispatch`
2. `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_actor_*.py\" -v"'`
3. `ruff check openagentic_sdk/subagents openagentic_sdk/runtime_core/tool_task.py tests/test_actor_http_transport.py tests/test_actor_remote_replay.py tests/test_remote_http_transport.py tests/test_remote_task_dispatch.py --config ruff.toml`
4. 反作弊条款：
   - 不允许 reconnect 后靠“重新跑一遍整个 child task”冒充 replay
   - 不允许 remote stream 断了以后只给一个通用 RuntimeError，而没有结构化 `down`

## Files

- Modify: `openagentic_sdk/subagents/remote_http.py`
- Modify: `openagentic_sdk/subagents/remote_worker.py`
- Modify: `openagentic_sdk/subagents/remote_types.py`
- Modify: `openagentic_sdk/runtime_core/tool_task.py`
- Modify: `tests/test_remote_http_transport.py`
- Modify: `tests/test_remote_task_dispatch.py`
- Create: `tests/test_actor_http_transport.py`
- Create: `tests/test_actor_remote_replay.py`
- Create: `e2e_k3d_tests/e2e_remote_actor_basic.py`
- Create: `e2e_k3d_tests/e2e_remote_actor_reconnect.py`

## Test Contract

### Contract A — remote transport 说的是 actor，不是 RPC

`tests.test_actor_http_transport` 至少覆盖：

- `spawn` / `receive` / `abort` 都通过 actor envelope 驱动
- child event 不再裸露为 transport-specific JSON line

### Contract B — replay / reconnect 正常工作

`tests.test_actor_remote_replay` 至少覆盖：

- host 消费到某个 `seq` 后连接中断
- reconnect 后从下一个未确认 `seq` 继续
- duplicate `message_id` 不会造成重复 child event

### Contract C — k3d smoke 验证远程断流恢复

`e2e_remote_actor_reconnect.py` 至少覆盖：

- 远程 worker stream 人工中断一次
- host 仍收到结构化 `down` 或成功 replay
- 不出现乱序 / 重复 / 静默吞消息

## Steps

1. Analysis
   - 读清当前 `remote_http.py` / `remote_worker.py` / `remote_types.py` 的 stream 生命周期

2. TDD Red：HTTP actor transport
   - 写 `tests.test_actor_http_transport`
   - 运行到红：`python -m unittest -v tests.test_actor_http_transport`

3. TDD Green：actor transport adapter
   - 修改 `remote_http.py` / `remote_types.py`
   - 跑到绿：`python -m unittest -v tests.test_actor_http_transport`

4. TDD Red：replay / reconnect
   - 写 `tests.test_actor_remote_replay`
   - 运行到红：`python -m unittest -v tests.test_actor_remote_replay`

5. TDD Green：replay / ack
   - 修改 `remote_http.py` / `remote_worker.py`
   - 跑到绿：`python -m unittest -v tests.test_actor_remote_replay tests.test_remote_http_transport`

6. E2E Red / Green：k3d smoke
   - 新增 `e2e_remote_actor_basic.py` 与 `e2e_remote_actor_reconnect.py`
   - 跑：
     - `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_actor_*.py\" -v"'`

7. Review
   - 更新 `docs/plan/v57-index.md`
   - 复核“没有把 cluster chat bridge 一并纳入”

## Evidence

- Date: 2026-03-29
- Env: Windows 11 + PowerShell 7.x
- Status: planned；not yet executed

