# v56 Plan — 集群主会话 host 与提交态同步

## Goal

让本地 `oa chat` 可以把主会话放到集群里跑，同时在每次 authoritative 会话结束后，把远程 worker 镜像工作区推进到相同的已提交 revision，为后续远程 subagent 提供稳定一致的代码版本。

## PRD Trace

- REQ-0056-004
- REQ-0056-006
- REQ-0056-007
- REQ-0056-008
- REQ-0056-009
- REQ-0056-010

## Scope

做：

- 增加 cluster-hosted main session host
- 增加本地 CLI 到远程主会话的通信桥
- 让远程主会话继续支持 `Task` 事件回流
- 定义并实现“会话结束后推进到相同 committed HEAD”的同步 contract
- 在本地 3 节点 k3d 环境里跑通 remote chat smoke

不做：

- 不传播 dirty worktree 未提交变更
- 不做公网 ingress / 多用户鉴权体系
- 不做 HA 主会话选主或故障迁移
- 不做自动镜像构建流水线

## Implementation Notes（设计约束）

- v56 的远程 chat 首先服务于实验环境，推荐以 cluster-local service + `kubectl port-forward` 或同等本地隧道方式接入，不强求一步到位做公网入口。
- authoritative 主会话结束后的同步目标是“所有 worker 镜像工作区指向同一 committed SHA”；如果主会话结束时工作区 dirty，同步必须失败并给出 `dirty-worktree` 之类的明确状态。
- 同步动作必须是**显式的 Git contract**，不能偷用“重新打包整个目录”来伪装 Git 同步。
- 主会话 host 与 worker 侧都必须记录 `git_revision`、`worker_execution_id`、`target_node` 等元数据，保证后续排障能落到具体节点与具体执行。

## Acceptance (DoD)

必须全部满足：

1) 单元/集成：
   - `python -m unittest -q tests.test_remote_chat_bridge tests.test_remote_git_sync_policy tests.test_remote_session_meta`
2) WSL2/k3d smoke：
   - `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_chat_*.py" -v'`
3) 反作弊条款：
   - 不允许只是本地起一个额外进程自称“cluster host”
   - 不允许把 dirty worktree 默默同步成某个不确定目录快照
   - 不允许同步步骤成功返回，但下一次远程 agent 仍跑在旧 revision

## Files（预期变更路径）

- `openagentic_cli/args.py`
- `openagentic_cli/repl.py`
- `openagentic_sdk/server/cluster_chat_host.py`
- `openagentic_sdk/server/cluster_chat_client.py`
- `openagentic_sdk/subagents/git_sync.py`
- `openagentic_sdk/subagents/session_meta.py`
- `tests/test_remote_chat_bridge.py`
- `tests/test_remote_git_sync_policy.py`
- `tests/test_remote_session_meta.py`
- `e2e_k3d_tests/e2e_remote_chat_basic.py`
- `e2e_k3d_tests/e2e_remote_chat_sync_after_session.py`
- `deploy/k8s/v56/chat-host.yaml`

## Test Contract（先写死，后实现）

### Contract A — 本地 CLI 能连到集群主会话 host

`tests.test_remote_chat_bridge` 至少覆盖：

- 本地 CLI client 能发起会话、接收 streaming 输出
- 远程主会话能维持 session id / resume
- 主会话触发 `Task` 时，子事件能继续回流到 CLI
- host 不可达时，CLI 快速失败并给出明确错误

### Contract B — Git 提交态同步 policy 正确

`tests.test_remote_git_sync_policy` 至少覆盖：

- authoritative 会话结束时，若工作区 clean，sync 返回目标 revision
- authoritative 会话结束时，若工作区 dirty，sync 返回 `blocked` / `dirty-worktree`
- 下一次远程派发前，worker 镜像工作区已更新到最新 committed SHA
- sync 失败时，不得把 worker 留在“半更新”状态

### Contract C — Session 元数据可追溯

`tests.test_remote_session_meta` 至少覆盖：

- 主会话 metadata 记录当前 authoritative revision
- child session metadata 记录 `target_node`、`dispatch_mode`、`worker_execution_id`
- `tool.result` 与 child session metadata 能交叉定位

### Contract D — k3d 远程 chat smoke

`e2e_remote_chat_basic.py` 至少覆盖：

1. 启动本地三节点集群
2. 启动主会话 host
3. 本地 `oa chat` client 连接到 host
4. 发送 prompt，拿到 streaming 输出
5. 再发送一个会触发 `Task` 的 prompt
6. 断言：
   - session 继续存在
   - 子事件被回流到本地 CLI
   - `tool.result` 带回 `target_node` / `git_revision`

`e2e_remote_chat_sync_after_session.py` 至少覆盖：

1. 启动远程 chat
2. 结束一轮 authoritative 会话
3. 触发同步
4. 再派发远程 subagent
5. 断言：
   - worker revision 已推进
   - dirty worktree 场景下同步明确阻塞

## Steps（Strict）

1) Analysis / Design
   - 确认 `oa chat` 当前 REPL 入口、session id 生命周期、可复用的 server/client 基础设施

2) TDD Red：remote chat bridge
   - 新增 `tests/test_remote_chat_bridge.py`
   - 先写失败断言：本地 CLI 可连到 cluster host 并收 streaming
   - 运行：`python -m unittest tests.test_remote_chat_bridge -v`

3) TDD Green：cluster host / client
   - 新增 `openagentic_sdk/server/cluster_chat_host.py`
   - 新增 `openagentic_sdk/server/cluster_chat_client.py`
   - 在 CLI 中接入 remote host 路径
   - 跑到绿：`python -m unittest tests.test_remote_chat_bridge -v`

4) TDD Red：提交态同步合同
   - 新增 `tests/test_remote_git_sync_policy.py`
   - 先写失败断言：clean 才能同步、dirty 必须阻塞
   - 运行：`python -m unittest tests.test_remote_git_sync_policy -v`

5) TDD Green：Git 同步模块
   - 新增 `openagentic_sdk/subagents/git_sync.py`
   - 实现 authoritative revision 检测与 worker mirror 推进
   - 跑到绿：`python -m unittest tests.test_remote_git_sync_policy -v`

6) TDD Red：session 元数据
   - 新增 `tests/test_remote_session_meta.py`
   - 先写失败断言：主/子会话 metadata 带 revision、target node、execution id
   - 运行：`python -m unittest tests.test_remote_session_meta -v`

7) TDD Green：元数据与追溯
   - 新增 `openagentic_sdk/subagents/session_meta.py`
   - 把相关 metadata 接入主/子会话链路
   - 跑到绿：`python -m unittest tests.test_remote_session_meta -v`

8) E2E Red：remote chat smoke
   - 新增 `deploy/k8s/v56/chat-host.yaml`
   - 新增 `e2e_k3d_tests/e2e_remote_chat_basic.py`
   - 新增 `e2e_k3d_tests/e2e_remote_chat_sync_after_session.py`
   - 先让它们在未接通链路前失败

9) E2E Green
   - 跑通 cluster host、本地 CLI、session-end sync
   - 运行：
     - `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_chat_*.py" -v'`

10) Review / Evidence
   - 回填 `docs/plan/v56-index.md`
   - 检查 Req → Plan → Tests 无断链

## Evidence（当前状态）

- Date: 2026-03-28
- Env: Windows 11 + PowerShell 7.x
- Command + Result:
  - 本轮仅完成 PRD / v56 计划立项，未进入实现与测试阶段
