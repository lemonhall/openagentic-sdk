# v56 M4 — 真实 Provider 驱动的 Cluster Host 与 Remote Subagents

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 cluster-hosted 主会话与 remote subagent 不再依赖 smoke provider，而是通过独立的 remote cluster 配置层连接真实模型供应商。

**Architecture:** 引入独立的 `openagentic.remote.json` + `.openagentic.remote.env` 配置模型，由 cluster host 在启动时解析 host/agents/provider profiles，并在远程 `Task` 派发时把目标 agent 的已解析 provider spec 一并下发给 worker。worker 不再自行猜测 provider；它只消费 host 下发的 provider spec 构造真实 provider，并通过轻量自检把 `provider_ready` 暴露到健康状态中。smoke cluster 保留用于离线回归，real-model cluster 走独立部署与手工验收链路。

**Tech Stack:** Python 3.11+、现有 `OpenAIResponsesProvider` / `OpenAICompatibleProvider`、HTTP remote worker server、k3d/k3s manifests、PowerShell + WSL2 运维脚本。

---

## PRD Trace

- REQ-0056-015
- REQ-0056-016
- REQ-0056-017
- REQ-0056-018
- REQ-0056-019

## Scope

做：

- 新增独立的 remote cluster 配置/解析层
- 支持 host/agent 绑定不同 provider profile 与 model
- 支持把 agent 的已解析 provider spec 经由远程 `Task` 请求下发到 worker
- 为 host / worker 增加 provider 自检与健康状态输出
- 保留 smoke cluster，并新增 real-model cluster 的部署/手工测试方法

不做：

- 不做多供应商 fallback
- 不做每个 agent 独立 secret 文件
- 不做 Secret/operator 化
- 不做写权限 / git 并发模型
- 不做启动阶段的真实模型 API 探活

## Acceptance (DoD)

必须全部满足：

1. 单元/集成：
   - `python -m unittest -q tests.test_remote_cluster_config tests.test_remote_http_transport tests.test_remote_chat_bridge`
2. 回归：
   - `python -m unittest -q tests.test_openai_tool_schemas tests.test_agent_config_mapping tests.test_remote_task_dispatch tests.test_remote_worker_protocol tests.test_remote_readonly_guard tests.test_remote_http_transport tests.test_remote_chat_bridge tests.test_remote_git_sync_policy tests.test_remote_session_meta`
3. 定向 lint：
   - `ruff check openagentic_sdk/options.py openagentic_sdk/remote_cluster_config.py openagentic_sdk/subagents/remote_http.py openagentic_sdk/subagents/remote_worker.py openagentic_sdk/server/cluster_chat_host.py openagentic_sdk/subagents/remote_http_worker_server.py openagentic_sdk/runtime_core/tool_task.py tests/test_remote_cluster_config.py tests/test_remote_http_transport.py tests/test_remote_chat_bridge.py scripts/apply_v56_real_cluster.py --config ruff.toml`
4. 部署渲染验证：
   - `python scripts/apply_v56_real_cluster.py --remote-config openagentic.remote.example.json --env-file .openagentic.remote.env.example --output-dir .openagentic-rendered-smoke`
5. 手工/半自动 real-model 验收：
   - host 闲聊输入不再只返回 smoke 兜底文本
   - `research` / `writer` 返回内容来自真实模型调用，而非 `_smoke_provider.py`
   - `/health` 显示 `provider_ready=true`
6. 反作弊条款：
   - 不允许只是把 smoke provider 的固定分支换个文案
   - 不允许 worker 继续依赖本地 CLI provider 配置猜测逻辑
   - 不允许 real-model cluster 依赖挂载 `.openagentic.remote.env` 明文文件到 pod

## File Structure

- Create: `openagentic_sdk/remote_cluster_config.py`
- Create: `tests/test_remote_cluster_config.py`
- Create: `.openagentic.remote.env.example`
- Modify: `openagentic_sdk/options.py`
- Modify: `openagentic_sdk/subagents/remote_http.py`
- Modify: `openagentic_sdk/runtime_core/tool_task.py`
- Modify: `openagentic_sdk/subagents/remote_worker.py`
- Modify: `openagentic_sdk/server/cluster_chat_host.py`
- Modify: `openagentic_sdk/subagents/remote_http_worker_server.py`
- Create: `deploy/k8s/v56/chat-host-real.template.yaml`
- Create: `deploy/k3d/v56-workers-real.template.yaml`
- Create: `scripts/apply_v56_real_cluster.py`
- Create: `openagentic.remote.example.json`
- Modify: `.gitignore`
- Modify: `docs/plan/v56-index.md`
- Modify: `docs/guides/k3s-remote-chat-manual-testing.md`

## Task 1: Remote Cluster 配置模型

**Files:**
- Create: `openagentic_sdk/remote_cluster_config.py`
- Create: `tests/test_remote_cluster_config.py`
- Create: `.openagentic.remote.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: 写失败测试，定义 remote config 基本 contract**

测试至少覆盖：
- `openagentic.remote.json` 可解析 host / providers / agents
- `.openagentic.remote.env` 对应的环境变量缺失时自检失败
- `rightcode` 这类 profile 能解析成真实 provider spec
- agent 允许覆盖 `model`，但默认继承 profile 默认 model

- [ ] **Step 2: 跑到红**

Run:
```powershell
python -m unittest -q tests.test_remote_cluster_config
```

Expected:
- FAIL，提示缺少 `remote_cluster_config` 模块或相关解析能力

- [ ] **Step 3: 写最小实现**

实现内容：
- 新增 remote cluster dataclass / loader
- 支持从 `openagentic.remote.json` 读取 provider profiles、host、agents
- 支持从当前环境解析 `base_url` / `api_key`
- 支持构造可序列化的 provider spec
- 将 `.openagentic.remote.env` 加入 `.gitignore`

- [ ] **Step 4: 跑到绿**

Run:
```powershell
python -m unittest -q tests.test_remote_cluster_config
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```powershell
git add .gitignore docs/plan/v56-real-provider-cluster-host-and-remote-subagents.md openagentic_sdk/remote_cluster_config.py tests/test_remote_cluster_config.py
git commit -m "v56: add remote cluster config loader"
```

## Task 2: Provider Spec 下发到 Worker

**Files:**
- Modify: `openagentic_sdk/options.py`
- Modify: `openagentic_sdk/subagents/remote_http.py`
- Modify: `openagentic_sdk/runtime_core/tool_task.py`
- Modify: `openagentic_sdk/subagents/remote_worker.py`
- Test: `tests/test_remote_http_transport.py`

- [ ] **Step 1: 写失败测试，证明 worker 仍只会用 base provider**

测试至少覆盖：
- `Task` 构造的远程请求带有 provider spec
- HTTP transport 可以序列化/反序列化 provider spec
- worker 收到 provider spec 后用真实 provider 执行，而不是回退到 base_options.provider

- [ ] **Step 2: 跑到红**

Run:
```powershell
python -m unittest -q tests.test_remote_http_transport
```

Expected:
- FAIL，提示远程定义里没有 provider spec 或 worker 未使用下发 spec

- [ ] **Step 3: 写最小实现**

实现内容：
- 扩展 agent / remote request 的 provider spec 承载能力
- `Task` 远程派发时带出目标 agent 的已解析 provider spec
- worker 反序列化后构造真实 provider，并让 child runtime 使用它

- [ ] **Step 4: 跑到绿**

Run:
```powershell
python -m unittest -q tests.test_remote_http_transport
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```powershell
git add openagentic_sdk/options.py openagentic_sdk/subagents/remote_http.py openagentic_sdk/runtime_core/tool_task.py openagentic_sdk/subagents/remote_worker.py tests/test_remote_http_transport.py
git commit -m "v56: send resolved provider spec to remote workers"
```

## Task 3: Host / Worker Real-Provider 模式与自检

**Files:**
- Modify: `openagentic_sdk/server/cluster_chat_host.py`
- Modify: `openagentic_sdk/subagents/remote_http_worker_server.py`
- Test: `tests/test_remote_chat_bridge.py`
- Test: `tests/test_remote_cluster_config.py`

- [ ] **Step 1: 写失败测试，定义 real-provider 启动与 `/health` contract**

测试至少覆盖：
- host 可由 `openagentic.remote.json` 启动，不再强制依赖 `--provider-factory`
- worker 可由 remote config 启动，不再强制依赖 smoke provider
- `/health` 至少返回 `provider_ready`、`provider_profiles`、`config_source`
- 缺少必需 env 时，`provider_ready=false`

- [ ] **Step 2: 跑到红**

Run:
```powershell
python -m unittest -q tests.test_remote_cluster_config tests.test_remote_chat_bridge
```

Expected:
- FAIL，提示 server 启动参数或 `/health` 输出不符合新 contract

- [ ] **Step 3: 写最小实现**

实现内容：
- 为 host / worker 增加 `--remote-config` 启动路径
- 保持 `--provider-factory` 路径给 smoke 测试继续使用
- 接入 provider 自检与健康状态输出

- [ ] **Step 4: 跑到绿**

Run:
```powershell
python -m unittest -q tests.test_remote_cluster_config tests.test_remote_chat_bridge
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```powershell
git add openagentic_sdk/server/cluster_chat_host.py openagentic_sdk/subagents/remote_http_worker_server.py tests/test_remote_cluster_config.py tests/test_remote_chat_bridge.py
git commit -m "v56: add real-provider server bootstrap and health checks"
```

## Task 4: 部署与文档

**Files:**
- Create: `deploy/k8s/v56/chat-host-real.template.yaml`
- Create: `deploy/k3d/v56-workers-real.template.yaml`
- Create: `scripts/apply_v56_real_cluster.py`
- Create: `openagentic.remote.example.json`
- Create: `.openagentic.remote.env.example`
- Modify: `docs/guides/k3s-remote-chat-manual-testing.md`
- Modify: `docs/plan/v56-index.md`

- [ ] **Step 1: 写失败测试或验证脚本说明，固定部署 contract**

覆盖点：
- smoke cluster 部署仍可用
- real-model cluster 需要 remote config + env 注入
- 手工测试文档区分 smoke / real-model 两种路径

- [ ] **Step 2: 修改部署与文档**

实现内容：
- 部署层支持读取 `.openagentic.remote.env` 并注入 env
- host / worker real manifests 改为 `--remote-config` 启动参数
- 新增 `.openagentic.remote.env.example`
- 文档明确 smoke / real-model 两条路径、cold start、重建、health、自检与真实 chat 验收

- [ ] **Step 3: 验证**

Run:
```powershell
python -m unittest -q tests.test_remote_cluster_config tests.test_remote_http_transport tests.test_remote_chat_bridge
python scripts/apply_v56_real_cluster.py --remote-config openagentic.remote.example.json --env-file .openagentic.remote.env.example --output-dir .openagentic-rendered-smoke
ruff check openagentic_sdk/options.py openagentic_sdk/remote_cluster_config.py openagentic_sdk/subagents/remote_http.py openagentic_sdk/subagents/remote_worker.py openagentic_sdk/server/cluster_chat_host.py openagentic_sdk/subagents/remote_http_worker_server.py openagentic_sdk/runtime_core/tool_task.py tests/test_remote_cluster_config.py tests/test_remote_http_transport.py tests/test_remote_chat_bridge.py scripts/apply_v56_real_cluster.py --config ruff.toml
```

Expected:
- PASS / All checks passed

- [ ] **Step 4: Commit**

```powershell
git add deploy/k3d/v56-workers-real.template.yaml deploy/k8s/v56/chat-host-real.template.yaml .openagentic.remote.env.example openagentic.remote.example.json scripts/apply_v56_real_cluster.py docs/guides/k3s-remote-chat-manual-testing.md docs/plan/v56-index.md
git commit -m "v56: wire real-provider cluster deployment"
```

## Evidence

- Date: 2026-03-28
- Env: Windows 11 + PowerShell 7.x
- Status: automated verification green; pending real credentials / cluster manual acceptance
