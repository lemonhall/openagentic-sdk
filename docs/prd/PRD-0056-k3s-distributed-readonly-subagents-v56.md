# PRD-0056 — K3s 分布式只读 Subagent v56（cluster-hosted `oa chat` + remote Task spike）

## Vision

把当前“父会话在本地进程内直接构造子 `AgentRuntime`”的 subagent 机制，推进成一个可实验的分布式模型：

- 本地仍然使用 `oa chat` 这一套交互语义，但主会话可以运行在 K3s 集群中的指定节点上；
- 配置文件里可以声明**有名字的 subagent**，并显式绑定其执行位置；
- 当模型调用 `Task` 工具时，父 runtime 仍然维持原有语义，但底层不再只会本地派生 child runtime，而是可把任务派发给 K3s 集群中的远程同构 worker；
- 远程 subagent 在与父会话一致的代码版本和镜像环境中运行，但 v56 明确限定为**只读工作区**，不允许改仓库内容；
- 第一阶段先在 Windows 11 本机上，通过 WSL2 Ubuntu 24 + Docker + k3d 起一个 `1 server + 2 agents` 的本地三节点实验集群，先把理论模型跑通，再谈真实多机。

## Non-Goals

- v56 不支持远程 subagent 写文件、改代码、执行会修改仓库状态的 `Bash`。
- v56 不支持把**未提交工作区**通过补丁/overlay 自动复制到远程节点；远程执行仅针对可解析的 Git 提交态。
- v56 不做生产级 HA、自动扩缩容、多租户隔离、跨集群调度。
- v56 不做 Windows 原生 K3s 节点；本地实验集群以 Linux 节点为前提。
- v56 不尝试用 Kubernetes Job 替代全部现有子会话语义；第一版以“保持父子会话事件流语义”为最高优先级。

## Requirements

### REQ-0056-001 — 配置文件必须能声明本地/远程两类 agent，并真正进入 runtime

- `opencode.json` / `opencode.jsonc` 的 `agent.<name>` 必须能声明：
  - `description`
  - `prompt`
  - `tools`
  - `executor.kind`（`local` / `k3s`）
  - `executor.node_name` 或等价的节点绑定字段
  - `workspace.mode`（v56 固定要求 `readonly`）
  - `worker.profile` / `image` 等远程执行所需字段
- CLI 配置构建链必须把这些 agent 映射为 `OpenAgenticOptions.agents`；不能停留在“配置能被扫描到，但 runtime 实际拿不到”。
- 未知 agent、未知 executor、缺失节点绑定等配置错误，必须在运行前明确失败。

### REQ-0056-002 — `Task` 语义必须保留，但允许从“本地 child runtime”转译成“远程 K3s 派发”

- 对 `executor.kind=local` 的 agent，现有本地 `Task` 路径必须继续工作。
- 对 `executor.kind=k3s` 的 agent，runtime 必须把 `Task` tool call 转译为远程执行请求，而不是直接在父进程里新建 child runtime。
- 父会话对外可见的事件语义不得被破坏：
  - 子事件继续带 `agent_name`
  - 子事件继续带 `parent_tool_use_id`
  - 父会话最终仍收到 `tool.result`
- 远程 `tool.result` 输出至少包含：
  - `child_session_id`
  - `final_text`
  - `dispatch_mode`
  - `target_node`
  - `git_revision`

### REQ-0056-003 — v56 必须采用“长驻 node worker”模型，而不是每次 `Task` 起一个 Kubernetes Job

- 每个远程执行节点上必须有一个长驻 worker 进程或 service，负责接收子任务请求、运行 child runtime、回传事件流。
- v56 不采用“每次 Task 都创建一个 Job/Pod 再等其结束”的模型。
- 选择长驻 worker 的原因必须体现在实现与测试中：它要支持父会话消费 child event stream，而不只是最后拿一个字符串结果。

### REQ-0056-004 — 远程 subagent 必须运行在与父会话一致的 Git 提交态和镜像环境上

- 父会话在派发远程任务时，必须解析出当前 authoritative Git revision（至少是 commit SHA）。
- 远程 worker 运行 child runtime 前，必须保证本地镜像工作区处于该 revision。
- v56 的环境对齐定义为：
  - 同一 OCI 镜像 digest 或同一 worker profile
  - 同一 Git revision
- 如果父会话工作区存在未提交变更，或者 revision 无法解析，远程派发必须失败得明确，不能静默降级成“随便用一个近似代码版本”。

### REQ-0056-005 — 远程 subagent 工作区必须是只读的，写入类能力要被系统性封死

- 远程 worker 侧工作区必须以只读方式挂载、打开或复制。
- 远程 agent 的默认工具白名单不得包含 `Write`、`Edit`、`NotebookEdit` 等写类工具。
- 即使模型误调用了写类工具，也必须得到明确拒绝，而不是依赖“通常不会调用”。
- 针对仓库状态有副作用的 `Bash` 命令，v56 必须默认拒绝；如果未来要放开，只能在后续版本设计。

### REQ-0056-006 — 本地 `oa chat` 必须能连到集群内主会话 host，并保留当前交互语义

- 本地 CLI 仍以 `oa chat` 为用户入口。
- v56 必须允许把主会话 runtime 运行在集群内，并通过本地 CLI 与之通信。
- 对用户可见的核心语义必须保留：
  - 多轮会话
  - streaming 输出
  - session id / resume 语义
  - `Task` 子会话的事件回流
- 集群主会话 host 不可用时，本地 CLI 必须快速失败并给出明确错误。

### REQ-0056-007 — 会话结束后的代码/环境同步必须有明确 contract，且 v56 只支持提交态同步

- v56 的“同步”定义为：当 authoritative 会话结束后，远程 worker 镜像工作区被推进到与 authoritative 分支头相同的**已提交 revision**。
- v56 不负责传播未提交变更；如果会话结束时工作区 dirty，则同步步骤必须返回 `blocked`/`dirty-worktree` 之类的明确状态。
- 同步完成后，下一次远程 subagent 派发不得落在旧 revision 上。
- 环境同步以镜像 digest / worker profile 一致性为准，不做 ad hoc 虚拟环境复制。

### REQ-0056-008 — 必须提供 Windows 11 本机可复现的三节点实验环境

- 仓库中必须包含本地实验集群配置，能在 WSL2 Ubuntu 24 环境里起一个 `1 server + 2 agents` 的三节点集群。
- 节点命名必须稳定，以便 agent 配置能静态绑定到具体节点。
- 本地实验环境必须足以验证：
  - agent A 被派发到 node A
  - agent B 被派发到 node B
  - 远程工作区只读
  - 主会话到子会话的事件桥接可用

### REQ-0056-009 — Session 元数据与可观测性必须覆盖“谁派给谁、在哪跑、跑的哪版代码”

- child session metadata 至少记录：
  - `parent_session_id`
  - `parent_tool_use_id`
  - `agent_name`
  - `dispatch_mode`
  - `target_node`
  - `git_revision`
  - `worker_execution_id`
- 父会话侧的 `tool.result` 与 child session metadata 必须能相互追溯。
- 远程 worker 失败时，错误信息必须保留 dispatch target 与 execution id，便于定位。

### REQ-0056-010 — 测试合同必须覆盖配置映射、远程派发、只读约束、主会话桥接与本地三节点 smoke

必须提供以下测试层级：

- 单元/集成：
  - config → `OpenAgenticOptions.agents` 映射
  - `Task` 本地/远程分流
  - 远程 worker 协议与事件桥接
  - 只读工具/工作区约束
  - Git revision / dirty worktree contract
- WSL2/k3d smoke：
  - 本地三节点集群启动
  - 主会话 host 可连接
  - 远程 agent 被派发到正确节点
  - 写类能力被拒绝
  - `tool.result` 带回正确节点与 revision 信息

### REQ-0056-011 — 主会话必须能把“具名 remote subagent 清单”显式暴露给模型

- v56 M3 必须允许在配置文件中声明多个短名字的 remote subagent，例如 `research`、`writer`。
- 主会话在构造 `Task` 工具 schema / prompt 时，必须把这些 agent 的可见信息显式提供给模型，至少包括：
  - agent 名字
  - description
  - tools
  - `executor.kind`
  - `executor.node_name`
- 提示内容必须与当前 `Task` 工具的真实入参一致；不得继续使用过时字段名。

### REQ-0056-012 — v56 M3 必须同时支持“显式点名”与“自然语言自动路由”

- 用户在 prompt 里显式点名 agent 名字时，主会话应优先路由到对应的 remote subagent。
- 用户不点名时，主模型必须可以依据 agent description / prompt 自行判断是否要调用某个 remote subagent。
- 如果主模型对是否要派发没有把握，默认策略是“主会话自己处理”，而不是追问用户。
- v56 M3 的默认编排语义是串行：例如先研究，再写作。
- 只有当主会话自己判断任务可以拆成多个原子子任务时，才允许并发 fan-out 后再由主会话汇总。

### REQ-0056-013 — 单个 remote worker 必须有显式的有界并发 contract

- v56 M3 中，每个 remote worker 节点默认最多同时执行 `3` 个任务。
- 超过上限时，不返回 `busy`；而是进入 worker 侧等待队列，直到有执行槽位释放。
- 该并发上限必须是可配置的，并通过 agent config / worker config 真正进入 runtime。
- 该 contract 仅针对单节点 worker；跨节点 group 调度与负载均衡不属于 M3 范围。

### REQ-0056-014 — M3 测试必须覆盖“研究 -> 写作”的串行链和“原子 fan-out”的受控并发

- 单元/集成至少覆盖：
  - `Task` 工具提示里包含具名 agent 清单
  - `Task` 提示与真实参数名一致
  - worker 并发上限配置映射为默认 `3`
  - 同一 worker 的第 `4` 个任务会等待，而不是无限放行
- k3d smoke 至少覆盖：
  - 本地 remote chat host 感知两个具名 remote subagent
  - 用户自然语言要求“先研究后写作”时，主会话会先派 `research` 再派 `writer`
  - 用户自然语言要求“从多个方向并发研究并汇总”时，主会话可并发派发多个研究子任务，再自行汇总
  - 上述 fan-out 场景不突破单 worker 的并发上限 contract

## Acceptance (DoD)

必须全部满足：

1) 单元/集成：
   - `python -m unittest -q tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard tests.test_remote_git_sync_policy tests.test_remote_chat_bridge tests.test_remote_session_meta`
   - `python -m unittest -q tests.test_openai_tool_schemas tests.test_remote_http_transport`
2) WSL2/k3d 三节点 smoke：
   - `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_task_*.py" -v'`
   - `wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p "e2e_remote_chat_*.py" -v'`
3) 反作弊条款：
   - 不允许把远程 agent 假实现成本地执行后只回填一个 `target_node` 字段
   - 不允许 remote worker 拿到可写工作区
   - 不允许只验证 k3d 集群“起起来了”，却没有真正跑通 `Task` 远程派发
4) 默认测试不得依赖真实公网 K3s 集群、不得依赖真实 OpenAI/RightCode 网络请求。
