# PRD-0061 — Real Runtime 预烘焙镜像 v61

## Vision

v61 解决的是当前 `real-model` 冷启动路径里一个非常具体、但非常影响体验的结构性问题：

- `oa chat --k3d-real` 在 WSL2 冷启动后，虽然不再依赖公网 `pip install`；
- 但 `oa-cluster-chat-host` 与 `oa-remote-worker-*` 仍然会在 Pod 启动命令里执行一次本地 wheelhouse 安装；
- 这会把“WSL2 恢复 + k3d cluster start + deployment rollout”这条冷启动链路继续拉长；
- 用户感知就是：明明镜像、代码、wheelhouse 都已经在本地，却还是要等一大段时间。

因此，v61 的目标是把 `real-model` 的运行时依赖从“容器启动时现装”收口成“镜像预烘焙”：

- `oa-cluster-chat-host` 与 `oa-remote-worker-*` 改用同一个本地预烘焙 runtime image；
- 冷启动时不再执行 `python -m pip install ...`；
- `oa chat --k3d-real` 的用户入口与语义保持不变；
- v57/v58/v59/v60 已建立的 actor、Jaeger、transcript、固定入口语义不被破坏；
- v61 第一阶段只覆盖 `real-model host + real-model workers`，不顺手改 `smoke`。

补充一个已经在现网实验环境里被明确诊断出来的外显症状：

- 当 `real-model` 的 host / worker 因启动期依赖安装失败而未真正起来时，Jaeger Search 页面的 service 列表通常只会剩下 `jaeger-all-in-one`；
- 也就是说，“看不到 `oa-cluster-chat-host-real` / `oa-remote-worker-real`”在 v61 语境下首先应被理解为 real runtime 没起来、没有 span 进 Jaeger，而不是先怀疑 Search UI 自己把服务名藏掉了。

## Non-Goals

- v61 不改 `smoke cluster` 的镜像策略。
- v61 不改 `oa chat --k3d-real` 的命令面、参数面或用户入口。
- v61 不改 provider 配置语义，不引入新的 provider profile。
- v61 不改 actor 协议、supervision、tracing 数据结构或 transcript API。
- v61 不把 `Jaeger UI`、`OTel Collector`、`jaeger-ui-proxy` 统一并入这个 runtime image。
- v61 不做“所有依赖都预烘焙进一个万能镜像”的过度扩张；只覆盖 `real host/worker` 当前必需的 Python 运行时依赖。
- v61 不引入 initContainer / sidecar / volume cache 作为主路径。
- v61 不改变“real-model 仍以 authoritative mirror 的提交态为准”这一现有约束。

## Diagnosed Failure Mode (2026-03-30)

在当前 v60 之前的 real runtime 路径上，已经抓到一条稳定、可复现的失败链：

- `openagentic-v56-real` 里的 `oa-cluster-chat-host` 与 `oa-remote-worker-*` 仍基于 `python:3.12-slim` 启动；
- Pod command 仍然先执行：
  - `python -m pip install -q --no-cache-dir --no-index --find-links /workspace/repo/.openagentic-wheelhouse ...`
- 当 `/workspace/repo/.openagentic-wheelhouse` 不存在或不可用时，容器会直接失败并进入 `CrashLoopBackOff`；
- 典型日志为：
  - `WARNING: Location '/workspace/repo/.openagentic-wheelhouse' is ignored`
  - `ERROR: Could not find a version that satisfies the requirement protobuf<6`
- 在这个故障态下，Jaeger `/api/services` 只剩 `jaeger-all-in-one` 是下游症状，不是独立的 Jaeger Search UI 缺陷。

## Requirements

### REQ-0061-001 — real host / worker 必须切换到同一个预烘焙 runtime image

- `oa-cluster-chat-host` 与 `oa-remote-worker-*` 的 `real-model` manifests 必须改用同一个本地 runtime image。
- 该 image 必须预装当前冷启动路径所需的 Python 运行时依赖，至少包括：
  - `protobuf<6`
  - `opentelemetry-api<2`
  - `opentelemetry-sdk<2`
  - `opentelemetry-exporter-otlp-proto-http<2`
- host 与 worker 不得再各自重复定义一套“启动时安装依赖”的逻辑。

### REQ-0061-002 — real host / worker 的 Pod 启动命令中不得再出现运行时 pip install

- `deploy/k8s/v56/chat-host-real.template.yaml`
- `deploy/k3d/v56-workers-real.template.yaml`

以上 real manifests 中：

- 不允许再包含 `python -m pip install ...`；
- 不允许再依赖 `.openagentic-wheelhouse` 作为 Pod 启动前置步骤；
- 容器启动命令必须只负责设置环境并直接 `exec python -u -m ...`。

这条要求的目标是把“安装依赖”从启动时职责移到镜像构建时职责。

### REQ-0061-003 — runtime image 的构建与导入链路必须是本地化、幂等、可复用的

- v61 必须定义一条明确的本地构建链路，用于在 WSL2 内构建 `real-model` runtime image。
- 该链路必须满足：
  - 可重复执行；
  - 已有镜像时可复用；
  - 不依赖远程镜像仓库推送/拉取；
  - 能导入当前 k3d 三节点实验集群。
- cluster recreate 或首次部署时，框架必须负责把该 runtime image 导入 k3d 节点，而不是让 Pod 运行时自行尝试外网拉取。

### REQ-0061-004 — `oa chat --k3d-real` 的 WSL2 冷启动路径必须不再包含运行时依赖安装

- 在以下前提下：
  - cluster 已存在；
  - authoritative mirror 已存在；
  - runtime image 已构建并可导入节点；
  - 用户执行过 `wsl --shutdown`，随后重新启动 WSL2；
- 再次执行 `oa chat --k3d-real` 时，冷启动路径不得包含：
  - 容器内 `pip install`
  - 容器内 wheel 下载
  - 因 Python 运行时依赖缺失而触发的补装逻辑
- v61 不要求“零等待”，但要求等待只来自：
  - WSL2 恢复
  - k3d cluster start
  - Pod 调度与容器启动
  - 端口转发与 health probe

### REQ-0061-005 — 缺失 runtime image 时必须快速失败并给出明确补救命令

- 如果当前本地没有预期的 runtime image，或该镜像未导入节点：
  - 不允许让 Pod 退回到 `python:3.12-slim + pip install` 的旧路径；
  - 不允许让用户在“为什么还是这么慢”与“是不是又在出网”之间瞎猜；
  - 必须快速失败，并给出明确、可复制的本地构建/导入命令。

### REQ-0061-006 — v61 不得扩大到 smoke cluster 或其它镜像链路

- `smoke cluster` 继续沿用现有 `python:3.12-slim` 路径；
- `jaeger` / `otel-collector` / `jaeger-ui-proxy` 维持现有镜像边界；
- v61 的镜像改造只允许触及：
  - real host image
  - real worker image
  - 对应的 build / preload / apply 脚本与测试

### REQ-0061-007 — 必须提供冷启动回归证据，而不是只看 manifest diff

v61 必须至少提供以下证据链：

1. 文本/单元：
   - real manifests 已切换到预烘焙 runtime image
   - real manifests 中不再包含启动时 `pip install`
2. 集群：
   - runtime image 可被导入 k3d 节点
   - real host / worker rollout 正常
3. 端到端：
   - `wsl --shutdown` 后重新执行 `oa chat --k3d-real`
   - 首次对话可正常返回
   - `http://127.0.0.1:16686` 仍可打开
   - Jaeger 中仍可看到 `oa-cluster-chat-host-real` 与 `oa-remote-worker-real`
4. 判读约束：
   - 对 Jaeger Search / `/api/services` 的检查，必须建立在 `openagentic-v56-real` 的 host / worker rollout healthy 且至少完成过一轮真实对话之后；
   - 如果 `openagentic-v56-real` Pod 仍处于 `CrashLoopBackOff`，或尚未产生 fresh trace，那么 Jaeger 只显示 `jaeger-all-in-one` 应判定为 runtime / rollout 失败，不得误判为 Search UI 问题。

## Acceptance (DoD)

必须全部满足：

1. 文本/配置回归：
   - `python -m unittest -q tests.test_apply_v56_real_cluster tests.test_k3d_real_runtime_image`
2. k3d / real rollout：
   - `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && PYTHONPATH=/mnt/e/development/openagentic-sdk python3 scripts/apply_v56_real_cluster.py --remote-config openagentic.remote.json --env-file .openagentic.remote.env --output-dir .openagentic-rendered --apply"'`
   - `wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real rollout status deployment/oa-remote-worker-agent-0 --timeout=180s && kubectl -n openagentic-v56-real rollout status deployment/oa-remote-worker-agent-1 --timeout=180s && kubectl -n openagentic-v56-real rollout status deployment/oa-cluster-chat-host --timeout=180s"'`
3. 冷启动回归：
   - 手工执行 `wsl --shutdown`
   - 再执行 `oa chat --k3d-real`
   - 首个 `你好啊` 成功返回
4. Jaeger 回归：
   - 先确认：
     - `kubectl -n openagentic-v56-real rollout status deployment/oa-remote-worker-agent-0 --timeout=180s`
     - `kubectl -n openagentic-v56-real rollout status deployment/oa-remote-worker-agent-1 --timeout=180s`
     - `kubectl -n openagentic-v56-real rollout status deployment/oa-cluster-chat-host --timeout=180s`
   - 且在 `oa chat --k3d-real` 下至少完成一轮真实对话后，再检查：
   - `curl.exe http://127.0.0.1:16686/api/services`
   - 返回中包含：
     - `oa-cluster-chat-host-real`
     - `oa-remote-worker-real`
5. 反作弊条款：
   - 不允许保留 `pip install` 但改成“安静安装”后宣称变快
   - 不允许缺镜像时偷偷退回 `python:3.12-slim` 旧路径
   - 不允许只改 manifests、不验证 `wsl --shutdown -> oa chat --k3d-real` 真实冷启动
   - 不允许为了省事把 smoke cluster 一起改坏
