# PRD-0058 — Jaeger Transcript Drilldown v58

## Vision

v58 的目标不是把整段聊天正文塞进 tracing backend，而是在保持 trace 轻量、稳定、可检索的前提下，让 Jaeger Web UI 可以在点击某个 span 时，按需把对应的会话正文取回来并渲染：

- trace 中只保留稳定引用信息，例如 `session_id`、`child_session_id`、`execution_id`、`target_node`；
- 完整聊天正文继续留在各自 agent 的 session store / `events.jsonl` 中，而不是复制进 span attributes；
- Jaeger 前端通过一段轻量级前端扩展 JS，在用户点击某个 span 时请求 transcript API；
- Jaeger UI 必须顺手修复当前低对比度、灰字难读的问题，至少保证 trace 详情页里的核心文字可读；
- 为了稳定改前端，v58 必须把 Jaeger UI 源码纳入本仓库并由 git 跟踪，而不是依赖运行时临时注入不可追溯的补丁；
- transcript API 由我们自己的集群内服务提供，Jaeger 只是 UI 入口，不是正文存储；
- v58 第一版优先服务于当前 k3s 本地实验环境，目标是“点开能看”，不是做完整的多租户观测平台。

## Non-Goals

- v58 不把完整 transcript 直接写入 Jaeger span attributes、span events 或 baggage。
- v58 不在本轮引入数据库、对象存储或新的持久化系统来专门存 transcript。
- v58 不做复杂权限系统、多租户鉴权、跨团队共享访问。
- v58 不把所有 CLI / bridge / cluster 内部链路都做成全文可视化；第一版只覆盖当前 real cluster 的 host ↔ subagent 会话正文回捞。
- v58 不改变现有 session 持久化主路径；`events.jsonl` 仍然是真实来源。
- v58 不追求长期重度魔改 Jaeger 整个产品；只维护本项目实际需要的 UI 源码快照与最小 patch 集。

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

### REQ-0058-009 — Jaeger UI 必须修复当前低对比度与灰字难读问题

- v58 必须修复当前 Jaeger trace 详情页中“关键信息为浅灰色、难以辨认”的可读性问题。
- 第一版至少必须覆盖：
  - trace 标题区
  - service / operation 列表
  - span 详情中的关键字段标签与正文
- 修复方式可以是 CSS、主题变量或前端组件 patch，但结果必须满足：
  - 在默认亮色界面下，核心文本明显可读
  - 不要求新增完整主题切换功能
  - 不得把 Jaeger 原生布局破坏到不可用

### REQ-0058-010 — Jaeger UI 源码必须作为仓库内第三方源码被 git 跟踪

- 既然 v58 要改 Jaeger UI 行为与样式，Jaeger UI 源码必须纳入本仓库并由 git 跟踪。
- 第一版至少应做到：
  - 在仓库内保留一个明确目录，例如 `third_party/jaeger-ui/`
  - 记录 upstream 版本、commit 或 release tag
  - 记录我们自己的 patch 边界与构建入口
- v58 不允许只靠运行时下载远端源码、临时 patch、或只注入一段无法审计的 JS/CSS。
- deploy 产物必须可从仓库内源码重复构建出来。
