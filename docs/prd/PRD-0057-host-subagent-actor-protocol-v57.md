# PRD-0057 — Host/Subagent Actor Protocol Core v57（local + remote 统一 actor 语义）

## Vision

把当前 host ↔ subagent 之间“`Task` 一次 dispatch + 一条临时事件流”的脆弱通信模型，推进成一套明确、统一、可监督、可恢复的 actor 协议层：

- local subagent 与 remote subagent 不再是两套不同的运行语义，而是同一个 actor 协议的两种 transport；
- host 与 child 之间的交互不再只靠临时 HTTP stream / in-memory generator，而是围绕 `execution_id`、mailbox、monitor、`down`、supervisor policy 形成稳定 contract；
- `Task` 仍然是对模型暴露的外层工具语义，但底层执行层升级为 host-authoritative actor runtime；
- v57 的第一阶段只覆盖 **host ↔ subagent**，不把 cluster chat host ↔ 本地 CLI remote chat bridge 纳入 actor 化范围；
- HTTP 在 v57 中退回为 transport adapter，而不是通信语义本身。

## Non-Goals

- v57 不 actor 化 cluster chat host ↔ 本地 CLI remote chat bridge。
- v57 不引入独立的外部 broker、消息总线、Kafka、NATS 或 Redis 队列。
- v57 不做跨 host 的通用 actor 系统；作用域仅限“一个 host 派生的 child executions”。
- v57 不实现 Erlang/BEAM 全套语义，不做热升级、任意 actor graph、分布式 name service。
- v57 不做 group 负载均衡、跨节点抢占式调度、worker pool 全局最优分配。
- v57 不改变用户对 `Task` 的高层使用方式，不要求用户理解 actor envelope 细节。

## Requirements

### REQ-0057-001 — host ↔ subagent 必须拥有统一的 actor envelope 协议

- v57 必须引入一层显式 actor envelope，作为 host ↔ subagent 的唯一通信语义。
- envelope 至少包含：
  - `protocol_version`
  - `message_id`
  - `execution_id`
  - `sender_actor_id`
  - `recipient_actor_id`
  - `mailbox`
  - `seq`
  - `kind`
  - `payload`
  - `ts`
- local subagent 与 remote subagent 都必须收发同一种 envelope，而不是分别维护“本地 Python object 流”和“远程 HTTP JSON 行”两套协议。

### REQ-0057-002 — 每个 child execution 必须拥有 host-authoritative 的 execution registry 与 mailbox 语义

- host 侧必须把每次 `Task` 派发视为一个独立 `execution`，并分配稳定的 `execution_id`。
- host 必须维护 active execution registry，至少可查询：
  - `execution_id`
  - `agent_name`
  - `dispatch_mode`
  - `state`
  - `target_node`
  - `worker_execution_id`
- 每个 execution 至少具有逻辑上的：
  - host → child control mailbox
  - child → host event mailbox
- mailbox 语义必须明确为“单 mailbox 内按 `seq` 有序追加”，而不是依赖 transport 的偶然顺序。

### REQ-0057-003 — local transport 与 remote transport 必须实现同一个 actor transport contract

- v57 必须定义统一的 `ActorTransport` 或等价接口。
- local transport 与 remote HTTP transport 都必须实现同一个 contract，至少包括：
  - `spawn`
  - `send`
  - `receive`
  - `abort`
  - `close`
- 上层 host runtime / supervisor / registry 不得依赖 transport-specific 细节；它只能依赖 actor 协议与 transport interface。

### REQ-0057-004 — host 必须默认 monitor 每个 child execution，并在 child 退出时收到结构化 `down`

- 每个 `Task` 派发出的 child execution，host 必须自动附加 monitor。
- child 结束时，无论是正常完成、异常崩溃、transport 中断、远端 worker stream 失败还是显式 abort，host 都必须收到一个结构化 `down` 或等价事件。
- `down` 至少包含：
  - `execution_id`
  - `actor_id`
  - `reason_kind`
  - `reason_detail`
  - `final_state`
- host 不得再依赖“是否收到了最后一个 `result`”来猜测 child 是否结束。

### REQ-0057-005 — host 必须拥有显式 supervisor policy，而不是直接把 transport 异常冒泡成脆弱失败

- v57 必须引入 host 侧 supervisor policy。
- 第一版至少支持以下 policy：
  - `no_restart`
  - `retry_once_on_transport_loss`
  - `fail_parent_tool_use`
- restart / retry 的触发条件必须结构化，不得只靠字符串匹配错误文案。
- supervisor policy 只作用于 host 监督的 child execution；v57 不要求 remote worker 内部再套一层 supervisor 树。

### REQ-0057-006 — remote transport 必须支持 replay / ack / reconnect contract，而不是断流即失忆

- remote actor transport 必须支持基于 `execution_id + mailbox + seq` 的 replay contract。
- host 侧必须能表达“我已经消费到哪个 `seq`”；remote transport reconnect 后，必须能从下一个未确认位置继续交付。
- duplicate envelope 必须能通过 `message_id` 或等价 idempotency key 去重。
- v57 不要求做到“任意长久化消息总线”，但必须明确解决“远端 stream 断一下，host 就不知道已收到了哪里”的问题。

### REQ-0057-007 — 现有 `Task` 外层语义必须保持稳定，actor 化只发生在执行层

- 模型侧仍然使用 `Task(agent=..., prompt=...)` 这一套工具语义。
- 父会话最终仍收到 `tool.result`；child event 继续带 `agent_name` / `parent_tool_use_id`。
- `Task` 的行为不允许因为 actor 化而退化成“只拿最终字符串结果，不再回流 child events”。
- 现有本地模式与 k3s remote 模式都必须接到同一套 actor foundation，而不是只改 remote。

### REQ-0057-008 — actor 层可观测性必须覆盖消息、生命周期与监督关系

- 日志 / trace / session metadata 至少要能追到：
  - `execution_id`
  - `message_id`
  - `seq`
  - `actor_id`
  - `monitor/supervisor` 关系
  - `down` 原因
- 现有 CLI trace 在不泄露冗余细节的前提下，至少应能显示 child execution 的稳定身份，而不只是 agent 名字。
- host 侧错误报告必须明确区分：
  - child 业务失败
  - transport 失败
  - remote worker 失败
  - supervision decision

### REQ-0057-009 — 测试合同必须覆盖 actor foundation、本地 transport、远程 replay 与 supervision

必须提供以下测试层级：

- 单元：
  - envelope 序列化 / 反序列化
  - mailbox 顺序 / 去重 / replay cursor
  - supervisor policy 决策
- 集成：
  - local transport 下 child execution 生命周期
  - remote HTTP transport 下 replay / reconnect / `down`
  - `Task` 兼容层仍能回流 child events
- k3d / smoke：
  - remote child stream 中断后 host 仍能得到结构化 `down`
  - reconnect/replay 不会把 child stream 乱序或吞消息

### REQ-0057-010 — v57 必须明确保持边界：不把 cluster chat bridge 一并纳入 actor 改造

- 文档、计划、测试与实现范围都必须明确：v57 的 actor 化只覆盖 host ↔ subagent。
- cluster chat host ↔ 本地 CLI remote chat bridge 继续沿用现有 session/event 桥，不在本轮 actor 化。
- 若施工中发现两条链必须同时改造，必须先写 ECN，再决定是否开 v58；不得在 v57 中隐式扩 scope。

## Acceptance (DoD)

必须全部满足：

1) 单元 / 集成：
   - `python -m unittest -q tests.test_actor_protocol tests.test_actor_mailbox_store tests.test_actor_local_transport tests.test_actor_supervision tests.test_actor_http_transport tests.test_actor_remote_replay tests.test_subagent_task tests.test_remote_task_dispatch tests.test_remote_http_transport`
2) k3d / smoke：
   - `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_actor_*.py\" -v"'`
3) 反作弊条款：
   - 不允许只把现有 `dispatch + event stream` 改个类名就宣称 actor 化完成
   - 不允许 local 与 remote 仍维持两套不同语义，只是在文档里说“它们概念上一样”
   - 不允许没有 `down` / supervisor decision / replay cursor，就宣称通信更稳了
4) 范围约束：
   - 不允许顺手把 cluster chat bridge actor 化后再说“既然都改了就一起做完”

