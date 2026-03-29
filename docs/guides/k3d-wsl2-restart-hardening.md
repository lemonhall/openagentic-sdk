# k3d / WSL2 重启稳态修复说明

这份文档记录 v56 本地 k3d 实验环境在 `WSL2 -> shutdown -> restart` 之后暴露出的几条真实脆弱链路，以及本次已经落地的结构性修复。

## 1. 观察到的真实问题

### 1.1 authoritative mirror 落在 `/tmp`

之前 `e2e_k3d_tests/_harness.py` 把这些状态放在 `/tmp`：

- authoritative git mirror
- cluster head 标记文件

结果：

- WSL2 重启后，这些路径不可靠；
- k3d 节点上的 `/var/lib/openagentic/repo` bind mount 仍然指向旧路径，但宿主路径可能已经空了；
- 下一次 smoke / real bring-up 会出现“节点里看不到 repo 内容”或 cluster 被误判为脏状态。

### 1.2 k3d server 节点在 WSL2 重启后可能没自动起来

真实症状：

- `oa chat --k3d-real` 一启动就报：
  - `The connection to the server 0.0.0.0:43636 was refused`
- `k3d cluster list` 会显示：
  - `SERVERS 0/1`

也就是说，问题并不在 `oa chat` 本身，而在于 WSL2 重启后 `k3d-v56-openagentic-server-0` 没恢复。

### 1.3 real host / worker 启动时依赖公网 `pip install`

之前 real manifests 在容器启动命令里直接执行：

- `python -m pip install ... protobuf/opentelemetry/...`

这带来两个问题：

- pod 每次重启都要再走一遍外网依赖下载；
- 只要代理链路断掉，pod 就会在启动阶段 `CrashLoopBackOff`。

### 1.4 `HTTP_PROXY/HTTPS_PROXY` 被全局注入 pod

之前 `.openagentic.remote.env` 里的代理变量会直接进 host / worker 进程环境。

结果：

- `WebSearch/WebFetch` 当然会走代理；
- 但 `rightcode` provider 请求也会被迫走代理；
- 一旦 relay 不在，连模型请求都会 `connection refused`。

这和“`rightcode` 不需要代理”的目标是冲突的。

## 2. 本次已经落地的修复

### 2.1 k3d 状态目录迁到持久路径

`e2e_k3d_tests/_harness.py` 现在把关键状态迁到了：

- 默认：`~/.cache/openagentic-k3d`
- 可覆盖：`OA_K3D_STATE_DIR`

当前布局：

- `~/.cache/openagentic-k3d/mirrors/openagentic-v56-authoritative`
- `~/.cache/openagentic-k3d/state/openagentic-v56-cluster-head.txt`
- `~/.cache/openagentic-k3d/state/openagentic-v56-mirror-head.txt`

这意味着：

- WSL2 重启后 authoritative mirror 不再随 `/tmp` 一起消失；
- cluster head 标记也不会无端丢掉。

### 2.2 `oa chat --k3d-real` 增加自恢复

`openagentic_cli/k3d_chat.py` 现在会处理两类重启后暂态错误：

1. k3d API 不可达
   - 自动执行 `k3d cluster start v56-openagentic`
2. port-forward 已建立，但 pod 端口暂时还没监听
   - 自动重试 port-forward，而不是立刻把用户打回 traceback

这让 `oa chat --k3d-real` 在 WSL2 重启后的第一轮恢复更稳。

### 2.3 k3d cluster 现在只因拓扑漂移而重建，不再因 git `HEAD` 漂移重建

这在 v60 暴露出一个新问题：

- `deploy/k3d/v56-cluster.yaml` 改了端口映射；
- 但如果当前 working tree 还没提交，`HEAD` 其实没变；
- 结果就是旧 cluster 被错误复用，新的 `16686` host port mapping 根本不会生效。

现在 `_harness.py` 的语义改成了两条独立链路：

- `authoritative mirror` 固定在稳定路径里，新的提交只会原地 `fetch + checkout`
- `cluster head`
- `cluster config signature`

只有这些情况才会删旧 cluster 重建：

- k3d cluster config 渲染结果变了
- cluster 本身不存在了

而 git `HEAD` 变化时的处理变成：

- 更新稳定 mirror 的内容
- 重新 `kubectl apply`
- 对 smoke host / worker 做一次 `rollout restart`

也就是说：

- 改 SDK 代码，不再默认触发整 cluster 重建
- 改端口映射 / volume 拓扑，才需要重建 cluster

这让“基础设施拓扑变更”和“代码内容变更”终于被正确区分开：

- 代码内容变更看 mirror sync + rollout restart
- cluster 端口/挂载拓扑变更看 config signature

### 2.4 k3d 节点镜像预热改成持久 tar cache

之前 `_preload_node_images()` 每次都会：

- `docker image save`
- `docker cp`
- `ctr images import`

即使本机 Docker 已经有镜像、节点里也已经导入过，也还会重复做一遍。

现在语义改成：

- 本机 Docker 缺镜像时，才允许一次 `docker pull`
- 本机 tar archive 存在且 image id 没变时，直接复用
- 节点里已经有目标镜像时，直接跳过 `docker cp + ctr import`

当前 cache 路径：

- `~/.cache/openagentic-k3d/images/<image>-amd64.tar`
- `~/.cache/openagentic-k3d/images/<image>-amd64.image-id.txt`

这意味着：

- “拉外网镜像”不再是每次 bring-up 的默认动作
- 真正需要访问外网的，只剩“本机 Docker 第一次根本没有这个镜像”
- 如果第一次 pull 失败，报错会明确提示：应让 WSL Docker daemon 通过 `http://192.168.50.149:7897` 访问外网
### 2.5 real cluster 改成预烘焙 runtime image 启动

从 v61 开始，`real-model host/worker` 不再依赖 authoritative mirror 里的 wheelhouse。

新的语义是：

- host / worker 共用同一个镜像：`openagentic/python-runtime:v61`
- 运行时依赖在镜像构建期预装：
  - `protobuf<6`
  - `opentelemetry-api<2`
  - `opentelemetry-sdk<2`
  - `opentelemetry-exporter-otlp-proto-http<2`
- real manifests 只负责：
  - 设置环境变量
  - `exec python -u -m ...`

手工构建命令（在 WSL2 的仓库根目录执行）：

```powershell
wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && docker build -f deploy/k8s/v61/openagentic-python-runtime.Dockerfile -t openagentic/python-runtime:v61 ."'
```

`scripts/apply_v56_real_cluster.py --apply` 现在会在 `kubectl apply` 前：

- 检查本地是否已有 `openagentic/python-runtime:v61`
- 若存在，则把它导入 k3d 三个节点
- 若不存在，则快速失败，并直接打印上面的 build 命令

效果：

- real pod 启动期不再执行 `pip install`
- relay 掉了也不会再因为启动期依赖安装失败而把整个 real namespace 打进 `CrashLoopBackOff`

### 2.6 代理只给 Web 工具，不再全局污染 provider

`scripts/apply_v56_real_cluster.py` 现在会把 `.openagentic.remote.env` 里的：

- `HTTP_PROXY`
- `HTTPS_PROXY`
- `NO_PROXY`

转换成：

- `OPENAGENTIC_WEB_HTTP_PROXY`
- `OPENAGENTIC_WEB_HTTPS_PROXY`
- `OPENAGENTIC_WEB_NO_PROXY`

并且不会再把全局 `HTTP_PROXY/HTTPS_PROXY/NO_PROXY` 注入 pod。

同时：

- `openagentic_sdk/tools/web_fetch.py`
- `openagentic_sdk/tools/web_search_tavily.py`

已经改成只在 Web 工具内部读取这些 scoped proxy 变量。

效果：

- `rightcode` provider 走直连；
- `WebSearch/WebFetch` 仍然可以单独走代理；
- relay 掉了以后，模型聊天/写作不会再被代理链路拖死。

### 2.7 `oa chat --k3d-real` 的 rollout 等待改成短轮询 + 总窗口

v61 现场又暴露出另一条冷启动脆弱链路：

- `wsl --shutdown` 之后，`k3d cluster start v56-openagentic` 虽然会返回成功；
- 但 `k3d-v56-openagentic-server-0` 与 kube-apiserver 仍可能在 2 到 4 分钟内反复经历：
  - `SERVERS 0/1`
  - `Error from server (ServiceUnavailable): apiserver not ready`
  - `kubectl rollout status ...` 单次等待 120 秒后直接超时

所以 `openagentic_cli/k3d_chat.py` 现在又补了一层恢复语义：

- 仍然保持用户入口不变：
  - `oa chat --k3d-real`
- 但内部的 rollout 等待从“一次性 `kubectl rollout status --timeout=120s`”改成了：
  - 每次最多等 `15s`
  - 遇到这些情况视为暂态，继续轮询：
    - `apiserver not ready`
    - `ServiceUnavailable`
    - `timed out waiting for the condition`
    - `context deadline exceeded`
    - `client timeout exceeded while awaiting headers`
    - `subprocess.TimeoutExpired`
  - 总恢复窗口放宽到 `240s`

这条改动的意义是：

- 热启动时不会因为一次长阻塞把 CLI 挂住；
- 冷启动时又能跨过 k3d/kube 控制面那段最容易抖动的时间窗；
- 失败时也不再是“120 秒到了就直接 traceback”，而是先把 cluster 醒稳再继续。

## 3. 当前验证结论

这次回归已经验证了下面几件事：

1. k3d 节点 bind mount 已经不再指向 `/tmp/...`
2. WSL2 重启后，`oa chat --k3d-real` 遇到 k3d API 未恢复时，能够通过自恢复路径继续拉起
3. 在 `17897` 没有任何 relay 监听的前提下：
   - real host / worker 仍能成功 rollout
   - `oa chat --k3d-real` 仍能正常直接聊天
   - writer remote subagent 仍能正常执行
4. 当 k3d cluster config 发生漂移时，harness 不再错误复用旧 cluster
5. 在 `2026-03-30` 的真实冷启动回归里：
   - 执行 `wsl --shutdown`
   - 再通过 `ManagedK3dChatPortForward` 走同一条 `oa chat --k3d-real` 恢复链
   - 从冷启动开始到 real host `/health` 恢复，实测约 `279s`
   - 随后真实 writer 派发与 `http://127.0.0.1:16686/api/services` 均恢复正常

换句话说：

- relay 现在只影响 Web 工具的外网访问；
- 不再影响 host / worker 的存活；
- 也不再影响 `rightcode` provider 的正常对话。

## 4. 现在的运维含义

### 4.1 WSL2 重启后，不需要再因为 pod 启动失败去重建整个 cluster

只要代码和 mirror 没坏：

- `oa chat --k3d-real` 会优先尝试把 k3d cluster 拉起来；
- real pods 不再因为启动期 `pip install` 失败而 CrashLoop。

### 4.2 relay 现在退化成“Web 工具专用依赖”

如果你只是：

- 普通聊天
- 使用 writer
- 使用不需要外网检索的 remote subagent

那么 relay 不在也没关系。

只有在你需要这些能力时，relay 才重要：

- `WebSearch`
- `WebFetch`
- 任何依赖 Tavily / DuckDuckGo 的研究任务

## 5. 仍然保留的现实边界

### 5.1 authoritative mirror 仍然是“提交态”

这次修的是“路径持久化”，不是“工作树自动同步”。

所以当前本地 spike 里仍然成立：

- k3d 节点看到的是 authoritative mirror；
- authoritative mirror 以 git `HEAD` 为准；
- 只改 working tree、但没提交时，节点未必能看到最新代码。

### 5.2 relay 还不是系统服务

目前 relay 是否常驻，仍然取决于你是否手动/脚本方式把它拉起来。

但这已经不再是 cluster 存活性的前置条件，只影响 Web 工具。

## 6. 推荐回归顺序

1. `wsl --shutdown`
2. 重新打开一个 PowerShell
3. 执行：
   - `oa chat --k3d-real`
4. 先验证普通聊天
5. 再验证 writer remote subagent
6. 如果要测 research / WebSearch / WebFetch，再单独确认 relay 是否启动
