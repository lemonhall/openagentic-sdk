# v57 Index

## Vision

v57 的目标不是“把所有远程通信都重写成 actor 系统”，而是把最脆弱、最核心的 **host ↔ subagent** 链路从同步 RPC 风格，推进成统一的 actor 协议层：

- local subagent 与 remote subagent 使用同一套 actor 语义；
- HTTP 退回 transport adapter，不再直接定义通信语义；
- host 获得 execution registry、mailbox、monitor、`down`、supervisor policy；
- 可观测性保持轻量：`OpenTelemetry + OTel Collector + Jaeger`，先把 host ↔ subagent trace 看清楚；
- `Task` 对模型与用户的高层语义保持不变；
- v57 明确不 actor 化 cluster chat bridge。

## Milestones

- **M1: Actor Protocol Foundation**
  - Plan: `docs/plan/v57-host-subagent-actor-protocol-foundation.md`
  - PRD: `docs/prd/PRD-0057-host-subagent-actor-protocol-v57.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_actor_protocol tests.test_actor_mailbox_store tests.test_actor_local_transport tests.test_subagent_task`
  - Status: done（verified locally 2026-03-29）

- **M2: Supervision And Recovery**
  - Plan: `docs/plan/v57-host-subagent-supervision-and-recovery.md`
  - PRD: `docs/prd/PRD-0057-host-subagent-actor-protocol-v57.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_actor_supervision tests.test_actor_local_transport tests.test_subagent_task tests.test_remote_task_dispatch`
  - Status: done（verified locally 2026-03-29）

- **M3: HTTP Actor Transport Adapter**
  - Plan: `docs/plan/v57-host-subagent-http-transport-adapter.md`
  - PRD: `docs/prd/PRD-0057-host-subagent-actor-protocol-v57.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_actor_http_transport tests.test_actor_remote_replay tests.test_remote_http_transport tests.test_remote_task_dispatch tests.test_k3d_dispatcher`
    - `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_actor_*.py\" -v"'`
  - Status: doing（当前真实完成度：本地单元/集成/ruff 已完成 2026-03-29；显式 ACK、`mailbox=child_events` replay、host `Task` 自动 reconnect 本地 smoke 与 k3d e2e 用例已补齐；当前 shell 仍缺 docker，未实跑）

- **M4: OTel + Jaeger Tracing**
  - Plan: `docs/plan/v57-host-subagent-tracing-jaeger.md`
  - PRD: `docs/prd/PRD-0057-host-subagent-actor-protocol-v57.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_actor_tracing`
    - `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_actor_trace_*.py\" -v"'`
  - Status: done（`tests.test_actor_tracing` 已通过；docker-backed k3d trace smoke 已于 2026-03-29 实跑通过，链路为 `port-forward -> cluster chat host -> remote subagent -> Jaeger`；Jaeger Web UI 固定地址为 `http://127.0.0.1:16686`）

## Plan Index

- `docs/plan/v57-host-subagent-actor-protocol-foundation.md`
- `docs/plan/v57-host-subagent-supervision-and-recovery.md`
- `docs/plan/v57-host-subagent-http-transport-adapter.md`
- `docs/plan/v57-host-subagent-tracing-jaeger.md`

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0057-001 → `docs/plan/v57-host-subagent-actor-protocol-foundation.md` → `tests.test_actor_protocol` → executed locally 2026-03-29
- REQ-0057-002 → `docs/plan/v57-host-subagent-actor-protocol-foundation.md` → `tests.test_actor_mailbox_store` + `tests.test_actor_local_transport` → executed locally 2026-03-29
- REQ-0057-003 → `docs/plan/v57-host-subagent-actor-protocol-foundation.md` + `docs/plan/v57-host-subagent-http-transport-adapter.md` → `tests.test_actor_local_transport` + `tests.test_actor_http_transport` + `tests.test_k3d_dispatcher` → M1 local portion executed；M3 local HTTP/send adapter executed 2026-03-29；k3d e2e pending docker-enabled run
- REQ-0057-004 → `docs/plan/v57-host-subagent-supervision-and-recovery.md` → `tests.test_actor_supervision` → executed locally 2026-03-29
- REQ-0057-005 → `docs/plan/v57-host-subagent-supervision-and-recovery.md` → `tests.test_actor_supervision` + `tests.test_remote_task_dispatch` → executed locally 2026-03-29
- REQ-0057-006 → `docs/plan/v57-host-subagent-http-transport-adapter.md` → `tests.test_actor_remote_replay` + `e2e_k3d_tests/e2e_remote_actor_reconnect.py` → local replay unit executed 2026-03-29；当前实现是 `child_events` 单 mailbox + `mailbox/after_seq` replay + 显式 ACK；worker replay smoke authored，current shell skipped due missing docker
- REQ-0057-007 → `docs/plan/v57-host-subagent-actor-protocol-foundation.md` + `docs/plan/v57-host-subagent-http-transport-adapter.md` → `tests.test_subagent_task` + `tests.test_remote_task_dispatch` + `tests.test_remote_http_transport` + `e2e_k3d_tests.e2e_remote_actor_host_reconnect` → local Task compatibility + remote abort/child event flow + host `Task` 自动 reconnect local smoke executed 2026-03-29；k3d host reconnect e2e authored，current shell skipped due missing docker
- REQ-0057-008 → `docs/plan/v57-host-subagent-supervision-and-recovery.md` + `docs/plan/v57-host-subagent-http-transport-adapter.md` → `tests.test_actor_supervision` + `tests.test_cli_trace_renderer` + `tests.test_actor_http_transport` + `tests.test_remote_task_dispatch` → M2 local supervision + CLI trace 已执行；M3 已补 send/down/abort 身份与显式 ACK，但 tracing 集成仍属于 M4
- REQ-0057-011 → `docs/plan/v57-host-subagent-tracing-jaeger.md` → `tests.test_actor_tracing` + `e2e_k3d_tests/e2e_remote_actor_trace_*.py` → local tracing unit executed 2026-03-29；docker-backed k3d trace smoke executed 2026-03-29，真实链路为 `cluster chat host -> remote subagent`；Jaeger Web UI 固定地址 `http://127.0.0.1:16686` 已验证
- REQ-0057-009 → 全部 v57 计划 → `tests.test_actor_*` + `e2e_k3d_tests/e2e_remote_actor_*.py` → local actor/http unit+integration executed 2026-03-29；k3d actor basic/reconnect/host-reconnect authored，current shell skipped due missing docker
- REQ-0057-010 → `docs/plan/v57-index.md` + 全部 v57 计划 → 文档边界审阅 + code review gate → M3 implementation仍限定于 host ↔ subagent；未把 cluster chat bridge 纳入 actor transport 改造

## ECN

- None

## Deltas (Vision vs Reality)

- 当前 reality：host ↔ subagent 更像“一次 dispatch + 一条临时事件流”，而不是 mailbox + monitor + supervisor。
- 当前 reality：local 与 remote transport 仍是两条不同语义链；统一抽象层缺失。
- 当前 progress：M4 已补上 local tracing facade、host/local/remote instrumentation、Collector/Jaeger manifests，并已完成 docker-enabled 的 Jaeger trace e2e 实跑与 UI 可达性验证。
- 当前 reality：cluster chat bridge 已可用，但它不在 v57 actor 改造范围内，必须显式排除。
- 当前 progress：M1/M2 已完成本地验证；M3 已完成当前 slice 的本地实现与回归，并补齐 worker 级 k3d basic/reconnect/host-reconnect e2e、显式 ACK、`mailbox=child_events` replay、host `Task` 自动 reconnect；剩余缺口主要是 docker-enabled 环境下的 M3 实跑，以及未来多 mailbox replay 的扩展。
