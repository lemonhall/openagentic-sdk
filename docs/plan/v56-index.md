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
    - `python -m unittest -q tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard`
    - `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_task_*.py" -v'`
  - Status: todo

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

- REQ-0056-001 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` → `tests.test_agent_config_mapping` → Evidence 未执行（当前仅立项文档）
- REQ-0056-002 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` → `tests.test_remote_task_dispatch` + `e2e_k3d_tests/e2e_remote_task_dispatch_smoke.py` → Evidence 未执行（当前仅立项文档）
- REQ-0056-003 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` → `tests.test_remote_worker_protocol` → Evidence 未执行（当前仅立项文档）
- REQ-0056-004 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` + `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `tests.test_remote_git_sync_policy` + `e2e_k3d_tests/e2e_remote_task_dispatch_smoke.py` → Evidence 未执行（当前仅立项文档）
- REQ-0056-005 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` → `tests.test_remote_readonly_guard` + `e2e_k3d_tests/e2e_remote_task_readonly_smoke.py` → Evidence 未执行（当前仅立项文档）
- REQ-0056-006 → `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `tests.test_remote_chat_bridge` + `e2e_k3d_tests/e2e_remote_chat_basic.py` → Evidence 未执行（当前仅立项文档）
- REQ-0056-007 → `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `tests.test_remote_git_sync_policy` + `e2e_k3d_tests/e2e_remote_chat_sync_after_session.py` → Evidence 未执行（当前仅立项文档）
- REQ-0056-008 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` + `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `deploy/k3d/v56-cluster.yaml` + `e2e_k3d_tests/*` → Evidence 未执行（当前仅立项文档）
- REQ-0056-009 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` + `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `tests.test_remote_session_meta` → Evidence 未执行（当前仅立项文档）
- REQ-0056-010 → 上述两份计划 → 上述全部测试 → Evidence 未执行（当前仅立项文档）

## ECN

- None

## Deltas (Vision vs Reality)

- 当前仓库已有本地 `Task` / `AgentDefinition` 机制，但 CLI 配置层尚未把 `agent` 配置真正映射到 `OpenAgenticOptions.agents`。
- 当前 subagent 运行方式仍是父 runtime 在本进程内直接构造 child runtime；远程派发、集群 host、提交态同步均尚未实现。
- v56 在设计上明确把问题拆成两个里程碑，防止“远程 Task、远程 chat、Git 同步、K3s 实验环境”四件事同时开工导致失控。
