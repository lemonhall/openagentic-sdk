# v56 Index

## Vision

v56 的目标不是立刻做成“生产级分布式 agent 平台”，而是先把这条最核心的理论链打通：

- 主会话可以从“本地 `oa chat` 进程”提升为“集群中的主会话 host + 本地 CLI 终端”；
- 现有 `Task` subagent 机制保留语义，但底层执行位置可以是 K3s 集群中的指定节点；
- 远程 subagent 与主会话共享同一套 SDK / 镜像 / Git revision，但 v56 严格限制为只读；
- 在 Windows 11 本机先用 WSL2 + k3d 造一个 3 节点实验场，把远程派发、只读工作区、会话桥接、提交态同步这些硬约束先验证掉。

## Milestones

- **M1: K3s 远程只读 Task 派发**
  - Plan: `docs/plan/v56-k3s-remote-readonly-task-dispatch.md`
  - PRD: `docs/prd/PRD-0056-k3s-distributed-readonly-subagents-v56.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard tests.test_remote_http_transport`
    - `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_task_*.py" -v'`
  - Status: done（2026-03-28；单元/集成与 k3d 三节点 smoke 已绿）

- **M2: 集群主会话 host + 提交态同步**
  - Plan: `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md`
  - PRD: `docs/prd/PRD-0056-k3s-distributed-readonly-subagents-v56.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_remote_chat_bridge tests.test_remote_git_sync_policy tests.test_remote_session_meta`
    - `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_chat_*.py" -v'`
  - Status: todo

## Plan Index

- `docs/plan/v56-k3s-remote-readonly-task-dispatch.md`
- `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md`

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0056-001 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` → `tests.test_agent_config_mapping` → `python -m unittest -q tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard tests.test_remote_http_transport` → OK（2026-03-28）
- REQ-0056-002 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` → `tests.test_remote_task_dispatch` + `e2e_k3d_tests/e2e_remote_task_dispatch_smoke.py` → 单元 + `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_task_*.py" -v'` → OK（2026-03-28）
- REQ-0056-003 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` → `tests.test_remote_worker_protocol` + `tests.test_remote_http_transport` → `python -m unittest -q tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard tests.test_remote_http_transport` → OK（2026-03-28）
- REQ-0056-004 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` + `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `tests.test_remote_task_dispatch` + `e2e_k3d_tests/e2e_remote_task_dispatch_smoke.py` → 远程 worker 校验请求 revision 与本地镜像 HEAD 一致；三节点 smoke OK（2026-03-28）
- REQ-0056-005 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` → `tests.test_remote_readonly_guard` + `e2e_k3d_tests/e2e_remote_task_readonly_smoke.py` → 单元 + readonly smoke OK（2026-03-28）
- REQ-0056-006 → `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `tests.test_remote_chat_bridge` + `e2e_k3d_tests/e2e_remote_chat_basic.py` → M2 todo
- REQ-0056-007 → `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `tests.test_remote_git_sync_policy` + `e2e_k3d_tests/e2e_remote_chat_sync_after_session.py` → M2 todo
- REQ-0056-008 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` + `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `deploy/k3d/v56-cluster.yaml` + `deploy/k3d/v56-workers.yaml` + `e2e_k3d_tests/*` → `e2e_remote_task_*.py` OK（2026-03-28）
- REQ-0056-009 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` + `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `tests.test_remote_worker_protocol` + `tests.test_remote_task_dispatch` → child session metadata 与父侧 `tool.result` 均带 `target_node` / `git_revision` / `worker_execution_id`（2026-03-28）
- REQ-0056-010 → 上述两份计划 → 上述全部测试 → M1 的 unit/integration + k3d smoke 已执行并通过；M2 chat/sync 测试仍待实现

## ECN

- None

## Deltas (Vision vs Reality)

- M1 已落地成“HTTP 长驻 worker + `kubectl port-forward` dispatcher + 三节点 k3d smoke”，远程 `Task` 已真实穿过指定节点，而不是只在父进程伪造 `target_node`。
- WSL 直接访问 `/mnt/e/development/openagentic-sdk` 会被 Git 视为 dirty；为满足 committed-revision contract，M1 smoke 改为先在 `/tmp/openagentic-v56-mirror-<head>` 生成一个按当前 `HEAD` checkout 的干净镜像，再让父会话与 k3d 节点共同指向这份 authoritative workspace。
- k3d 自带 `image import` 在当前 Docker/k3d 组合下会对 multi-arch tar 报假成功；M1 通过 `docker image save --platform linux/amd64` + 节点内 `ctr images import` 预加载 `rancher/mirrored-pause:3.6` 与 `python:3.12-slim`，保证 worker pod 可启动。
- M2 仍未开始：主会话 host、remote chat bridge、会话结束后提交态同步仍在下一里程碑。
