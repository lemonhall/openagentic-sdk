# PRD-0058 — Jaeger Transcript Drilldown v58

## Vision

v58 的目标不是把整段聊天正文塞进 tracing backend，而是在保持 trace 轻量、稳定、可检索的前提下，让 Jaeger Web UI 可以在点击某个 span 时，按需把对应的会话正文取回来并渲染：

- trace 中只保留稳定引用信息，例如 `session_id`、`child_session_id`、`execution_id`、`target_node`；
- 完整聊天正文继续留在各自 agent 的 session store / `events.jsonl` 中，而不是复制进 span attributes；
- Jaeger 前端通过一段轻量级前端扩展 JS，在用户点击某个 span 时请求 transcript API；
- transcript API 由我们自己的集群内服务提供，Jaeger 只是 UI 入口，不是正文存储；
- v58 第一版优先服务于当前 k3s 本地实验环境，目标是“点开能看”，不是做完整的多租户观测平台。

## Non-Goals

- v58 不把完整 transcript 直接写入 Jaeger span attributes、span events 或 baggage。
- v58 不 fork 一套完整 Jaeger 前端工程长期维护。
- v58 不在本轮引入数据库、对象存储或新的持久化系统来专门存 transcript。
- v58 不做复杂权限系统、多租户鉴权、跨团队共享访问。
- v58 不把所有 CLI / bridge / cluster 内部链路都做成全文可视化；第一版只覆盖当前 real cluster 的 host ↔ subagent 会话正文回捞。
- v58 不改变现有 session 持久化主路径；`events.jsonl` 仍然是真实来源。

## Requirements

### REQ-0058-001 — trace 中必须写入稳定 transcript 引用，而不是正文

- host 侧与 subagent 侧的关键 tracing spans 必须写入稳定引用字段，至少包括：
  - `oa.session_id`
  - `oa.execution.id`
  - `oa.agent.name`
- 当 span 对应 child execution 时，还必须尽量写入：
  - `oa.parent_session_id`
  - `oa.child_session_id`
  - `oa.target_node`
- v58 不允许把完整 user/assistant 正文直接写入 trace backend。

### REQ-0058-002 — cluster chat host 必须提供只读 transcript 查询能力

- cluster chat host 必须提供只读 transcript API，用于按 `session_id` 返回该会话的可渲染正文。
- 第一版 API 至少支持：
  - 查询 host/root session transcript
  - 返回结构化消息列表，而不是只吐原始 JSONL 文本
- transcript 返回格式至少包含：
  - `session_id`
  - `agent_name`
  - `messages[]`
  - `source`

### REQ-0058-003 — remote worker transcript 必须能通过 host 代理方式读取

- 当 Jaeger 里点到的是 remote subagent span，前端不得直接访问 worker Pod。
- host 必须能够基于 `child_session_id + target_node` 代理读取对应 worker transcript，或给出明确的“不可用”结构化结果。
- v58 第一版允许 host 只做只读代理，不允许修改 remote session 内容。

### REQ-0058-004 — Jaeger UI 必须支持点击 span 后按需显示 transcript

- 继续使用固定地址 `http://127.0.0.1:16686`。
- Jaeger UI 必须加载一段我们自己的轻量 JS 扩展，而不是要求用户另外开一个独立 viewer 页面。
- 当用户点击带有 `oa.session_id` / `oa.child_session_id` 的 span 时，UI 必须能够：
  - 识别可用 transcript 引用
  - 发起 transcript 请求
  - 在当前页面中显示正文面板或等价 drilldown 区域
- 如果 span 没有可用引用，UI 必须安静降级，不得破坏 Jaeger 原生页面。

### REQ-0058-005 — transcript drilldown 必须默认按需加载

- 默认页面加载时不得批量抓取 transcript。
- 只有当用户显式点击某个 span，且该 span 有 transcript 引用字段时，前端才允许发起读取。
- UI 必须避免重复请求同一个 transcript；允许简单内存缓存。

### REQ-0058-006 — 第一版显示重点是“会话正文可读”，不是编辑能力

- drilldown 面板第一版只读。
- 至少应显示：
  - user 消息
  - assistant 消息
  - agent 名称 / session id / execution id
- 第一版不要求支持会话编辑、重放、回滚、分享、下载等功能。

### REQ-0058-007 — API 与 UI 必须对异常做结构化降级

- 当 transcript 不存在、session id 无效、worker 不可达、host 无法代理或正文解析失败时，前端必须显示结构化错误状态。
- 不允许 UI 静默失败。
- 后端错误返回至少要区分：
  - `not_found`
  - `invalid_session_id`
  - `worker_unreachable`
  - `transcript_unavailable`

### REQ-0058-008 — v58 不得破坏当前 v57 tracing 与本地单机行为

- 当前已有的：
  - local tracing
  - remote tracing
  - `oa chat --k3d-real`
  - 固定 Jaeger 地址
  必须继续可用。
- 单机模式如果没有 Jaeger transcript 扩展环境，也不得因此报错或影响对话。

