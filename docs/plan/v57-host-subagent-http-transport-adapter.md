# v57 Plan — Host/Subagent HTTP Transport Adapter

## Goal

把现有 remote HTTP worker 链路从“dispatch + NDJSON event stream”升级成 actor transport adapter；当前 M3 实现的真实边界是：远程 transport 接入 `execution_id / child_events / seq / replay / down` 语义，并补齐 `send / abort / close` 的 actor contract。

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
- 让 remote transport 显式实现 `spawn / send / receive / abort / close`
- 引入 remote replay / reconnect contract（当前 slice 仅覆盖 `child_events` 单 mailbox）
- 让 remote worker 对 child lifecycle 产出结构化 `down`
- 保持外层 `Task` 兼容语义
- 让 host abort remote child 时仍走结构化 `down`

不做：

- 不做独立 broker
- 不做 cluster chat bridge 改造
- 不做跨 host actor routing

## Implementation Notes

- 现有 `RemoteTaskRequest` / `RemoteTaskDispatchHandle` 更像 RPC handle；M3 需要把它们重构成 actor transport 兼容对象，而不是继续堆字段。
- 当前实现里的 replay cursor 已带 `mailbox` 参数；本轮 slice 仍只覆盖 `child_events` mailbox，不扩展到多 mailbox cursor。
- 当前实现已引入显式 ACK envelope：transport client 在上层恢复迭代后经 `/send` 回 ACK；对 host `Task` 路径，这条 ACK 发生在 child event 已写入 session store 之后。
- 当前实现已解决“远端 stream 断一下，transport client 不知道从哪里继续”的问题，并补了 host `Task` 走 `HttpRemoteTaskDispatcher` 的自动 reconnect 本地 smoke；k3d e2e 仍主要证明 worker transport replay。
- remote `send` 必须落到显式 `/send` actor endpoint，而不是继续把 control 语义塞进 ad-hoc query params 或隐藏副作用里。
- remote abort 仍可保留独立 `/abort` 入口，但 host 侧 `Task` 必须和本地模式一样监听 `abort_event`，不能只在 local transport 生效。

## Acceptance (DoD)

必须全部满足：

1. `python -m unittest -q tests.test_actor_http_transport tests.test_actor_remote_replay tests.test_remote_http_transport tests.test_remote_task_dispatch tests.test_k3d_dispatcher`
2. `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_actor_*.py\" -v"'`
3. `ruff check openagentic_sdk/subagents openagentic_sdk/runtime_core/tool_task.py tests/test_actor_http_transport.py tests/test_actor_remote_replay.py tests/test_remote_http_transport.py tests/test_remote_task_dispatch.py tests/test_k3d_dispatcher.py e2e_k3d_tests/e2e_remote_actor_basic.py e2e_k3d_tests/e2e_remote_actor_reconnect.py e2e_k3d_tests/_harness.py --config ruff.toml`
4. 反作弊条款：
   - 不允许 reconnect 后靠“重新跑一遍整个 child task”冒充 replay
   - 不允许 remote stream 断了以后只给一个通用 RuntimeError，而没有结构化 `down`
   - 不允许 remote transport 号称 actor 化了，却仍然没有 `send()` / control mailbox 入口
   - 不允许 host abort 只能中断本地 child，而 remote child 继续跑

## Files

- Modify: `openagentic_sdk/subagents/remote_http.py`
- Modify: `openagentic_sdk/subagents/remote_worker.py`
- Modify: `openagentic_sdk/subagents/remote_types.py`
- Modify: `openagentic_sdk/subagents/actor_lifecycle.py`
- Modify: `openagentic_sdk/runtime_core/tool_task.py`
- Modify: `openagentic_sdk/subagents/k3d_dispatcher.py`
- Modify: `tests/test_remote_http_transport.py`
- Modify: `tests/test_remote_task_dispatch.py`
- Modify: `e2e_k3d_tests/_harness.py`
- Create: `tests/test_actor_http_transport.py`
- Create: `tests/test_actor_remote_replay.py`
- Create: `tests/test_k3d_dispatcher.py`
- Create: `e2e_k3d_tests/e2e_remote_actor_basic.py`
- Create: `e2e_k3d_tests/e2e_remote_actor_reconnect.py`

## Test Contract

### Contract A — remote transport 说的是 actor，不是 RPC

`tests.test_actor_http_transport` 至少覆盖：

- `spawn` / `send` / `receive` / `abort` 都通过 actor envelope 驱动
- child event 不再裸露为 transport-specific JSON line

### Contract B — replay / reconnect 正常工作

`tests.test_actor_remote_replay` 至少覆盖：

- transport client 消费到某个 `seq` 后连接中断
- reconnect 后从 `mailbox + after_seq` 指定的最后 ACK 点继续
- transport client 会发送显式 `ack` envelope 到 `/send`
- duplicate `message_id` 不会造成重复 child event
- 当前合同只覆盖 `child_events` 单 mailbox，不覆盖多 mailbox cursor

### Contract C — k3d smoke 验证 worker transport replay

`e2e_remote_actor_reconnect.py` 至少覆盖：

- 客户端对远程 worker 的首个 stream 主动断连一次
- 随后的 `/stream?execution_id=...&after_seq=...` 能继续 replay
- 不出现乱序 / 重复 / 静默吞消息
- 当前不覆盖 host `Task` 自动 reconnect / replay

### Contract D — host `Task` 自动 reconnect 不重派发

`tests.test_remote_task_dispatch` 至少覆盖：

- host 通过 `HttpRemoteTaskDispatcher` 派发远程 child，只发起一次 `/dispatch`
- 首个 stream 中断后，host 自动走 `/stream?execution_id=...&mailbox=child_events&after_seq=...`
- 最终 parent 仍拿到完整 child result 与结构化 `tool.result`

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
- Local verification:
  - `python -m unittest -q tests.test_actor_http_transport tests.test_actor_remote_replay tests.test_remote_http_transport tests.test_remote_task_dispatch tests.test_k3d_dispatcher`
  - `python -m unittest -q`
  - `ruff check openagentic_sdk/subagents openagentic_sdk/runtime_core/tool_task.py tests/test_actor_http_transport.py tests/test_actor_remote_replay.py tests/test_remote_http_transport.py tests/test_remote_task_dispatch.py tests/test_k3d_dispatcher.py e2e_k3d_tests/e2e_remote_actor_basic.py e2e_k3d_tests/e2e_remote_actor_reconnect.py e2e_k3d_tests/_harness.py --config ruff.toml`
- k3d e2e status:
  - `python -m unittest -v e2e_k3d_tests.e2e_remote_actor_basic e2e_k3d_tests.e2e_remote_actor_reconnect`
  - Result in current shell: skipped (`missing required tool: docker`)
- Remaining gaps vs broader v57 intent:
  - 当前 replay/ACK 合同只覆盖 `child_events` 单 mailbox，不扩展到多 mailbox cursor
  - docker-enabled 环境下的 k3d M3 e2e 仍待实跑
- Status: implemented locally as current M3 slice；显式 ACK、mailbox replay、host `Task` 自动 reconnect 本地验证已补齐，待 docker-enabled 环境实跑
