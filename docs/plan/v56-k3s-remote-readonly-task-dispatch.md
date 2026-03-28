# v56 Plan — K3s 远程只读 Task 派发

## Goal

把现有本地 `Task` 子代理链路推进到“可按 agent 名称派发到 K3s 指定节点”的版本，同时保持父子事件流语义不变，并把远程工作区硬性限制为只读。

## PRD Trace

- REQ-0056-001
- REQ-0056-002
- REQ-0056-003
- REQ-0056-004
- REQ-0056-005
- REQ-0056-008
- REQ-0056-009
- REQ-0056-010

## Scope

做：

- 把 `opencode.json{,c}` 的 agent 配置真正映射成 `OpenAgenticOptions.agents`
- 扩展 `AgentDefinition`，让 agent 能声明 `executor.kind=k3s` 与节点绑定信息
- 在 `Task` runtime 路径里增加本地/远程分流
- 设计并实现“长驻 node worker”协议与事件桥接
- 对远程执行加只读工作区 + 工具白名单硬约束
- 提供本地 3 节点 k3d smoke，证明真能把任务派发到指定节点

不做：

- 不做集群主会话 host
- 不做 session 结束后的 Git 同步
- 不做 dirty worktree patch 复制
- 不做 Kubernetes Job-per-task 实现
- 不做远程 agent 写仓库能力

## Implementation Notes（设计约束）

- 现有 `Task` 关键转译点在 `openagentic_sdk/runtime_core/tool_task.py`；v56 必须优先改这里，而不是绕开现有 runtime 另起一套独立调度器。
- 现有 `opencode_config` 已能扫描 `agent` 配置，但 `openagentic_cli/config.py` 尚未将其映射到 `OpenAgenticOptions.agents`；M1 的第一步必须补上这条链。
- v56 采用**长驻 node worker**，原因是它更接近当前 child event stream 语义；如果改成 Job-per-task，会把“父会话实时消费 child 事件”降级成“只拿最终结果”，这不符合 PRD。
- 远程 agent 的 authoritative 代码版本以 dispatch 时解析出的 commit SHA 为准；如果当前工作区 dirty，M1 可以先报错而不是自动同步。
- 远程 agent 的默认工具白名单建议只包含：`Read`、`Glob`、`Grep`、必要时 `WebFetch`；不得默认带写类工具。
- 在本机 WSL2 上，`/mnt/e/...` 工作树会被 Git 视作 dirty；M1 smoke 必须先把当前 `HEAD` checkout 到 `/tmp/openagentic-v56-mirror-<head>`，再把这份干净镜像作为 authoritative workspace 挂进 k3d 节点。
- 当前 Docker 29 + k3d 5.8.3 组合下，`k3d image import` 对 multi-arch tar 会报假成功；M1 的节点预热方式固定为：`docker image save --platform linux/amd64 ...` 后进入各节点执行 `ctr -n k8s.io images import`。

## Acceptance (DoD)

必须全部满足：

1) 单元/集成：
   - `python -m unittest -q tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard tests.test_remote_http_transport`
2) WSL2/k3d smoke：
   - `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_task_*.py" -v'`
3) 反作弊条款：
   - 不允许只在 `tool.result` 里伪造 `target_node`
   - 不允许所谓“远程执行”其实仍在父进程本地跑完
   - 不允许只靠 prompt 约束“不要写文件”而没有 runtime/tool guard

## Files（预期变更路径）

- `openagentic_sdk/options.py`
- `openagentic_cli/config.py`
- `openagentic_sdk/runtime_core/tool_task.py`
- `openagentic_sdk/subagents/remote_types.py`
- `openagentic_sdk/subagents/remote_dispatch.py`
- `openagentic_sdk/subagents/remote_worker.py`
- `openagentic_sdk/subagents/remote_http.py`
- `openagentic_sdk/subagents/remote_http_worker_server.py`
- `openagentic_sdk/subagents/k3d_dispatcher.py`
- `openagentic_sdk/subagents/readonly_policy.py`
- `tests/test_agent_config_mapping.py`
- `tests/test_remote_task_dispatch.py`
- `tests/test_remote_worker_protocol.py`
- `tests/test_remote_readonly_guard.py`
- `tests/test_remote_http_transport.py`
- `e2e_k3d_tests/_harness.py`
- `e2e_k3d_tests/_smoke_provider.py`
- `e2e_k3d_tests/e2e_remote_task_dispatch_smoke.py`
- `e2e_k3d_tests/e2e_remote_task_readonly_smoke.py`
- `deploy/k3d/v56-cluster.yaml`
- `deploy/k3d/v56-workers.yaml`

## Test Contract（先写死，后实现）

### Contract A — agent 配置真正进入 runtime

`tests.test_agent_config_mapping` 至少覆盖：

- `opencode.jsonc` 中声明的 `agent.worker_a.executor.kind = "k3s"` 能进入 `OpenAgenticOptions.agents`
- `node_name`、`workspace.mode`、`tools`、`prompt` 被正确映射
- 缺少 `executor.node_name` 时构建 options 明确失败
- `executor.kind = "local"` 仍映射为现有本地 agent

### Contract B — `Task` 本地/远程分流正确

`tests.test_remote_task_dispatch` 至少覆盖：

- 本地 agent 继续走现有 child runtime 路径
- 远程 agent 走 remote dispatcher 路径
- 父会话继续收到 child event stream
- 最终 `tool.result` 带回：
  - `dispatch_mode == "k3s"`
  - `target_node`
  - `git_revision`
  - `child_session_id`
  - `final_text`

### Contract C — node worker 协议与事件桥接

`tests.test_remote_worker_protocol` 至少覆盖：

- worker 收到执行请求后，能在本地启动 child runtime
- worker 能逐条流出 child event，而不是只返回最后文本
- 父 runtime 能把远程事件重新发回主事件流，并保留 `agent_name` / `parent_tool_use_id`
- worker 异常时，父会话拿到明确的 `tool.result.is_error`

### Contract D — 只读约束不可绕过

`tests.test_remote_readonly_guard` 至少覆盖：

- 远程 agent 默认不暴露 `Write` / `Edit`
- 若模型仍尝试调用写类工具，结果必须是明确拒绝
- 若远程 `Bash` 尝试触发工作区写入，必须被 guard 拦截
- 工作区 mount/路径策略确实是只读，而不是“大家自觉不要写”

### Contract E — k3d 三节点 smoke

`e2e_remote_task_dispatch_smoke.py` 至少覆盖：

1. 启动本地 `1 server + 2 agents` k3d 集群
2. 部署 node worker
3. 配置 `worker_a` 绑定到 node A，`worker_b` 绑定到 node B
4. 主会话依次触发两个 `Task`
5. 断言：
   - `worker_a` 的结果来自 node A
   - `worker_b` 的结果来自 node B
   - 两次结果都带回相同 authoritative `git_revision`

`e2e_remote_task_readonly_smoke.py` 至少覆盖：

1. 派发一个只读远程 agent
2. 强迫其尝试写仓库文件
3. 断言：
   - 写入被拒绝
   - 远程节点上的工作区未变化

## Steps（Strict）

1) Analysis / Design
   - 确认 `Task` 当前本地运行路径、agent 配置载入现状、事件流约束

2) TDD Red：agent 配置映射
   - 新增 `tests/test_agent_config_mapping.py`
   - 先写失败断言：`opencode.jsonc` 的 agent 配置能进入 `OpenAgenticOptions.agents`
   - 运行：`python -m unittest tests.test_agent_config_mapping -v`

3) TDD Green：配置层补齐
   - 扩展 `AgentDefinition`
   - 在 `openagentic_cli/config.py` 中把 agent 配置映射到 `OpenAgenticOptions.agents`
   - 跑到绿：`python -m unittest tests.test_agent_config_mapping -v`

4) TDD Red：远程分流合同
   - 新增 `tests/test_remote_task_dispatch.py`
   - 先写失败断言：`executor.kind=k3s` 触发 remote dispatcher，而不是本地 child runtime
   - 运行：`python -m unittest tests.test_remote_task_dispatch -v`

5) TDD Green：dispatcher 类型与协议
   - 新增 `openagentic_sdk/subagents/remote_types.py`
   - 新增 `openagentic_sdk/subagents/remote_dispatch.py`
   - 在 `tool_task.py` 中接入本地/远程分流
   - 跑到绿：`python -m unittest tests.test_remote_task_dispatch -v`

6) TDD Red：worker 协议与事件桥接
   - 新增 `tests/test_remote_worker_protocol.py`
   - 先写失败断言：远程 worker 能回流 child events
   - 运行：`python -m unittest tests.test_remote_worker_protocol -v`

7) TDD Green：长驻 worker
   - 新增 `openagentic_sdk/subagents/remote_worker.py`
   - 实现执行请求、事件流、错误回传
   - 跑到绿：`python -m unittest tests.test_remote_worker_protocol -v`

8) TDD Red：只读 guard
   - 新增 `tests/test_remote_readonly_guard.py`
   - 先写失败断言：写类工具与写副作用 Bash 被拦截
   - 运行：`python -m unittest tests.test_remote_readonly_guard -v`

9) TDD Green：只读工作区策略
   - 新增 `openagentic_sdk/subagents/readonly_policy.py`
   - 把远程工具白名单与工作区策略接入 dispatcher/worker
   - 跑到绿：`python -m unittest tests.test_remote_readonly_guard -v`

10) E2E Red：k3d 三节点实验环境
   - 新增 `deploy/k3d/v56-cluster.yaml`
   - 新增 `e2e_k3d_tests/e2e_remote_task_dispatch_smoke.py`
   - 新增 `e2e_k3d_tests/e2e_remote_task_readonly_smoke.py`
   - 先让它们在未接通远程路径时失败

11) E2E Green
   - 部署 node worker，修通远程派发链路
   - 运行：
     - `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_task_*.py" -v'`

12) Review / Evidence
   - 回填 `docs/plan/v56-index.md`
   - 检查 Req → Plan → Tests 无断链

## Evidence（当前状态）

- Date: 2026-03-28
- Env: Windows 11 + PowerShell 7.x
- Command + Result:
  - `python -m unittest -q tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard tests.test_remote_http_transport` → OK（7 tests）
  - `ruff check openagentic_sdk/runtime_core/tool_task.py openagentic_sdk/subagents/remote_types.py openagentic_sdk/subagents/remote_worker.py openagentic_sdk/subagents/remote_http.py openagentic_sdk/subagents/k3d_dispatcher.py e2e_k3d_tests tests/test_remote_task_dispatch.py tests/test_remote_worker_protocol.py tests/test_remote_http_transport.py --config ruff.toml` → OK
  - `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_task_*.py" -v'` → OK（3 tests；dispatch node A、dispatch node B、readonly guard）
  - `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && kubectl -n openagentic-v56 get pods -o wide'` → `oa-remote-worker-agent-0` / `oa-remote-worker-agent-1` 均为 `Running`
