# PRD-0060 — Jaeger LoadBalancer 固定暴露 v60

## Vision

v60 解决的是一个很具体、但会持续影响日常调试体验的问题：

- 现在 Jaeger UI 实际上还是 cluster-internal service；
- 用户虽然只想记住固定地址 `http://127.0.0.1:16686`，但当前实现仍依赖手工 `kubectl port-forward`；
- 这会让“集群已经起来了，但 Jaeger 还打不开”变成常态，运维心智负担过高。

因此，v60 的目标是把 Jaeger 的对外暴露语义补齐成：

- 当本地 k3d/k3s 实验集群处于运行状态时，Jaeger Web UI 直接稳定出现在 `http://127.0.0.1:16686`；
- 用户不再需要手工运行 `kubectl port-forward service/jaeger-query 16686:16686`；
- `oa chat --k3d-real` 的入口、行为与心智模型保持不变；
- v57/v58/v59 已经建立的 tracing / transcript / Jaeger UI 能力不被这轮暴露改造破坏。

## Non-Goals

- v60 不改 `oa chat --k3d-real` 的聊天链路。
- v60 不改 tracing 数据模型、`oa.*` span attributes、transcript API 或 session store。
- v60 不新增新的 CLI 入口、额外的用户命令或新的固定 URL。
- v60 不要求在 Windows 侧新增 portproxy、计划任务或常驻守护脚本。
- v60 不追求“任意真实云 k3s 环境的通用暴露模板”；本轮只把当前本地 `k3d + WSL2 + mirrored networking` 这条实验路径做稳。
- v60 不把 Jaeger、OTel Collector、chat host、remote worker 的镜像构建链重做一遍；只改它们的暴露与集群接入语义。

## Requirements

### REQ-0060-001 — Jaeger Query Service 必须升级为显式的对外暴露语义

- `deploy/k8s/v57/jaeger.yaml` 中的 `jaeger-query` service 不得继续保持默认 `ClusterIP` 语义。
- 它必须显式声明为 `type: LoadBalancer`，从而让“Jaeger 是一个应该被外部访问的固定入口”在 Kubernetes 层成为事实，而不是依赖临时 port-forward。
- `16686` 仍然是唯一固定的 Web UI 端口。

### REQ-0060-002 — k3d 集群层必须把 16686 从 cluster load balancer 映射到宿主机

- 由于当前环境是 `k3d`，仅把 Service 改成 `LoadBalancer` 还不够。
- k3d cluster 配置必须把 `16686` 暴露到宿主机，使得运行在 WSL2 内的 k3d load balancer 能真正监听 `0.0.0.0:16686`。
- 该映射必须成为 cluster config 的一部分，而不是事后手工执行的临时命令。
- 这条要求的根因要在文档中明确写清：
  - 对真实 k3s 而言，`LoadBalancer` 依赖 ServiceLB/hostPort；
  - 对 k3d 而言，hostPort 先落在 node container 内部；
  - 如果不把这个端口继续映射出 container，WSL2/Windows 宿主机仍然看不到 `16686`。

### REQ-0060-003 — 用户入口必须继续收敛为两个固定入口

- 用户侧继续只记：
  - `oa chat --k3d-real`
  - `http://127.0.0.1:16686`
- v60 不允许为了 Jaeger 暴露再引入新的“先跑某条命令再打开浏览器”的常规操作。
- 手工 `kubectl port-forward` 只允许保留在 debug 附录中，且必须降级为非常态排障手段。

### REQ-0060-004 — 文档必须明确区分“需要重建 cluster”的情况与“不需要重建”的情况

- v60 必须明确写出：
  - 修改 k3d port mapping / cluster config 时，通常需要重建 cluster；
  - 修改仓库代码、git 内容、agent 行为时，不应因为 Jaeger 暴露本身而强制重建 cluster；
  - Jaeger UI 的固定暴露是基础设施层变更，不是 git 同步层变更。
- 这条边界必须在手工测试指南或经验包中被明确表达，避免后续再次把“代码更新”和“cluster 拓扑更新”混为一谈。

### REQ-0060-005 — 必须提供可重复验证的固定地址回归证据

- v60 必须提供一组可重复验证，至少覆盖：
  - `jaeger-query` service 已为 `LoadBalancer`
  - k3d cluster config 中存在 `16686` 的 host port mapping
  - 在不运行 `kubectl port-forward` 的前提下，Windows/PowerShell 侧访问 `http://127.0.0.1:16686` 能拿到 Jaeger UI 响应
  - v57/v58/v59 的 tracing / transcript drilldown 能继续工作
- 验证中必须有明确的反作弊条款：
  - 不允许后台偷偷启动一个 `kubectl port-forward` 进程，再宣称“固定地址可用了”
  - 不允许改成别的端口或临时随机端口，再宣称“差不多可用”

### REQ-0060-006 — 这轮暴露改造不得扩大用户心智负担

- 不允许把 Windows/WSL2/k3d/cluster 内部的网络细节泄漏成新的日常操作步骤。
- 如果实现需要额外的 k3d 端口映射、cluster recreate、manifest 调整，这些细节必须由框架文档和脚本收口，而不是要求用户长期记忆。
- 文档中的推荐路径必须保持“先启动集群，再直接打开 `http://127.0.0.1:16686`”这一简单语义。
