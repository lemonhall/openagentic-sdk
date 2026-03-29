# v61 Plan — Real Runtime 预烘焙镜像

## Goal

把 `real-model` 冷启动路径里“Pod 启动时本地 pip install”这段结构性开销彻底移除，改成预烘焙 runtime image：

- `oa-cluster-chat-host`
- `oa-remote-worker-agent-0`
- `oa-remote-worker-agent-1`

三者在 `real-model` 下共用同一个 runtime image；
冷启动时只允许做 cluster start / rollout / health，不再做运行时依赖安装。

## PRD Trace

- REQ-0061-001
- REQ-0061-002
- REQ-0061-003
- REQ-0061-004
- REQ-0061-005
- REQ-0061-006
- REQ-0061-007

## Scope

做：

- 新增一个仅服务于 `real-model host/worker` 的 Python runtime image
- 修改 real manifests，去掉启动时 `pip install`
- 补充本地 build / preload / apply 链路
- 补充针对 real runtime image 的单元回归
- 跑一次 `wsl --shutdown -> oa chat --k3d-real -> Jaeger` 冷启动回归

不做：

- 不改 smoke cluster
- 不改 Jaeger / OTel Collector / jaeger-ui-proxy 的镜像边界
- 不改 provider 语义
- 不改 actor / tracing / transcript 协议
- 不做远程仓库 push/pull 型镜像分发
- 不顺手优化 cluster recreate 的其它慢点

## Recommended Architecture

### 1. 新增本地 runtime image

- 镜像命名：
  - `openagentic/python-runtime:v61`
- 基础镜像：
  - `python:3.12-slim`
- 预装依赖：
  - `protobuf<6`
  - `opentelemetry-api<2`
  - `opentelemetry-sdk<2`
  - `opentelemetry-exporter-otlp-proto-http<2`

推荐原因：

- 与当前 real host/worker 的 Python 版本保持一致
- 只把“冷启动必须的运行时依赖”烘进去，边界清晰
- 不把整个仓库代码打进镜像，仍然维持现有 authoritative mirror 挂载模型

### 2. real manifests 改成直接运行

`chat-host-real.template.yaml` 与 `v56-workers-real.template.yaml` 改成：

- `image: openagentic/python-runtime:v61`
- `command` 中直接 `exec python -u -m ...`
- 保留现有：
  - `PYTHONPATH=/workspace/repo`
  - `repo` hostPath mount
  - `remote-config`
  - tracing env

删除：

- `python -m pip install ...`
- `.openagentic-wheelhouse` 作为 Pod 启动前置

### 3. build / preload / apply 链路收口

主路径：

1. 在 WSL2 内构建 `openagentic/python-runtime:v61`
2. 导入 k3d 三个节点
3. `apply_v56_real_cluster.py --apply`

建议收口位置：

- `scripts/apply_v56_real_cluster.py`
- 必要时复用/抽取 `e2e_k3d_tests/_harness.py` 里的 image archive cache / import 逻辑

关键约束：

- 不依赖外部 registry
- 已有本地镜像时幂等复用
- 缺镜像时快速失败并提示明确 build 命令

### 4. 冷启动回归边界

v61 只承诺移除“运行时依赖安装”这段慢点，不承诺所有冷启动都秒开。

因此回归重点是：

- 冷启动时 logs / commands 中不再出现 `pip install`
- `oa chat --k3d-real` 能在 WSL2 重启后恢复
- Jaeger 与 transcript 不回归

## Acceptance

必须全部满足：

1. 配置/单元：
   - `python -m unittest -q tests.test_apply_v56_real_cluster tests.test_k3d_real_runtime_image`
2. real rollout：
   - `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && PYTHONPATH=/mnt/e/development/openagentic-sdk python3 scripts/apply_v56_real_cluster.py --remote-config openagentic.remote.json --env-file .openagentic.remote.env --output-dir .openagentic-rendered --apply"'`
3. 冷启动：
   - `wsl --shutdown`
   - `oa chat --k3d-real`
   - 发送 `你好啊`
   - 成功收到回复
4. Jaeger：
   - `curl.exe http://127.0.0.1:16686/api/services`
   - 包含 `oa-cluster-chat-host-real` 与 `oa-remote-worker-real`
5. 反作弊：
   - Pod command 中不得保留任何 `pip install`
   - 不允许只 build 镜像但未导入节点
   - 不允许因为 v61 把 smoke cluster 改坏

## Files

- Create: `deploy/k8s/v61/openagentic-python-runtime.Dockerfile`
- Modify: `deploy/k8s/v56/chat-host-real.template.yaml`
- Modify: `deploy/k3d/v56-workers-real.template.yaml`
- Modify: `scripts/apply_v56_real_cluster.py`
- Modify: `e2e_k3d_tests/_harness.py`（如需复用 image preload 能力）
- Create: `tests/test_k3d_real_runtime_image.py`
- Modify: `docs/guides/k3s-remote-chat-manual-testing.md`
- Modify: `docs/guides/k3d-wsl2-restart-hardening.md`

## Milestones

### M1 — Runtime Image Contract

- 新增 runtime Dockerfile
- real manifests 改用 `openagentic/python-runtime:v61`
- 去掉 Pod 启动时 `pip install`
- 补文本/单元回归

DoD：

- `python -m unittest -q tests.test_apply_v56_real_cluster tests.test_k3d_real_runtime_image`

### M2 — Build / Preload / Apply Pipeline

- 在 WSL2 内 build runtime image
- 导入 k3d 节点
- `apply_v56_real_cluster.py --apply` 收口 build/preload/apply 主路径
- real host / workers rollout 通过

DoD：

- `wsl -u root -e bash -lc 'su - lemonhall -c "cd /mnt/e/development/openagentic-sdk && PYTHONPATH=/mnt/e/development/openagentic-sdk python3 scripts/apply_v56_real_cluster.py --remote-config openagentic.remote.json --env-file .openagentic.remote.env --output-dir .openagentic-rendered --apply"'`
- `wsl -u root -e bash -lc 'su - lemonhall -c "kubectl -n openagentic-v56-real rollout status deployment/oa-remote-worker-agent-0 --timeout=180s && kubectl -n openagentic-v56-real rollout status deployment/oa-remote-worker-agent-1 --timeout=180s && kubectl -n openagentic-v56-real rollout status deployment/oa-cluster-chat-host --timeout=180s"'`

### M3 — WSL2 冷启动回归

- 手工执行 `wsl --shutdown`
- 再执行 `oa chat --k3d-real`
- 验证真实对话、Jaeger UI、service 列表
- 更新手工测试文档

DoD：

- `oa chat --k3d-real`
- `curl.exe http://127.0.0.1:16686/api/services`

## Risks

- 风险 1：只把 Dockerfile 写出来，但 `apply_v56_real_cluster.py` 没负责 build/import，导致冷启动时 Pod 仍然卡在找不到镜像。
  - 缓解：把“build + preload + apply”收成同一条默认链路。

- 风险 2：real manifests 虽然换了 image，但 command 里还残留 `pip install`。
  - 缓解：把“无 pip install”写成单元测试与反作弊条款。

- 风险 3：为了省事，把 smoke cluster 也一起改了，导致 v56/v57 的 e2e harness 回归。
  - 缓解：明确 smoke 为非目标，并加文档/测试边界。

- 风险 4：运行时镜像缺失时，系统退回旧路径或表现成“莫名其妙很慢”。
  - 缓解：缺镜像快速失败，并打印明确的本地构建命令。
