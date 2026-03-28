# k3s Remote Chat 手工测试指南（v56 M3）

这份 guide 记录 v56 M3 的手工测试方法，目标是验证：

- 本地 `oa chat` 可以连到集群里的主会话 host；
- 主会话可以感知两个具名 remote subagent：
  - `research`
  - `writer`
- 用户既可以显式点名，也可以直接说自然语言，让主会话自己路由；
- 默认编排是串行的：先研究，再写作；
- 对原子研究任务，主会话可以 fan-out 并发派发；
- 同一 remote worker 默认最多同时执行 3 个任务。

## 1. 先明确当前 M3 是什么

当前 `deploy/k8s/v56/chat-host.yaml` 挂的仍然是 smoke host provider：

- `e2e_k3d_tests._smoke_provider:create_host_provider`

这意味着：

- 它已经不再是 M2 那种只认 `CHAT_PING` / `TASK_A` / `TASK_B` 的固定触发桩；
- 它现在会用确定性的自然语言规则，模拟 M3 的路由行为；
- 它不是通用大模型，但已经足够验证“具名 agent + 自然语言路由 + 串行/并发编排”的框架语义。

当前 cluster agents 是：

- `research`
  - 角色：研究型 remote subagent
  - 节点：`k3d-v56-openagentic-agent-0`
  - 约束：只读
- `writer`
  - 角色：写作型 remote subagent
  - 节点：`k3d-v56-openagentic-agent-1`
  - 约束：只读

## 2. bring-up 的推荐方式

当前仓库还没有单独的 `oa cluster up` 命令。最稳的 bring-up 方式，还是直接跑 v56 的 k3d chat smoke：

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_chat_*.py\" -v"'
```

注意：

- k3d authoritative workspace 只看当前 `HEAD`
- 你本地未提交的改动不会自动进集群
- 想验证最新代码，先 `git commit`

## 3. 看集群是否就绪

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56 get pods -o wide"'
```

预期至少能看到：

- `oa-cluster-chat-host-*`
- `oa-remote-worker-agent-0-*`
- `oa-remote-worker-agent-1-*`

并且都处于 `Running`

## 4. 建立本地到 cluster host 的端口转发

新开一个 PowerShell 终端，保持它不要关闭：

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56 port-forward service/oa-cluster-chat-host 18766:8766"'
```

## 5. 本地进入交互式 chat

再开一个终端：

```powershell
oa chat --remote-host http://127.0.0.1:18766
```

## 6. 当前 M3 smoke 环境推荐怎么测

### 6.1 先测主会话是否正常说话

输入：

```text
你好啊
```

预期：

- 主会话返回自然语言问候；
- 不应该再只返回 `CHAT_HOST_OK`

### 6.2 测“默认串行编排”

输入：

```text
请先研究一下 v56 的 remote subagent 路由方案，再根据研究结果写一个简短摘要。
```

预期：

- 主会话先派发 `research`
- 收到研究结果后，再派发 `writer`
- 最终结果里会看到研究结果来自 `k3d-v56-openagentic-agent-0`
- 写作结果来自 `k3d-v56-openagentic-agent-1`

这验证的是：

- 主会话可以串行 orchestrate 多个 remote subagent；
- “先研究，再写作”这类请求，不需要你手工写 `Task(...)`

### 6.3 测“只研究，不写作”

输入：

```text
请帮我研究一下 v56 的 remote subagent 路由设计。
```

预期：

- 主会话只派发 `research`
- 最终结果来自 `k3d-v56-openagentic-agent-0`

### 6.4 测“只写作”

输入：

```text
请把这段内容整理成一个简短摘要。
```

预期：

- 主会话只派发 `writer`
- 最终结果来自 `k3d-v56-openagentic-agent-1`

### 6.5 测“fan-out 并发研究”

输入：

```text
请并发研究四个方向，并把结果汇总给我。
```

预期：

- 主会话一次性派发 4 个研究子任务；
- 4 个任务都会路由到 `research`；
- 主会话最后汇总成一个 `FANOUT_SUMMARY ...`

说明：

- 这里的“并发”只适用于可拆分的原子研究任务；
- 当前 worker 默认 `max_concurrent_tasks=3`，所以第 4 个任务会等待，不会无限制并发。

## 7. 如何用自然语言把任务派给 agent-0

这一层要分两种语义。

### 7.1 你想显式点名

当前框架支持显式点名 agent 名字。M3 smoke 里的名字是：

- `research`
- `writer`

如果你的目标就是 `agent-0` 上的研究者，推荐这样说：

```text
请调用 research，让它只读研究一下 v56 的 remote subagent 路由方案，并返回结论。
```

这背后的语义是：

- `research` 这个名字已经绑定到 `k3d-v56-openagentic-agent-0`
- 所以“点名 research”本质上就是“点名派发到 agent-0 上的研究型 remote subagent”

### 7.2 你不想点名，只想自然说

更多时候你可以直接说任务意图，例如：

```text
请研究一下 v56 的 remote subagent 路由方案。
```

或者：

```text
先研究，再给我整理一个摘要。
```

主会话会根据任务类型自动决定：

- 研究任务交给 `research`
- 写作任务交给 `writer`
- 如果判断不稳，它就自己做，而不是去烦用户确认

这就是当前 M3 约定的默认行为。

## 8. 当前 smoke 与未来真实模型的关系

当前 smoke 已经能验证这些框架语义：

- 主会话可见具名 remote subagent
- 用户可显式点名，也可不点名
- 默认串行编排
- 原子任务允许 fan-out 并发
- worker 有默认并发上限

但它仍然不是“真正的模型理解”。真正上线到模型 provider 后，决定路由的是：

- `Task(agent="research", prompt="...")`
- `Task(agent="writer", prompt="...")`

以及主模型是否根据 agent description / prompt 做出正确选择。

也就是说：

- smoke 负责验证协议与框架语义
- 真模型环境负责验证实际的模型路由质量

## 9. 恢复远程会话

如果你已经拿到了 `session_id`，可以继续：

```powershell
oa resume --remote-host http://127.0.0.1:18766 <session_id>
```

## 10. 当前相关文件

- `deploy/k8s/v56/chat-host.yaml`
- `e2e_k3d_tests/_smoke_provider.py`
- `e2e_k3d_tests/e2e_remote_chat_basic.py`
- `e2e_k3d_tests/e2e_remote_chat_fanout.py`
- `e2e_k3d_tests/e2e_remote_chat_sync_after_session.py`
- `openagentic_sdk/tool_prompts/task.txt`
- `openagentic_sdk/subagents/remote_http.py`
