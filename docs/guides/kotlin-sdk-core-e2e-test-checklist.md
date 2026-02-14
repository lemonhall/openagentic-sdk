# Kotlin SDK（核心模块 / 不含 CLI）E2E 测试 Checklist

面向：正在把 `openagentic-sdk` 的核心能力移植到 Kotlin/Java 生态的同学。  
目标：把“SDK 回归”与“模型随机性/网络波动”拆开，用一套**离线、确定性、可追溯**的 E2E 把核心模块的硬不变量钉死。

> 约定：本文不覆盖 CLI（TTY/PTY/ConPTY、输入编辑、多行粘贴等），只覆盖 SDK 核心模块：runtime/tool loop、tools、permissions、hooks、sessions/resume、provider 适配层。

---

## 0. 成功标准（强烈建议）

- **离线硬不变量套件**（offline hard invariants）：
  - 必须**100% 通过**，失败基本等价于“SDK 回归/协议破坏”。
  - 必须可在 CI **每次 PR** 自动跑。
  - 不依赖真实网络、不依赖真实 LLM、不依赖人类交互、不依赖系统 TTY。
- **在线/随机性套件**（online / stochastic flows）：
  - 可以 nightly、手动触发或按阈值（pass-rate）门禁。
  - 失败更多是“环境/模型/提供方变化”，不应该掩盖 SDK 回归。

---

## 1. 测试分层建议（套件结构）

### A) Offline Hard Invariants（必做）

核心思路：提供一个 `ScriptedProvider`（或等价“录制/回放 provider”），直接按脚本返回：
- assistant message（可选）
- tool calls（必选）
- tool call outputs（可选）
- 最终 assistant message（可选）

用例断言重点放在：
- 事件序列（trace/events）是否完整、因果关系是否可恢复
- 权限门/allowed_tools 是否严格生效
- sessions 落盘与 resume 是否严格满足约束
- hooks 是否在正确时间点被调用、改写是否生效
- 工具协议的输入/输出边界是否稳健

### B) Online Contract（可选但很有价值）

目的不是测“模型聪明不聪明”，而是测：
- provider HTTP/SDK 协议适配是否稳（鉴权、错误分类、响应解析、重试/超时）
- 网络抖动下不会写坏 session / 事件

### C) Stochastic Model-Driven Flows（可选）

只测用户体验流：模型规划/自然语言质量/工具选择策略。建议采用：
- 多次运行 + pass-rate 阈值 + 失败归因报告落盘

---

## 2. 必备测试基础设施（Kotlin 侧建议先做）

### 2.1 ScriptedProvider（离线确定性）

Checklist：
- [ ] 支持按脚本输出 `tool_calls`（含 name + arguments）以及最终文本。
- [ ] 支持“多轮对话”脚本：第 N 轮输出取决于输入历史（至少能按轮次出）。
- [ ] 支持模拟常见 provider 错误：timeout、rate limit、非 2xx、响应字段缺失/变形。
- [ ] 支持“流式与非流式”两种路径（流式只影响 UI，不应影响事件落盘）。

### 2.2 Golden Trace（关键事件对齐 / 追溯）

建议产物：
- `events.jsonl`（或 Kotlin 端等价物）：每行一个 JSON 事件。
- “规范化比较器”：允许忽略 `timestamp`、`duration_ms` 等噪声字段，但严格比较：
  - 事件类型集合、必需字段
  - tool.use 与 tool.result 的关联关系
  - 权限决策/拒绝原因
  - compaction 事件（若存在）

Checklist：
- [ ] 允许“新增字段”但不允许“删除/改名核心字段”（向后兼容策略清晰且可测）。
- [ ] 对未知事件类型/未知字段具备鲁棒解析（不会崩溃）。

### 2.3 最小追溯门禁（防止套件失控）

推荐机制：
1) `docs/plan/...` 或等价 PRD/plan 中维护一个 Traceability Matrix：suite → module list / invariant list  
2) 用脚本检查“suite 清单 ↔ 文档矩阵”一致性（缺失/重复/引用不存在即 fail）

Checklist：
- [ ] 新增/删除 suite 或模块时，CI 自动发现追溯矩阵不一致并失败。
- [ ] 追溯矩阵中引用的 suite/module 必须存在且可运行。

---

## 3. 核心模块 E2E Checklist（离线硬不变量优先）

下面每一条都建议写成离线 E2E（ScriptedProvider + 真 tool runner + 真 permission gate + 真 session store）。  
格式建议：每条用例写清楚 **Given / When / Then**，并且断言“事件序列 + 最终状态”，少断言最终自然语言。

### 3.1 事件协议（trace/events）硬不变量

- [ ] **JSONL 行协议**：每行一个完整 JSON；遇到换行/特殊字符不会破坏行边界。
- [ ] **事件类型稳定**：`user_message` / `assistant_message` / `tool_use` / `tool_result` / `hook` / `compaction`（按你们实现）命名与字段集合稳定。
- [ ] **tool.use/result 可关联**：必须有 `call_id`（或等价字段）把一次调用串起来；并发/乱序下也可还原因果。
- [ ] **禁止落盘 streaming delta**：任何 `*_delta` 类事件（或等价“分片输出”）不能写入持久化 trace。
- [ ] **未知字段容忍**：新增字段不会导致旧解析器崩溃；未知字段被忽略或透传（策略明确）。
- [ ] **错误事件结构化**：异常/错误有统一结构（type/message/optional stack/optional code）。
- [ ] **尺寸/上限**：单事件大小有上限策略（截断/摘要/拒绝），并且可测（避免 1 条事件写爆磁盘）。

### 3.2 Runtime 核心循环（query loop / tool loop）

- [ ] **0 工具调用**：模型直接返回最终文本，loop 正常结束并落盘完整事件。
- [ ] **1 工具调用**：一次 tool.use → tool.result → 最终文本；事件顺序与关联正确。
- [ ] **多工具串行**：A → B → C 调用顺序稳定；任何一步失败行为可预测（继续/终止策略可测）。
- [ ] **工具返回非 JSON**：tool.result 的内容仍可存储并可回放；不会导致解析崩溃。
- [ ] **取消/中断**：中途取消会话不会留下“半行 JSON”；恢复策略明确（例如标记 aborted）。
- [ ] **超时**：provider 超时、tool 超时分别处理；错误分类准确、可重试策略正确。
- [ ] **重试幂等**：若有重试，确保不会对有副作用的 tool 重复执行（或有幂等 key）。
- [ ] **并发语义（若支持）**：并发 tool calls 的结果合并稳定；事件可解释且可恢复。

### 3.3 Tools 协议与边界（tool plumbing）

- [ ] **参数校验**：
  - [ ] 缺字段、类型错、超长字符串、非法 Unicode、深层嵌套 JSON，都不会 crash。
  - [ ] oneOf/enum/optional/default 语义与 schema 一致。
- [ ] **工具不存在**：请求未知 tool 时，按策略拒绝并落盘“可解释”的错误事件。
- [ ] **工具返回大 payload**：能被安全截断/摘要；不会把 session 写爆。
- [ ] **工具异常**：抛异常时 tool.result 仍然结构化落盘；loop 按策略继续或终止。
- [ ] **工具注册/覆盖**：同名工具覆盖/禁止覆盖策略明确；可测。
- [ ] **allowed_tools**：
  - [ ] allow-list 生效（未允许的一律拒绝，默认安全）。
  - [ ] allow-list 在多轮/compaction 后仍生效（不会丢）。

### 3.4 Permission Gate（人类在环 / 权限门）

- [ ] **allow 模式**：工具正常执行，事件记录完整。
- [ ] **deny 模式**：工具不执行；事件记录包含拒绝原因/策略来源；loop 行为可预测。
- [ ] **prompt 模式**：
  - [ ] 有交互 callback 时能得到答案并继续。
  - [ ] 无交互环境下不会死等；有清晰失败方式（可测）。
- [ ] **bypass/always-allow（若存在）**：仅在明确配置下生效；默认不越权。
- [ ] **安全默认**：schema 解析失败、未知工具、未知策略时不应默认放行。

### 3.5 Hooks（可插拔改写/拦截）

- [ ] **触发点覆盖**：Before/AfterModelCall、Pre/PostToolUse、UserPromptSubmit（按实现）。
- [ ] **改写生效**：
  - [ ] hook 修改系统提示词/消息列表后，provider 输入确实变化（可通过 trace 断言）。
  - [ ] hook 修改 tool 参数后，tool.use 记录的是改写后的参数。
- [ ] **hook 拒绝/短路**：hook 决定中止时，事件记录完整且会话状态一致。
- [ ] **hook 异常隔离**：hook 报错不会把整个会话“无记录地”打死（要么落错误事件，要么策略化失败）。

### 3.6 Sessions / Resume（持久化与恢复）

- [ ] **落盘目录**：默认目录 + 自定义目录都可用；目录不存在时创建或报错清晰。
- [ ] **写入原子性**：进程崩溃/断电后：
  - [ ] 已写入行仍可读；
  - [ ] 截断行/坏行能被跳过或触发明确错误（策略可测）。
- [ ] **resume 一致性**：
  - [ ] 恢复后继续跑得到与不中断一致的关键事件（允许 timestamp 等噪声不同）。
  - [ ] 恢复时不会重复执行已执行过的 tool（除非明确设计要重放）。
- [ ] **多会话隔离**：不同 session id 不串；并发写不会互相覆盖（或明确不支持并发并有保护）。
- [ ] **事件膨胀防护**：长对话下 trace 规模可控（compaction 或上限策略可测）。

### 3.7 Compaction / Summarization（如有）

- [ ] **可控触发**：token/轮数/大小阈值可配置；离线用例可强制触发。
- [ ] **硬约束不丢**：allowed_tools、permission 策略、系统提示词中的安全约束不会因 compaction 消失。
- [ ] **可解释事件**：compaction 前后都有明确事件记录（原因、输入范围、输出摘要）。
- [ ] **resume 后不漂移**：恢复后不会二次 compaction 导致不可预测的状态漂移。

### 3.8 Provider 抽象与适配

- [ ] **ScriptedProvider 是一等公民**：离线 E2E 不依赖真实网络/真实 LLM。
- [ ] **错误分类**：鉴权失败、限流、超时、连接失败、响应字段缺失/变形都有覆盖。
- [ ] **响应解析鲁棒**：提供方新增字段/顺序变化不会导致崩溃；缺字段有清晰错误。
- [ ] **重试与退避**：仅对可重试错误重试；次数/间隔可配置且可测。

### 3.9 配置与跨平台一致性（Kotlin/Java 生态常见坑）

- [ ] **环境变量优先级**：参数 vs env vs 默认，优先级固定且可测。
- [ ] **路径规范化**：`..`、绝对/相对路径、Windows 盘符、分隔符差异都能正确处理。
- [ ] **目录穿越防护**：任何写文件类工具不得写出允许的根目录（canonical path 校验）。
- [ ] **时区/locale**：时间戳采用稳定格式（建议 epoch 或 ISO-8601 + 固定时区）；locale 不影响解析。
- [ ] **大文本**：超长 prompt、超长 tool 输出、超长历史不会 OOM（至少有上限与可测退化策略）。

### 3.10 安全（默认不越权）

- [ ] **默认拒绝高风险工具**：写文件/执行命令/网络请求等，除非明确 allow。
- [ ] **敏感信息不落盘**：API keys、tokens、私钥内容、cookie 等不得写入 events（或可配置脱敏）。
- [ ] **提示词注入对抗**：用户试图绕过 allowed_tools/permissions 时仍不越权（离线硬不变量必须覆盖）。

---

## 4. “从 Checklist 到 套件”的落地打法（建议执行顺序）

1) 先实现 `ScriptedProvider` + 真 session store + 真 permission gate 的最小闭环（3～5 个用例）。
2) 把 **3.1～3.6** 中最关键的硬不变量补齐到 25～40 个离线用例（每个用例都断言 trace）。
3) 再加 “最小追溯门禁脚本”：suite 清单必须与 PRD/plan 的矩阵一致。
4) 最后再考虑在线/随机性套件（nightly/手动 + pass-rate）。

---

## 5. 评审者用 Checklist（你给 Kotlin 同学 Code Review 时可用）

- [ ] 离线套件是否真的**不依赖**真实网络/真实 LLM？
- [ ] 失败时能否快速定位：是“SDK 回归”还是“外部波动/模型随机性”？
- [ ] 用例断言是否主要基于 **trace/tool.result/落盘**，而不是基于最终自然语言？
- [ ] sessions/resume 是否覆盖了截断/坏行/中断恢复？
- [ ] permission/allowed_tools 是否默认安全、拒绝可解释？
- [ ] hooks/tool plumbing 的边界条件是否覆盖了“缺字段/类型错/超大 payload/异常”？
- [ ] 是否有追溯矩阵门禁，防止套件膨胀后失控？

