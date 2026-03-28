# k3s Remote Chat 手工测试指南（v56 M4）

这份 guide 把 v56 当前两条测试路径分开写清楚：

- `smoke cluster`
  - 继续使用 `_smoke_provider.py`
  - 目标是低成本回归协议、路由语义、并发 contract
- `real-model cluster`
  - 使用 `openagentic.remote.json + .openagentic.remote.env`
  - 目标是验证 host 和 remote subagent 都已经是“真 agent”，不再返回 smoke 固定文案

## 0. 先看端口，不要连错

- `http://127.0.0.1:18766`
  - 这是 `smoke cluster` 常用入口
  - 预期会返回固定 smoke 文案，不是真实模型
- `http://127.0.0.1:18776`
  - 这是 `real-model cluster` 入口
  - 预期会走真实 provider

从当前版本开始，`oa chat --remote-host ...` 连接远程 host 时，会先读一次 `/health` 并打印一行模式提示：

- 如果看到：
  - `warning: remote host is smoke-only; ...`
  - 说明你连到的是 smoke host
- 如果看到：
  - `remote: real-model host (...)`
  - 说明你连到的是 real-model host

最短诊断命令：

```powershell
curl.exe http://127.0.0.1:18766/health
curl.exe http://127.0.0.1:18776/health
```

现在推荐直接看 `deployment_mode`：

- `deployment_mode = "smoke"`
- `deployment_mode = "real-model"`

如果你只是想直接进入聊天，而不想手工开 `kubectl port-forward`，现在可以直接用正式命令：

```powershell
oa chat --k3d-smoke
oa chat --k3d-real
```

这两个命令会自己：

- 选择一个空闲本地端口
- 启动对应 namespace 的 `port-forward`
- 预检 `/health`
- 进入 `oa chat`
- 退出时自动清理 `port-forward`

## 1. 先认清当前 M4 的边界

当前仓库已经具备：

- 独立的 remote cluster 配置层：
  - `openagentic.remote.json`
  - `.openagentic.remote.env`
- real-model 启动入口：
  - `openagentic_sdk.server.cluster_chat_host --remote-config`
  - `openagentic_sdk.subagents.remote_http_worker_server --remote-config`
- real-model 部署模板：
  - `deploy/k8s/v56/chat-host-real.template.yaml`
  - `deploy/k3d/v56-workers-real.template.yaml`
- real-model 渲染 / apply 脚本：
  - `scripts/apply_v56_real_cluster.py`

当前仍然保留的实验性限制：

- 本地 k3d 三节点实验环境仍然复用 `e2e_k3d_tests/_harness.py` 的 authoritative mirror 模型；
- 也就是说，在本机 spike 环境里，节点看到的仓库内容仍然绑定到某个已提交 `HEAD`；
- 仅修改 `openagentic.remote.json` / `.openagentic.remote.env` 时，不必删整个 cluster；
- 但如果你要让当前 local k3d 节点看到新的 SDK 代码提交，还是要刷新 mirror，最稳的方式仍然是重新跑一次 k3d bring-up。

## 2. 需要哪些文件

仓库里提供了两个示例文件：

- `openagentic.remote.example.json`
- `.openagentic.remote.env.example`

你本地实际使用时，创建：

- `openagentic.remote.json`
- `.openagentic.remote.env`

PowerShell 命令：

```powershell
Copy-Item openagentic.remote.example.json openagentic.remote.json
Copy-Item .openagentic.remote.env.example .openagentic.remote.env
```

说明：

- `openagentic.remote.json` 可以进入 Git，它只存结构化配置，不放密钥；
- `.openagentic.remote.env` 只应存在于控制端机器，已经被 `.gitignore` 忽略；
- pod 内不会挂载这个 `.env` 文件本身，只会收到展开后的环境变量。

## 3. `openagentic.remote.json` 现在表达什么

当前示例里预置了两个 remote subagent：

- `research`
  - 节点：`k3d-v56-openagentic-agent-0`
  - 定位：研究型 remote subagent
- `writer`
  - 节点：`k3d-v56-openagentic-agent-1`
  - 定位：写作型 remote subagent

这意味着：

- 你可以显式点名 `research` / `writer`
- 也可以直接说自然语言，让主会话自己判断是否需要派发
- `research` 本质上就是“agent-0 上那个研究者”

## 4. 从零开始的完整 real-model 冷启动流程

### Step 1. 先确认你要测的代码已经进入当前 `HEAD`

```powershell
git status --short
git rev-parse --short HEAD
```

要求：

- 最好工作区干净；
- 至少要保证 SDK 代码的变更已经提交；
- 因为当前本地 k3d 实验环境仍然以 authoritative mirror 的提交态为准。

### Step 2. 准备 remote config 和 env

填好这两个文件：

- `openagentic.remote.json`
- `.openagentic.remote.env`

最小示例：

```text
RIGHTCODE_BASE_URL=...
RIGHTCODE_API_KEY=...
```

如果你在 Windows 11 本机用 k3d，并且希望 real cluster 内的 `WebSearch` / `WebFetch` 能借助本机代理出网，先启动一个 WSL host relay，再把 proxy env 写进 `.openagentic.remote.env`。

启动 relay：

```powershell
wsl -u root -e bash -lc 'nohup python3 /mnt/e/development/openagentic-sdk/scripts/k3d_host_proxy_relay.py --listen-host 0.0.0.0 --listen-port 17897 --upstream-host 127.0.0.1 --upstream-port 7897 >/tmp/oa-k3d-proxy-relay.log 2>&1 </dev/null & echo $! >/tmp/oa-k3d-proxy-relay.pid; cat /tmp/oa-k3d-proxy-relay.pid'
```

停止 relay：

```powershell
wsl -u root -e bash -lc 'if [ -f /tmp/oa-k3d-proxy-relay.pid ]; then kill $(cat /tmp/oa-k3d-proxy-relay.pid); rm -f /tmp/oa-k3d-proxy-relay.pid; fi'
```

对应的 `.openagentic.remote.env` 追加：

```text
HTTP_PROXY=http://host.k3d.internal:17897
HTTPS_PROXY=http://host.k3d.internal:17897
NO_PROXY=127.0.0.1,localhost,.svc,.cluster.local
```

说明：

- `host.k3d.internal` 在 pod 内指向 k3d/docker host；
- WSL 能访问 Windows 的 `127.0.0.1:7897`，所以 relay 可以把 pod 流量转回你本机代理；
- 当前 real chat-host 会用 worker service 的 DNS 名称（`.svc.cluster.local`）派发 remote task，所以 `NO_PROXY` 里保留 `.svc,.cluster.local` 即可；不要指望 Python `urllib` 对 `10.43.0.0/16` 这种 CIDR 一定生效。

### Step 3. 先把本地三节点 k3d 基础环境准备出来

最稳的方式，仍然是先跑一次现有 smoke chat bring-up。  
这一步的意义不是“我要测 smoke”，而是复用它已经成熟的：

- k3d 三节点创建
- authoritative mirror 准备
- `/var/lib/openagentic/repo` 挂载
- `python:3.12-slim` 等镜像预加载

命令：

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_k3d_tests -p \"e2e_remote_chat_basic.py\" -v"'
```

### Step 4. 渲染并 apply real-model manifests

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && PYTHONPATH=/mnt/e/development/openagentic-sdk python scripts/apply_v56_real_cluster.py --remote-config openagentic.remote.json --env-file .openagentic.remote.env --output-dir .openagentic-rendered --apply"'
```

这一步会做：

- 读取 `openagentic.remote.json`
- 读取 `.openagentic.remote.env`
- 先做 remote provider 自检
- 渲染：
  - `.openagentic-rendered/v56-workers-real.yaml`
  - `.openagentic-rendered/chat-host-real.yaml`
- 再 `kubectl apply` 到 `openagentic-v56-real` namespace

### Step 5. 等待 real-model pods ready

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real rollout status deployment/oa-remote-worker-agent-0 --timeout=180s"'
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real rollout status deployment/oa-remote-worker-agent-1 --timeout=180s"'
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real rollout status deployment/oa-cluster-chat-host --timeout=180s"'
```

### Step 6. 看 real-model namespace 里的 pod 状态

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real get pods -o wide"'
```

预期至少能看到：

- `oa-cluster-chat-host-*`
- `oa-remote-worker-agent-0-*`
- `oa-remote-worker-agent-1-*`

而且都应该是 `Running`

### Step 7. 检查 `/health`

先给 host 做端口转发：

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real port-forward service/oa-cluster-chat-host 18776:8766"'
```

另开一个终端：

```powershell
curl.exe http://127.0.0.1:18776/health
```

你至少要看到这些字段：

- `ok`
- `deployment_mode`
- `provider_ready`
- `provider_profiles`
- `config_source`
- `host_node_name`

正确预期：

- `provider_ready` 为 `true`

如果想看 worker health，也可以：

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real port-forward service/oa-remote-worker-agent-0 18765:8765"'
curl.exe http://127.0.0.1:18765/health
```

## 5. 进入 real-model 交互测试

另开一个 PowerShell：

```powershell
oa chat --remote-host http://127.0.0.1:18776
```

### 5.1 先测主会话是不是“真 agent”

输入：

```text
你好
```

再输入：

```text
今天是星期几？
```

正确预期：

- 主会话会正常闲聊；
- 不应再只返回 smoke 的固定兜底文案；
- 尤其不能再只回 `CHAT_HOST_OK`，也不能只回“我可以帮你研究资料、并行拆分研究方向”这种硬编码模板。

### 5.2 测显式点名 research

输入：

```text
请调用 research，只读研究一下 v56 的 remote subagent 路由设计，并返回结论。
```

正确预期：

- 主会话会派发到 `research`
- `research` 实际绑定的是 `agent-0`
- 返回内容应是正常研究结果，而不是 smoke 固定句子

### 5.3 测显式点名 writer

输入：

```text
请调用 writer，把下面这段材料整理成一个简短摘要：v56 先把主会话放到集群，再把只读 remote subagent 分发到不同节点。
```

正确预期：

- 主会话会派发到 `writer`
- 返回内容应是正常摘要，不是固定模板

### 5.4 测自然语言自动路由

输入：

```text
请研究一下 v56 的 remote subagent 路由设计。
```

或者：

```text
请先研究 v56 的 remote subagent 路由设计，再整理成一个摘要。
```

正确预期：

- 不点名时，主会话会依据 agent description / prompt 自己判断；
- 第一条更容易路由到 `research`；
- 第二条通常应先路由 `research`，再路由 `writer`；
- 如果模型自己判断不稳，主会话也可能自己完成，这属于当前真实模型语义的一部分。

## 6. 如何用自然语言把任务派给 agent-0

现在推荐两种说法。

### 6.1 显式点名

因为 `agent-0` 上绑定的名字就是 `research`，所以直接说：

```text
请调用 research，让它只读研究一下这个主题。
```

这就是最稳定的“派给 agent-0”的自然语言方式。

### 6.2 不点名，只表达任务意图

```text
请研究一下这个主题。
```

或者：

```text
先研究，再给我整理成摘要。
```

此时主会话会自己决定：

- 研究任务是否交给 `research`
- 写作任务是否交给 `writer`
- 如果不确定，就主会话自己做，不会来烦用户确认

## 7. 如何确认这次对话真的发生了 remote 派发

CLI 输出里会显示 `session_id`。拿到以后，可以看事件流：

```powershell
$session = "<替换成 session_id>"
(Invoke-RestMethod "http://127.0.0.1:18776/session/$session/events").entries | Where-Object { $_.type -eq "tool.result" } | ConvertTo-Json -Depth 6
```

你应该能在 `tool.result` 里看到类似字段：

- `dispatch_mode`
- `target_node`
- `git_revision`
- `worker_execution_id`

如果是显式点名 `research`，正确预期是：

- `dispatch_mode = "k3s"`
- `target_node = "k3d-v56-openagentic-agent-0"`

## 8. 什么时候必须重建 cluster，什么时候只要重启 real deployments

### 只改了这些，一般不必删整个 cluster

- `.openagentic.remote.env`
- `openagentic.remote.json`
- real-model manifests 本身

做法：

1. 重新跑一遍 `scripts/apply_v56_real_cluster.py --apply`
2. 必要时 `rollout restart`

命令：

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real rollout restart deployment/oa-remote-worker-agent-0"'
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real rollout restart deployment/oa-remote-worker-agent-1"'
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real rollout restart deployment/oa-cluster-chat-host"'
```

### 当前本地 spike 里，改了 SDK 代码后，最稳的还是刷新 authoritative mirror

如果：

- 你改了 Python 代码
- 提交 `HEAD` 变化了
- 你怀疑节点里挂载的 `/var/lib/openagentic/repo` 还是旧 mirror

那么当前本地 k3d 实验路径里，最稳妥的仍然是重新跑一次 Step 3。  
这是 v56 当前本地 spike 的现实限制，不是未来生产化 git pull 模型的最终形态。

## 9. 如果 real-model 还是像 smoke，一步一步这样排查

### 9.1 先看 health

```powershell
curl.exe http://127.0.0.1:18776/health
```

先确认：

- `provider_ready=true`

### 9.2 看 host 日志

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real logs deployment/oa-cluster-chat-host --tail=200"'
```

### 9.3 看 worker 日志

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real logs deployment/oa-remote-worker-agent-0 --tail=200"'
wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real logs deployment/oa-remote-worker-agent-1 --tail=200"'
```

### 9.4 确认你测的是当前提交态

```powershell
git rev-parse --short HEAD
git status --short
```

### 9.5 重新渲染并 apply real manifests

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && PYTHONPATH=/mnt/e/development/openagentic-sdk python scripts/apply_v56_real_cluster.py --remote-config openagentic.remote.json --env-file .openagentic.remote.env --output-dir .openagentic-rendered --apply"'
```

### 9.6 还不对，再刷新基础 k3d 环境

重新执行 Step 3，然后再执行 Step 4 和 Step 5。

## 10. 当前相关文件

- `openagentic.remote.example.json`
- `.openagentic.remote.env.example`
- `scripts/apply_v56_real_cluster.py`
- `scripts/k3d_host_proxy_relay.py`
- `deploy/k8s/v56/chat-host-real.template.yaml`
- `deploy/k3d/v56-workers-real.template.yaml`
- `deploy/k8s/v56/chat-host.yaml`
- `deploy/k3d/v56-workers.yaml`
- `openagentic_sdk/remote_cluster_config.py`
- `openagentic_sdk/server/cluster_chat_host.py`
- `openagentic_sdk/subagents/remote_http_worker_server.py`
- `openagentic_sdk/subagents/remote_http.py`
