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
  - Status: done（2026-03-28；cluster chat bridge、dirty sync contract 与 k3d chat smoke 已绿）

- **M3: 自然语言 remote subagent 路由 + worker 有界并发**
  - Plan: `docs/plan/v56-natural-language-remote-routing-and-bounded-worker-concurrency.md`
  - PRD: `docs/prd/PRD-0056-k3s-distributed-readonly-subagents-v56.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_openai_tool_schemas tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_http_transport tests.test_remote_chat_bridge`
    - `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_chat_*.py\" -v"'`
  - Status: done（2026-03-28；自然语言路由、串行/并发 smoke、worker 默认并发 3 均已验证）

- **M4: 真实 provider 驱动的 cluster host + remote subagents**
  - Plan: `docs/plan/v56-real-provider-cluster-host-and-remote-subagents.md`
  - PRD: `docs/prd/PRD-0056-k3s-distributed-readonly-subagents-v56.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_remote_cluster_config tests.test_remote_http_transport tests.test_remote_chat_bridge`
    - `python -m unittest -q tests.test_openai_tool_schemas tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard tests.test_remote_http_transport tests.test_remote_chat_bridge tests.test_remote_git_sync_policy tests.test_remote_session_meta`
    - `python scripts/apply_v56_real_cluster.py --remote-config openagentic.remote.example.json --env-file .openagentic.remote.env.example --output-dir .openagentic-rendered-smoke`
    - `ruff check openagentic_sdk/options.py openagentic_sdk/remote_cluster_config.py openagentic_sdk/subagents/remote_http.py openagentic_sdk/subagents/remote_worker.py openagentic_sdk/server/cluster_chat_host.py openagentic_sdk/subagents/remote_http_worker_server.py openagentic_sdk/runtime_core/tool_task.py tests/test_remote_cluster_config.py tests/test_remote_http_transport.py tests/test_remote_chat_bridge.py scripts/apply_v56_real_cluster.py --config ruff.toml`
    - 手工 / 半自动 real-model 验收：`/health` 显示 `deployment_mode="real-model"` 与 `provider_ready=true`，闲聊与 research/writer 不再返回 smoke 固定回复
  - Status: done（2026-03-28；自动化验证、real-model `/health` 与真实闲聊已验证；CLI 会明确提示 smoke vs real-model）

## Plan Index

- `docs/plan/v56-k3s-remote-readonly-task-dispatch.md`
- `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md`
- `docs/plan/v56-natural-language-remote-routing-and-bounded-worker-concurrency.md`
- `docs/plan/v56-real-provider-cluster-host-and-remote-subagents.md`

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0056-001 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` → `tests.test_agent_config_mapping` → `python -m unittest -q tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard tests.test_remote_http_transport` → OK（2026-03-28）
- REQ-0056-002 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` → `tests.test_remote_task_dispatch` + `e2e_k3d_tests/e2e_remote_task_dispatch_smoke.py` → 单元 + `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_task_*.py" -v'` → OK（2026-03-28）
- REQ-0056-003 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` → `tests.test_remote_worker_protocol` + `tests.test_remote_http_transport` → `python -m unittest -q tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard tests.test_remote_http_transport` → OK（2026-03-28）
- REQ-0056-004 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` + `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `tests.test_remote_task_dispatch` + `e2e_k3d_tests/e2e_remote_task_dispatch_smoke.py` → 远程 worker 校验请求 revision 与本地镜像 HEAD 一致；三节点 smoke OK（2026-03-28）
- REQ-0056-005 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` → `tests.test_remote_readonly_guard` + `e2e_k3d_tests/e2e_remote_task_readonly_smoke.py` → 单元 + readonly smoke OK（2026-03-28）
- REQ-0056-006 → `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `tests.test_remote_chat_bridge` + `e2e_k3d_tests/e2e_remote_chat_basic.py` → 本地 remote client/CLI bridge + k3d chat smoke OK（2026-03-28）
- REQ-0056-007 → `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `tests.test_remote_git_sync_policy` + `e2e_k3d_tests/e2e_remote_chat_sync_after_session.py` → clean sync / dirty-worktree 阻塞 / cleanup 后恢复派发 OK（2026-03-28）
- REQ-0056-008 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` + `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `deploy/k3d/v56-cluster.yaml` + `deploy/k3d/v56-workers.yaml` + `deploy/k8s/v56/chat-host.yaml` + `e2e_k3d_tests/*` → `e2e_remote_task_*.py` + `e2e_remote_chat_*.py` OK（2026-03-28）
- REQ-0056-009 → `docs/plan/v56-k3s-remote-readonly-task-dispatch.md` + `docs/plan/v56-k3s-cluster-chat-and-committed-sync.md` → `tests.test_remote_worker_protocol` + `tests.test_remote_task_dispatch` + `tests.test_remote_session_meta` → parent/child session metadata 与父侧 `tool.result` 均带 `target_node` / `git_revision` / `worker_execution_id`（2026-03-28）
- REQ-0056-010 → 上述两份计划 → 上述全部测试 → M1 / M2 unit/integration + k3d smoke 均已执行并通过（2026-03-28）
- REQ-0056-011 → `docs/plan/v56-natural-language-remote-routing-and-bounded-worker-concurrency.md` → `tests.test_openai_tool_schemas` → `python -m unittest -q tests.test_openai_tool_schemas tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard tests.test_remote_http_transport tests.test_remote_chat_bridge tests.test_remote_git_sync_policy tests.test_remote_session_meta` + `ruff check openagentic_cli/config.py openagentic_sdk/options.py openagentic_sdk/tools/openai.py openagentic_sdk/runtime_core/query_loop_steps/tool_schemas.py openagentic_sdk/subagents/remote_http.py e2e_k3d_tests/_smoke_provider.py e2e_k3d_tests/e2e_remote_chat_basic.py e2e_k3d_tests/e2e_remote_chat_sync_after_session.py e2e_k3d_tests/e2e_remote_chat_fanout.py tests/test_openai_tool_schemas.py tests/test_agent_config_mapping.py tests/test_remote_http_transport.py tests/test_remote_chat_bridge.py --config ruff.toml` → OK（2026-03-28）
- REQ-0056-012 → `docs/plan/v56-natural-language-remote-routing-and-bounded-worker-concurrency.md` → `tests.test_remote_chat_bridge` + `e2e_k3d_tests/e2e_remote_chat_*.py` → 本地 bridge 测试 + `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_chat_*.py\" -v"'` → OK（2026-03-28）
- REQ-0056-013 → `docs/plan/v56-natural-language-remote-routing-and-bounded-worker-concurrency.md` → `tests.test_agent_config_mapping` + `tests.test_remote_http_transport` → 默认并发 3 与第 4 个任务排队 contract 已验证（2026-03-28）
- REQ-0056-014 → `docs/plan/v56-natural-language-remote-routing-and-bounded-worker-concurrency.md` → `tests.test_openai_tool_schemas` + `tests.test_remote_http_transport` + `e2e_k3d_tests/e2e_remote_chat_*.py` → 具名 agent 提示注入、worker 并发上限与 chat smoke 路由均已验证（2026-03-28）
- REQ-0056-015 → `docs/plan/v56-real-provider-cluster-host-and-remote-subagents.md` → `tests.test_remote_cluster_config` + `python scripts/apply_v56_real_cluster.py --remote-config openagentic.remote.example.json --env-file .openagentic.remote.env.example --output-dir .openagentic-rendered-smoke` → 远程集群配置层与本地 `oa chat` 配置链已分离；自动化 OK（2026-03-28）
- REQ-0056-016 → `docs/plan/v56-real-provider-cluster-host-and-remote-subagents.md` → `.gitignore` + `.openagentic.remote.env.example` + `python scripts/apply_v56_real_cluster.py --remote-config openagentic.remote.example.json --env-file .openagentic.remote.env.example --output-dir .openagentic-rendered-smoke` → 控制端 `.env` 注入模板已打通，pod 不挂载明文 env 文件；自动化 OK（2026-03-28）
- REQ-0056-017 → `docs/plan/v56-real-provider-cluster-host-and-remote-subagents.md` → `tests.test_remote_http_transport` + `tests.test_remote_chat_bridge` → host 下发 provider spec，worker 与 host 均使用真实 provider stub + 正确鉴权头；自动化 OK（2026-03-28）
- REQ-0056-018 → `docs/plan/v56-real-provider-cluster-host-and-remote-subagents.md` → `tests.test_remote_cluster_config` + `tests.test_remote_chat_bridge` → `/health` 暴露 `deployment_mode` / `provider_ready` / `provider_profiles` / `config_source`；自动化 OK（2026-03-28）
- REQ-0056-019 → `docs/plan/v56-real-provider-cluster-host-and-remote-subagents.md` → `docs/guides/k3s-remote-chat-manual-testing.md` + real-model 手工验收 → smoke / real-model 两条路径已文档化，CLI 误连 smoke 会报警；real-model `/health` + 闲聊已手工验证（2026-03-28）

## ECN

- None

## Deltas (Vision vs Reality)

- M1 已落地成“HTTP 长驻 worker + `kubectl port-forward` dispatcher + 三节点 k3d smoke”，远程 `Task` 已真实穿过指定节点，而不是只在父进程伪造 `target_node`。
- WSL 直接访问 `/mnt/e/development/openagentic-sdk` 会被 Git 视为 dirty；为满足 committed-revision contract，M1 smoke 改为先在 `/tmp/openagentic-v56-mirror-<head>` 生成一个按当前 `HEAD` checkout 的干净镜像，再让父会话与 k3d 节点共同指向这份 authoritative workspace。
- k3d 自带 `image import` 在当前 Docker/k3d 组合下会对 multi-arch tar 报假成功；M1 通过 `docker image save --platform linux/amd64` + 节点内 `ctr images import` 预加载 `rancher/mirrored-pause:3.6` 与 `python:3.12-slim`，保证 worker pod 可启动。
- M2 已落地成“cluster-hosted chat host + 本地 CLI remote bridge + session-end committed sync + dirty-worktree 阻塞 + k3d 三节点 chat smoke”。
- cluster host 在容器内不依赖系统 `git` 可执行文件：有 `git` 时走真实 Git contract，无 `git` 时使用启动时工作树基线判定 dirty，并显式忽略 `__pycache__` 这类运行时噪音。
- cluster host 对 remote worker 的寻址改为依赖 Kubernetes Service 注入的 `*_SERVICE_HOST` 环境变量，而不是 pod 内 DNS，避免首次派发时的解析波动。
- M3 目标是把“固定触发词 smoke”推进到“具名 remote subagent + 自然语言路由 + 单 worker 默认并发 3 的受控执行”。
- M4 目标是把当前 smoke provider 驱动的 cluster host / workers 推进到“真实 provider 驱动的真 agent”，同时把远程集群配置层从本地 `oa chat` 配置中独立出来。
- M4 已完成：host / worker 的真实 provider bootstrap、自检、provider spec 下发、env 注入模板渲染、real-model `/health` 与真实闲聊都已验证；同时补上了 smoke / real-model 显式模式标识与 CLI 启动预警，避免把 smoke host 误判成真 agent。
- 本地 k3d 三节点环境额外暴露出一个基础设施问题：node 对 Docker Hub 的 443 出站不稳定时，`kube-system` 的 `coredns` / `metrics-server` / `local-path-provisioner` / `traefik` 相关镜像会卡在 `ImagePullBackOff`；v56 现已在 `e2e_k3d_tests/_harness.py` 里把这些系统镜像一起预加载，避免 fresh cluster 出现 pod DNS 全挂。
