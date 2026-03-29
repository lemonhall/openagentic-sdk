# v60 Plan — Jaeger LoadBalancer 固定暴露

## Goal

把当前 Jaeger UI 的访问方式从“cluster 内服务 + 手工 port-forward”收口成“cluster 启动后，固定地址 `http://127.0.0.1:16686` 直接可用”，同时不改变 `oa chat --k3d-real`、不增加新的用户入口、也不把 Windows/WSL2/k3d 的细节转嫁给用户。

## PRD Trace

- REQ-0060-001
- REQ-0060-002
- REQ-0060-003
- REQ-0060-004
- REQ-0060-005
- REQ-0060-006

## Scope

做：

- 把 `jaeger-query` service 从 cluster-internal service 明确改为 `LoadBalancer`
- 在 k3d cluster config 中加入固定 `16686` host port mapping
- 把“cluster 重建是因为端口映射变化，而不是因为 git 内容变化”写清楚
- 把手工测试指南与相关经验包改成以固定地址为默认路径
- 提供一组能证明“没有依赖 port-forward 也能打开 Jaeger”的回归验证

不做：

- 不改 `oa chat --k3d-real` 的行为
- 不改 Jaeger UI 前端、transcript drilldown、OTel spans、session API
- 不改 chat host / remote worker 的 provider 语义
- 不新增新的 CLI flag
- 不依赖 Windows `netsh interface portproxy`
- 不把 `kubectl port-forward` 继续包装成新的默认命令

## Approaches Considered

### 方案 A：继续保留手工 `kubectl port-forward`

优点：

- 改动最小
- 不需要改 cluster config

缺点：

- 与“固定地址就是默认入口”的目标冲突
- 每次 WSL2 / cluster 重启后都容易失效
- 用户仍要记额外命令，违背当前心智目标

结论：

- 不采用。这只是 debug 方案，不是默认架构。

### 方案 B：使用 `NodePort`

优点：

- Kubernetes 语义简单
- 不一定依赖 ServiceLB

缺点：

- 需要引入额外端口号，容易漂移出 `16686`
- 对用户来说，“为什么 chat 是一个入口、Jaeger 又是另一个 NodePort 语义”不够统一
- 在 k3d 本地实验路径里，最终仍然要处理 container → host 的端口映射问题

结论：

- 不采用。它能工作，但不符合“固定地址、最低心智负担”的设计目标。

### 方案 C：`LoadBalancer` + k3d host port mapping

优点：

- 与用户已经认同的语义一致：Jaeger 是一个固定的外部入口
- 与未来真实 k3s 环境的暴露模型更接近
- 地址可以稳定保持为 `http://127.0.0.1:16686`

缺点：

- 在 k3d 中不是只改 Service 就完，需要同时补 cluster port mapping
- 改 cluster config 后通常需要重建 cluster

结论：

- 采用。这是当前最符合用户语义、未来扩展也最顺的方案。

## Recommended Architecture

### 1. Kubernetes 层：Jaeger Query 改为 `LoadBalancer`

- 修改目标：
  - `deploy/k8s/v57/jaeger.yaml`
- 设计要求：
  - `jaeger-query` service 显式设置 `type: LoadBalancer`
  - Web 端口继续使用 `16686`
- 语义目的：
  - 把“Jaeger 应被外部访问”固化到 manifest，而不是依赖临时转发。

### 2. k3d 层：把 `16686` 从 load balancer container 映射到宿主机

- 修改目标：
  - `deploy/k3d/v56-cluster.yaml`
  - 必要时 `e2e_k3d_tests/_harness.py`
- 设计要求：
  - cluster config 中必须包含固定的 `16686:16686` 端口映射
  - 映射应绑定到 k3d load balancer 对外入口，而不是靠运行后临时 patch
- 关键解释：
  - 在 k3d 里，`LoadBalancer` 服务的对外监听先发生在 node/container 世界；
  - 如果 container 的 `16686` 没有继续映射到 WSL2 宿主机，Windows 浏览器仍然打不开 `127.0.0.1:16686`；
  - 因此，`LoadBalancer` 与 `host port mapping` 在本地 k3d 实验环境里是成对出现的。

### 3. 运行语义：Jaeger 固定地址不再依赖 port-forward

- 默认推荐路径：
  1. 启动/恢复 k3d cluster
  2. 确认 Jaeger deployment ready
  3. 直接访问 `http://127.0.0.1:16686`
- `kubectl port-forward` 的地位调整为：
  - 仅用于 debug 附录
  - 仅在 `LoadBalancer` 路径失效时作为边界定位工具
  - 不再出现在“推荐入口”正文里

### 4. 重建边界：为什么这件事通常需要重建 cluster

- 需要重建 cluster 的情况：
  - k3d cluster config 改了端口映射
  - 需要让 k3d load balancer container 在创建时就带上新的 publish 规则
- 不需要因为 Jaeger 暴露而重建 cluster 的情况：
  - 仅更新 git 内容
  - 仅修改 Python 代码
  - 仅修改聊天/路由/提示词逻辑
  - 仅修改 Jaeger UI 前端静态内容
- 这条边界必须写进文档，否则后续仍会把“代码更新”和“拓扑变更”混在一起。

## Acceptance (DoD)

必须全部满足：

1. Service 语义：
   - `jaeger-query` 明确为 `LoadBalancer`
   - 不是默认 `ClusterIP`
2. k3d 暴露：
   - cluster config 中存在固定的 `16686` host port mapping
   - 重建后的集群能实际把该端口监听到宿主机
3. 固定地址：
   - 在没有运行 `kubectl port-forward` 的前提下，`curl.exe http://127.0.0.1:16686/` 能返回 Jaeger UI 响应
   - 浏览器直接打开 `http://127.0.0.1:16686` 可见 Jaeger 页面
4. 回归：
   - `oa chat --k3d-real` 不受影响
   - 已有 tracing / transcript drilldown 不受影响
5. 文档：
   - 手工测试指南不再把 Jaeger `port-forward` 写成默认步骤
   - 明确写出 cluster recreate 与 git 更新的边界
6. 反作弊条款：
   - 不允许后台残留 `kubectl port-forward service/jaeger-query 16686:16686`
   - 不允许改成随机端口后再宣称“功能可用”

## Files

- Modify: `deploy/k8s/v57/jaeger.yaml`
- Modify: `deploy/k3d/v56-cluster.yaml`
- Modify: `e2e_k3d_tests/_harness.py`
- Modify: `docs/guides/k3s-remote-chat-manual-testing.md`
- Modify: `docs/guides/k3d-wsl2-restart-hardening.md`
- Create: `tests/test_k3d_jaeger_exposure.py`
- Modify: `docs/plan/v60-index.md`
- Create: `docs/prd/PRD-0060-jaeger-loadbalancer-exposure-v60.md`
- Create: `docs/plan/v60-jaeger-loadbalancer-exposure.md`

## Milestones

### M1 — Service 语义与配置收口

- 把 Jaeger service 调整为 `LoadBalancer`
- 为 k3d cluster config 增加固定 `16686` 端口映射
- 补测试，证明 manifest / cluster config 的语义已对齐

DoD：

- `python -m unittest -q tests.test_k3d_jaeger_exposure`
- `wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56 get svc jaeger-query -o jsonpath=\"{.spec.type}\""'`

### M2 — 集群重建与固定地址回归

- 按新 config 重建本地 k3d cluster
- 确认不依赖 `kubectl port-forward` 即可打开 Jaeger
- 回归 chat 与 tracing 主路径

DoD：

- `curl.exe http://127.0.0.1:16686/`
- `oa chat --k3d-real`
- real trace 手工验证：Jaeger 页面可打开，trace 仍可查

### M3 — 文档与经验包收口

- 清理旧文档里“Jaeger 默认靠 port-forward”的表述
- 明确写出什么时候要重建 cluster，什么时候不需要
- 把 `port-forward` 降级为 debug 附录

DoD：

- 文档审阅通过
- 手工测试指南默认入口只保留：
  - `oa chat --k3d-real`
  - `http://127.0.0.1:16686`

## Risks

- 风险 1：仅改 Service 为 `LoadBalancer`，但忘了 k3d host port mapping，导致表面上“语义对了”，实际仍打不开。
  - 缓解：把这两个点写成同一个验收链，测试与文档都必须同时检查。

- 风险 2：cluster recreate 与代码更新边界表达不清，后续又回到“凡是有问题就整 cluster 重建”。
  - 缓解：在手工测试指南里单列“什么时候必须重建 / 什么时候不必”章节。

- 风险 3：为了快速验证，又偷偷回到 `kubectl port-forward`。
  - 缓解：把“无 port-forward 的 curl 验证”写成 DoD 与反作弊条款。

## Notes

- v60 是基础设施收口，不是功能扩张。
- 这轮的关键不是“Jaeger 在集群里能跑”，而是“Jaeger 在用户固定地址上能直接打开”。
- 对当前本地环境而言，`LoadBalancer` 不是一句 manifest 就能完成的事；k3d 端口映射是这个方案不可跳过的一半。
