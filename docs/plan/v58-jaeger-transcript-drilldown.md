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
- REQ-0058-009
- REQ-0058-010

## Scope

做：

- 在 tracing spans 中补 `oa.session_id` / `oa.child_session_id` / `oa.target_node` 等稳定引用
- 给 cluster chat host 增加只读 transcript API
- 给 remote worker 增加只读 transcript API，供 host 代理读取
- 给 Jaeger Web UI 增加 transcript drilldown 前端扩展
- 修复 Jaeger UI 当前低对比度 / 灰字难读问题
- 把 Jaeger UI 源码 vendoring 到仓库内并纳入 git 跟踪
- 保持固定 Jaeger URL，不增加新的用户入口命令

不做：

- 不把正文直接写入 Jaeger
- 不做 transcript 编辑与回写
- 不在本轮解决多租户、鉴权、审计
- 不追求大规模改造 Jaeger 全部页面；只改 trace drilldown 与当前明显的可读性问题

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

- 既然要同时改交互与样式，第一版直接采用“仓库内 vendored Jaeger UI 源码 + 最小 patch”的方式。
- 建议目录：
  - `third_party/jaeger-ui/`
  - `deploy/k8s/v58/jaeger-ui-*.yaml`
- patch 范围第一版至少包括：
  - 监听 span 选中并抽取 `oa.*` 引用字段
  - 请求 transcript API
  - 在当前 trace 详情页旁边插入 transcript panel
  - 提升 trace 详情页关键文字对比度
- 必须记录 upstream 版本与本地 patch 边界，避免后续完全失控。

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
   - trace 详情页中的标题、service / operation 文本与关键字段不再是“难以辨认的浅灰字”
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
- Create: `third_party/jaeger-ui/`
- Create: `third_party/jaeger-ui/UPSTREAM.md`
- Create: `tests/test_v58_jaeger_ui_assets.py`
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

- 把 Jaeger UI 源码纳入仓库
- 给 Jaeger 加 transcript drilldown 与对比度修复 patch
- 点击 span 后在同页渲染 transcript panel

DoD：

- `python -m unittest -q tests.test_actor_tracing tests.test_session_transcript_view tests.test_cluster_chat_transcript_api tests.test_remote_worker_transcript_api tests.test_v58_jaeger_ui_assets`
- 手工验证：
  - `oa chat --k3d-real`
  - `http://127.0.0.1:16686`
  - 点击 real trace span，能看到 transcript panel
  - 关键文字对比度明显改善，截图中那类浅灰标题不再难读

## Notes

- v58 的核心哲学是“trace 里存 ref，正文留在 session store”。
- Jaeger 仍然只是 trace UI；正文来源仍然是我们自己的 host / worker session store。
- Jaeger UI 源码会被 vendoring 进仓库，但 patch 必须保持最小、可审计、可回放。
- 只要这个边界不破，后面无论换 Jaeger、SigNoz 还是别的 UI，都还能复用 transcript API 这一层。
