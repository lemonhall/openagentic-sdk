# v58 Plan — Jaeger Transcript Drilldown

## Goal

在不把正文塞进 trace backend 的前提下，让 `http://127.0.0.1:16686` 里的 Jaeger UI 能在点击 span 后，按需回捞并显示对应的 host / subagent transcript。

## PRD Trace

- REQ-0058-001
- REQ-0058-002
- REQ-0058-003
- REQ-0058-004
- REQ-0058-005
- REQ-0058-006
- REQ-0058-007
- REQ-0058-008

## Scope

做：

- 在 tracing spans 中补 `oa.session_id` / `oa.child_session_id` / `oa.target_node` 等稳定引用
- 给 cluster chat host 增加只读 transcript API
- 给 remote worker 增加只读 transcript API，供 host 代理读取
- 给 Jaeger Web UI 增加一个轻量 transcript drilldown 前端扩展
- 保持固定 Jaeger URL，不增加新的用户入口命令

不做：

- 不把正文直接写入 Jaeger
- 不维护 Jaeger 完整前端 fork
- 不做 transcript 编辑与回写
- 不在本轮解决多租户、鉴权、审计

## Recommended Architecture

### 1. Trace Ref Layer

- host / worker 在关键 spans 上写入稳定 ref：
  - `oa.session_id`
  - `oa.parent_session_id`
  - `oa.child_session_id`
  - `oa.execution.id`
  - `oa.target_node`
- 这些字段只做“定位正文”的索引，不承载正文本身。

### 2. Transcript Read API

- `cluster_chat_host` 增加 host transcript 查询：
  - 例：`GET /oa/transcript/session/{session_id}`
- remote worker 增加 child transcript 查询：
  - 例：`GET /oa/transcript/session/{session_id}`
- host 再提供代理入口：
  - 例：`GET /oa/transcript/child/{target_node}/{session_id}`
- 浏览器只打 host / Jaeger 同源代理入口，不直接碰 worker Pod。

### 3. Jaeger UI Extension

- 不建议硬 fork Jaeger 前端源码。
- 第一版建议通过一个轻量 JS 注入层完成：
  - 监听 Jaeger span 选中事件
  - 抽取 `oa.*` 引用字段
  - 请求 transcript API
  - 在当前 trace 详情页旁边插入一个 transcript panel
- 如果无法稳定拿到 Jaeger 内部事件，可退一步做 DOM-level hook，但仍然保持“薄注入层”而不是整站重写。

## Acceptance (DoD)

必须全部满足：

1. Runtime / API：
   - host trace span 可见 `oa.session_id`
   - child trace span 可见 `oa.child_session_id` 与 `oa.target_node`
   - host transcript API 可返回 root 会话正文
   - host 能代理 remote worker transcript
2. UI：
   - 打开 `http://127.0.0.1:16686`
   - 点开一条 real trace 的 host span，可看到 root transcript
   - 点开一条 real trace 的 worker span，可看到 child transcript 或明确结构化错误
3. 回归：
   - 不破坏现有 `oa chat --k3d-real`
   - 不破坏 v57 Jaeger trace 查询
   - 不破坏本地单机模式

## Files

- Modify: `openagentic_sdk/subagents/actor_tracing.py`
- Modify: `openagentic_sdk/server/cluster_chat_host.py`
- Modify: `openagentic_sdk/subagents/remote_http.py`
- Modify: `openagentic_sdk/subagents/remote_http_worker_server.py`
- Create: `openagentic_sdk/server/session_transcript_view.py`
- Create: `tests/test_session_transcript_view.py`
- Create: `tests/test_cluster_chat_transcript_api.py`
- Create: `tests/test_remote_worker_transcript_api.py`
- Create: `deploy/k8s/v58/jaeger-ui-overlay.yaml`
- Create: `deploy/k8s/v58/jaeger-ui-proxy.yaml`
- Create: `docs/plan/v58-index.md`

## Milestones

### M1 — Transcript Refs And Read APIs

- 给 trace 补稳定 ref 字段
- 给 host / worker 补 transcript 读取接口
- 先把“正文能按 id 读出来”跑通

DoD：

- `python -m unittest -q tests.test_actor_tracing tests.test_session_transcript_view tests.test_cluster_chat_transcript_api tests.test_remote_worker_transcript_api`

### M2 — Jaeger Drilldown UI

- 给 Jaeger 加薄前端扩展
- 点击 span 后在同页渲染 transcript panel

DoD：

- `python -m unittest -q tests.test_actor_tracing tests.test_session_transcript_view tests.test_cluster_chat_transcript_api tests.test_remote_worker_transcript_api`
- 手工验证：
  - `oa chat --k3d-real`
  - `http://127.0.0.1:16686`
  - 点击 real trace span，能看到 transcript panel

## Notes

- v58 的核心哲学是“trace 里存 ref，正文留在 session store”。
- Jaeger 仍然只是 trace UI；正文来源仍然是我们自己的 host / worker session store。
- 只要这个边界不破，后面无论换 Jaeger、SigNoz 还是别的 UI，都还能复用 transcript API 这一层。

