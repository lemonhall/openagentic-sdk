# k3s Remote Chat 手工测试与自然语言派发

这份 guide 记录 v56 M2 的手工测试方法，并说明“如何把请求派发到 `agent-0` 节点”在当前 smoke 环境与后续真实模型环境里的区别。

## 1. 先明确当前 M2 是什么

当前 M2 已经打通了这条链路：

- 本地 `oa chat --remote-host ...` 连接到集群里的主会话 host
- 主会话 host 运行在 `k3d-v56-openagentic-server-0`
- 远程 worker 运行在：
  - `k3d-v56-openagentic-agent-0`
  - `k3d-v56-openagentic-agent-1`
- `Task` 工具命中 `executor.kind="k3s"` 的 agent 时，会被转译成远程 HTTP 派发
- child event / `tool.result` / `target_node` / `git_revision` 会回流到主会话
- 每轮 authoritative 会话结束后，host 会做一次 committed-sync 检查

但当前 `deploy/k8s/v56/chat-host.yaml` 里挂的是 smoke host provider：

- `e2e_k3d_tests._smoke_provider:create_host_provider`

所以它不是“真正理解自然语言”的主模型，而是一个固定规则的测试 provider。

## 2. 当前 smoke 环境能识别什么输入

当前只认这几个固定输入：

- `CHAT_PING`
- `TASK_A`
- `TASK_B`

其中：

- `TASK_A` 会派发到 `worker_a`
- `worker_a` 绑定到 `k3d-v56-openagentic-agent-0`
- `TASK_B` 会派发到 `worker_b`
- `worker_b` 绑定到 `k3d-v56-openagentic-agent-1`

所以在 **当前 M2 smoke 部署** 里，如果你问：

> 请把这个任务交给 agent-0

它不会自然理解；因为这里的 host provider 还不是通用模型，只是测试桩。

## 3. 手工测试 M2 的推荐方法

### 3.1 最省事的 bring-up 方式

当前仓库还没有单独的 `oa cluster up` 命令；最稳的 bring-up 方式，就是直接跑 M2 的 k3d chat smoke。  
这一步会：

- 确保三节点 k3d 集群存在
- 准备 authoritative clean mirror
- 应用 worker / chat-host manifests
- 等待 pod ready
- 顺便验证 M2 基本链路

命令：

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_chat_*.py\" -v"'
```

注意：

- k3d authoritative workspace 是按当前 `HEAD` 生成的 clean mirror
- 你本地 **未提交** 的代码改动不会自动出现在 cluster host / remote worker 里
- 所以想测试最新代码，先 `git commit`

### 3.2 看集群是否都起来了

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56 get pods -o wide"'
```

你应该能看到：

- `oa-cluster-chat-host-*`
- `oa-remote-worker-agent-0-*`
- `oa-remote-worker-agent-1-*`

并且都处于 `Running`

### 3.3 本地端口转发到 cluster chat host

新开一个终端，保持它不要关：

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56 port-forward service/oa-cluster-chat-host 18766:8766"'
```

### 3.4 本地进入交互式 chat

再开一个终端：

```powershell
oa chat --remote-host http://127.0.0.1:18766
```

### 3.5 当前 smoke 环境下的交互式测试顺序

先输入：

```text
CHAT_PING
```

预期：

- 主会话返回 `CHAT_HOST_OK`

再输入：

```text
TASK_A
```

预期：

- 主会话会触发 `Task`
- 任务会被派发到 `worker_a`
- `worker_a` 绑定的目标节点是 `k3d-v56-openagentic-agent-0`
- child result 文本里会带出 `k3d-v56-openagentic-agent-0`

如果你要测另一个节点：

```text
TASK_B
```

它会派发到 `k3d-v56-openagentic-agent-1`

### 3.6 恢复远程会话

如果你已经拿到了 `session_id`，可以继续：

```powershell
oa resume --remote-host http://127.0.0.1:18766 <session_id>
```

## 4. 当前怎么“派发到 agent-0”

在 M2 smoke 环境里，当前的“派发到 agent-0”不是靠自然语言，而是靠固定触发词：

- `TASK_A` -> `worker_a` -> `k3d-v56-openagentic-agent-0`

也就是说，**当前的测试方法** 就是用 `TASK_A` 代替“请把任务派给 agent-0”。

这是一种可重复、可断言的 smoke contract，不是最终产品形态。

## 5. 真正的自然语言派发，需要什么条件

如果你想让用户在主会话里直接说自然语言，比如：

> 请让运行在 agent-0 的研究型 subagent 帮我搜索资料并整理结论

那么 host provider 不能再是 smoke provider，而要换成真正的模型 provider。  
同时，主会话必须提前知道有哪些 remote subagent 可用，以及它们各自擅长什么。

最低需要这几个条件：

1. 配置文件里声明多个 agent
2. 每个 agent 有自己的：
   - `description`
   - `prompt`
   - `tools`
   - `executor.kind`
   - `executor.node_name`
3. 主模型在读到用户自然语言后，自己决定调用 `Task`
4. `Task` 的 `agent` 参数必须精确命中某个已配置 agent 名字
5. 该 agent 的 `executor.kind` 必须是 `k3s`

真正决定“去哪个远程节点”的，不是自然语言本身，而是最终生成出来的这次 `Task` tool call 里的：

- `agent`

然后 runtime 再根据这个 agent 的配置，拿到：

- `executor.kind="k3s"`
- `executor.node_name="k3d-v56-openagentic-agent-0"`

## 6. 一个接近 M3 的配置例子

下面这个例子表达的是“两个 remote subagent，分别擅长研究与写作”：

```json
{
  "agent": {
    "researcher_remote": {
      "description": "只读研究型远程 subagent，擅长搜索、阅读、整理资料，固定运行在 agent-0 节点。",
      "prompt": "You are a remote research worker. Read, search, and synthesize. Never modify repository files.",
      "tools": ["Read", "Glob", "Grep", "WebFetch", "WebSearch"],
      "executor": {
        "kind": "k3s",
        "node_name": "k3d-v56-openagentic-agent-0"
      },
      "workspace": {
        "mode": "readonly"
      }
    },
    "writer_remote": {
      "description": "只读写作型远程 subagent，擅长整理结构、撰写初稿，固定运行在 agent-1 节点。",
      "prompt": "You are a remote writing worker. Produce structured drafts from provided material. Never modify repository files.",
      "tools": ["Read", "Glob", "Grep"],
      "executor": {
        "kind": "k3s",
        "node_name": "k3d-v56-openagentic-agent-1"
      },
      "workspace": {
        "mode": "readonly"
      }
    }
  }
}
```

在这种配置下，主模型才有机会把自然语言路由成：

- `Task(agent="researcher_remote", prompt="...")`
- `Task(agent="writer_remote", prompt="...")`

## 7. 自然语言要怎么说，才更容易命中 agent-0

如果你的目标是“高概率把任务路由给 `agent-0` 上的研究型 subagent”，自然语言最好显式带出三件事：

1. 指明要调用哪个 agent 名字，或者至少指明它的角色
2. 指明它运行在 `agent-0`
3. 指明是只读任务，不要改文件

例如：

```text
请调用 researcher_remote，这个 subagent 固定运行在 agent-0。让它只读搜索并整理这个主题的资料，返回结论，不要修改任何文件。
```

或者：

```text
把这件事交给运行在 agent-0 的研究型远程 subagent，只做资料搜索、阅读和总结，不要写文件。
```

但要注意：

- 这仍然是“模型路由”
- 不是协议层 100% 强制
- 如果你要做绝对确定的派发，还是要让上层显式产生 `Task(agent="researcher_remote", ...)`

## 8. M2 与 M3 的边界

M2 已经证明：

- 主会话可以放到 cluster host 上
- 本地 CLI 可以跟它交互
- `Task` 可以派发到远程节点
- 远程结果可以回流

M3 更像是要补上这一层：

- 主会话感知多个具名 remote subagent
- 每个 remote subagent 有自己的人设 / prompt / 工具集 / 节点绑定
- 用户提自然语言
- 主模型根据 agent description + prompt 自然选择合适的 remote subagent

这正是“从固定 smoke 触发词，进入真正自然语言路由”的那一步。

## 9. 相关文件

- `deploy/k8s/v56/chat-host.yaml`
- `e2e_k3d_tests/_smoke_provider.py`
- `e2e_k3d_tests/e2e_remote_chat_basic.py`
- `e2e_k3d_tests/e2e_remote_chat_sync_after_session.py`
- `openagentic_sdk/runtime_core/tool_task.py`
- `openagentic_cli/config.py`
