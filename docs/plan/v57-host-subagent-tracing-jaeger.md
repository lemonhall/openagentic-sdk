# v57 Plan — Host/Subagent Tracing With OTel And Jaeger

## Goal

把 v57 的 actor runtime 接到一套轻量、可落地、可在 k3s 里直接观察的 tracing 栈上：应用侧统一走 OpenTelemetry，集群内通过 OTel Collector 汇聚，再导出到 Jaeger，让我们能在 Jaeger Web UI 中看到至少一条 host → subagent 的完整 trace。

## PRD Trace

- REQ-0057-008
- REQ-0057-011
- REQ-0057-010

## Scope

做：

- 为 host ↔ subagent actor runtime 设计 OTel span / event / link 映射
- 明确 `execution_id`、`message_id`、`seq`、`down`、`supervisor decision` 的 trace 表达
- 在 k3s 中加入最小 tracing 栈：
  - OTel instrumentation
  - OTel Collector
  - Jaeger
- 提供一条可重复的验证链路，证明 Jaeger Web UI 中能看到 host → subagent trace

不做：

- 不把 logs、metrics、profiles 一起纳入本轮
- 不把 Jaeger / Collector 当作 actor mailbox、broker、queue 或 supervisor 本体
- 不把 cluster chat bridge 一并拉进 tracing 改造
- 不在本轮引入 SigNoz、Tempo、Phoenix、Langfuse 等更重或更高层的方案

## Implementation Notes

- OTel 是观测协议层，不是执行协议层；runtime 正确性仍然由 actor runtime 自己负责。
- Collector 只负责接收、处理、导出 telemetry；不得承载业务消息。
- Jaeger 用作第一跳 trace backend + Web UI，目标是轻量 bring-up，而不是全家桶 observability。
- trace 建模上，异步 fan-out / replay / retry 优先使用 span links，不要强行把所有关系都压成单一父子树。
- 第一版属性命名以 `oa.*` 为主，例如：
  - `oa.execution.id`
  - `oa.actor.id`
  - `oa.agent.name`
  - `oa.dispatch.mode`
  - `oa.transport.kind`
  - `oa.message.id`
  - `oa.mailbox`
  - `oa.seq`
  - `oa.reason.kind`

## Acceptance (DoD)

必须全部满足：

1. 单元 / 集成：
   - `python -m unittest -q tests.test_actor_tracing`
2. k3d / tracing：
   - `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_actor_trace_*.py\" -v"'`
3. 手工 UI 验证：
   - 能通过 `kubectl port-forward` 打开 Jaeger Web UI
   - 在 UI 中能查询到至少一条 host → subagent trace
   - 该 trace 至少可见 `oa.execution.id`、`oa.agent.name`、`oa.dispatch.mode`
4. 反作弊条款：
   - 不允许只把 Jaeger 服务部署起来，却没有任何 actor trace 可查
   - 不允许只导出一个“顶层请求 span”，却没有 child execution / transport / lifecycle 关键信息
   - 不允许把 trace backend 当作 actor runtime 的状态来源，再宣称架构更稳

## Files

- Create: `openagentic_sdk/subagents/actor_tracing.py`
- Modify: `openagentic_sdk/runtime_core/tool_task.py`
- Modify: `openagentic_sdk/subagents/actor_local_transport.py`
- Modify: `openagentic_sdk/subagents/remote_http.py`
- Modify: `openagentic_sdk/subagents/remote_worker.py`
- Create: `tests/test_actor_tracing.py`
- Create: `deploy/k8s/v57/otel-collector.yaml`
- Create: `deploy/k8s/v57/jaeger.yaml`
- Create: `e2e_k3d_tests/e2e_remote_actor_trace_smoke.py`
- Modify: `e2e_k3d_tests/_harness.py`
- Modify: `docs/plan/v57-index.md`

## Test Contract

### Contract A — actor 关键语义有稳定 trace 映射

`tests.test_actor_tracing` 至少覆盖：

- host 派发 child execution 时会创建稳定 trace/span
- `spawn` / `send` / `receive` / `down` 会进入 span events 或相关 spans
- `execution_id` / `message_id` / `seq` / `dispatch_mode` 会进入 attributes

### Contract B — local 与 remote 共用同一套 trace 语义

`tests.test_actor_tracing` 至少覆盖：

- local transport 与 remote transport 的核心字段命名一致
- 同一 child execution 的 trace 不会因为 transport 不同而换一套语义

### Contract C — k3d 中能查到真实 trace

`e2e_remote_actor_trace_smoke.py` 至少覆盖：

- 起一个最小 tracing 栈
- 触发一次真实 host → remote subagent 执行
- 通过 Jaeger query API 或等价方式验证 trace 已落地

## Steps

1. Analysis
   - 读清当前 host / local transport / remote transport / worker 的事件边界
   - 锁定需要映射为 spans、events、links 的最小集合

2. TDD Red：trace 映射
   - 先写 `tests/test_actor_tracing.py`
   - 运行到红：`python -m unittest -v tests.test_actor_tracing`

3. TDD Green：runtime instrumentation
   - 新增 `actor_tracing.py`
   - 把 host / local / remote 的关键生命周期接到统一 tracing facade
   - 跑到绿：`python -m unittest -v tests.test_actor_tracing`

4. Infra Red：k3s tracing 栈
   - 先写 / 渲染 Collector 与 Jaeger manifests
   - 让 e2e 证明当前 k3d 环境还查不到 trace

5. Infra Green：Jaeger 可观察
   - 补齐 deploy 与 harness
   - 跑到绿：
     - `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_actor_trace_*.py\" -v"'`

6. Review
   - 更新 `docs/plan/v57-index.md`
   - 复核“Jaeger 只是观测面，不是通信面”
   - 复核没有顺手把 cluster chat bridge 纳入

## Evidence

- Date: 2026-03-29
- Env: Windows 11 + PowerShell 7.x
- Status:
  - local tracing/unit path 已完成并通过：`python -m unittest -q tests.test_actor_tracing`
  - Collector / Jaeger manifests 已落地：`deploy/k8s/v57/otel-collector.yaml`、`deploy/k8s/v57/jaeger.yaml`
  - cluster-host trace smoke 已切到真实 v56 语义：`port-forward -> cluster chat host -> remote subagent -> Jaeger`
  - docker-backed k3d trace smoke 已实跑通过：`wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest -v e2e_k3d_tests.e2e_remote_actor_trace_smoke.TestRemoteActorTraceSmoke.test_jaeger_receives_cluster_chat_host_to_remote_subagent_trace"'`
  - Jaeger Web UI 首页已通过 `kubectl port-forward service/jaeger-query 36686:16686` 验证可打开（HTTP 200）
