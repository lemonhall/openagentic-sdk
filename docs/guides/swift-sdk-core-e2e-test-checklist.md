# Swift SDK（核心模块 / 不含 CLI）E2E 测试 Checklist

面向：正在把 `openagentic-sdk` 的核心能力移植到 Swift（iOS/macOS）生态的同学。  
目标：把“SDK 回归”与“模型随机性/网络波动”拆开，用一套**离线、确定性、可追溯**的 E2E 把核心模块的硬不变量钉死。

> 约定：本文不覆盖 CLI（TTY/PTY、输入编辑、多行粘贴等），只覆盖 SDK 核心模块：runtime/tool loop、tools、permissions、hooks、sessions/resume、provider 适配层，以及（如有）skills/commands/project 兼容层。

---

## 0. 成功标准（强烈建议）

- **离线硬不变量套件**（offline hard invariants）：
  - 必须 **100% 通过**，失败基本等价于“SDK 回归/协议破坏”。
  - 必须可在 CI **每次 PR** 自动跑。
  - 不依赖真实网络、不依赖真实 LLM、不依赖人类交互、不依赖系统 TTY。
  - **零 flake（不抖动）**：同样输入在同机多跑结果一致；不依赖时间/随机数/调度顺序。
  - **失败可解释**：失败能直接定位到“哪个不变量被破坏”。
  - **断言以 trace 为主**：用 `events.jsonl`/关键事件做断言，而不是自然语言最终输出。
- **在线/随机性套件**（online / stochastic flows）：
  - 可以 nightly、手动触发或按阈值（pass-rate）门禁。
  - 失败更多是“环境/模型/提供方变化”，不应该掩盖 SDK 回归。

### 0.1 非目标（避免误测）

- 不测 CLI 交互（输入编辑、多行粘贴、TTY/PTY）。
- 不把“模型是否会规划工具/是否按提示词写得好”当成硬门禁（除非你们明确愿意承担随机性）。
- 不把“费用/速度优化”当成阻碍（可以做，但不要降低信噪比）。

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

## 2. 必备测试基础设施（Swift 侧建议先做）

### 2.1 ScriptedProvider（离线确定性）

Checklist：
- [ ] 支持按脚本输出 `tool_calls`（含 name + arguments）以及最终文本。
- [ ] 支持“多轮对话”脚本：第 N 轮输出取决于输入历史（至少能按轮次出）。
- [ ] 支持模拟常见 provider 错误：timeout、rate limit、非 2xx、响应字段缺失/变形。
- [ ] 支持“流式与非流式”两种路径（流式只影响 UI，不应影响事件落盘）。
- [ ] 支持“脚本断言”：能断言 runtime 发给 provider 的输入（messages/system/tool schemas）与预期一致。
- [ ] 支持“确定性调度”：对并发/异步路径，测试里能强制串行或固定顺序（避免 Task 调度导致 flake）。
- [ ] 支持“可插入时钟/随机源”：用 fake clock、固定 seed，避免时间/随机导致 flake。
- [ ] 支持“响应变形器”：同一语义用不同字段顺序/空白/可选字段，验证解析鲁棒性。

> Swift 提示：并发/时钟建议通过自定义 `Clock`/`Sleeper` 协议或注入 `now()/sleep()` 依赖，避免直接用 `Date()`/`Task.sleep` 写死在生产代码里。

### 2.2 Golden Trace（关键事件对齐 / 追溯）

建议产物：
- `events.jsonl`（或 Swift 端等价物）：每行一个 JSON 事件。
- “规范化比较器”：允许忽略 `timestamp`、`duration_ms` 等噪声字段，但严格比较：
  - 事件类型集合、必需字段
  - tool.use 与 tool.result 的关联关系
  - 权限决策/拒绝原因
  - compaction 事件（若存在）

Checklist：
- [ ] 允许“新增字段”但不允许“删除/改名核心字段”（向后兼容策略清晰且可测）。
- [ ] 对未知事件类型/未知字段具备鲁棒解析（不会崩溃）。
- [ ] 有“事件规范化器”（normalizer）：可选择性忽略噪声字段（timestamp、duration、provider_request_id 等）。
- [ ] 有“严格模式”（strict）：用于 hard invariants，禁止缺失必需字段/禁止关键语义漂移。
- [ ] 有“序列号/单调递增顺序”（推荐）：每个事件有 `seq` 或等价字段，方便定位缺失/重复。
- [ ] 有“最小证据链”断言：每个 tool.use 必有对应 tool.result（除非被 permission deny）。

> Swift 提示：JSON 对象 key 的顺序不应作为断言依据；Golden 对齐应基于“解析后结构”的 canonicalization（排序 key、规范化缺字段 vs `null` 的语义）。

### 2.3 最小追溯门禁（防止套件失控）

推荐机制：
1) `docs/plan/...` 或等价 PRD/plan 中维护一个 Traceability Matrix：suite → module list / invariant list  
2) 用脚本检查“suite 清单 ↔ 文档矩阵”一致性（缺失/重复/引用不存在即 fail）

Checklist：
- [ ] 新增/删除 suite 或模块时，CI 自动发现追溯矩阵不一致并失败。
- [ ] 追溯矩阵中引用的 suite/module 必须存在且可运行。
- [ ] suite 允许分层标签（offline/online/stochastic），CI 根据标签决定触发频率。
- [ ] 追溯矩阵里记录“每个 suite 覆盖的硬不变量集合”，避免“只写模块名不写断言点”。

### 2.4 最小测试夹具（强烈建议）

- [ ] `FakeClock` / `DeterministicClock`：可控时间，避免与真实系统时间耦合。
- [ ] `TempSessionDir`：所有测试写入临时目录（`FileManager.default.temporaryDirectory`），绝不污染 repo。
- [ ] `InMemorySessionStore`（可选）：用于极少数“只测事件逻辑不测 IO”的用例，但 hard invariants 仍建议走真实文件 IO。
- [ ] `EventAsserts`：统一断言工具（包含“事件序列”“关联关系”“字段存在性”“敏感信息脱敏”等）。
- [ ] `ToolTestDoubles`：一组标准工具（成功/失败/慢/大输出/非 JSON 输出/副作用工具），让边界测试可复用。
- [ ] `NetworkStubs`（若有在线 contract）：可替换 `URLSession`（protocol + fake）或使用本地 stub server。

---

## 3. 核心模块 E2E Checklist（离线硬不变量优先）

下面每一条都建议写成离线 E2E（ScriptedProvider + 真 tool runner + 真 permission gate + 真 session store）。  
格式建议：每条用例写清楚 **Given / When / Then**，并且断言“事件序列 + 最终状态”，少断言最终自然语言。

### 3.1 事件协议（trace/events）硬不变量

- [ ] **JSONL 行协议**：每行一个完整 JSON；遇到换行/特殊字符不会破坏行边界。
- [ ] **事件类型稳定**：`user_message` / `assistant_message` / `tool_use` / `tool_result` / `hook` / `compaction`（按实现）命名与字段集合稳定。
- [ ] **tool.use/result 可关联**：必须有 `call_id`（或等价字段）把一次调用串起来；并发/乱序下也可还原因果。
- [ ] **禁止落盘 streaming delta**：任何 `*_delta` 类事件（或等价“分片输出”）不能写入持久化 trace。
- [ ] **未知字段容忍**：新增字段不会导致旧解析器崩溃；未知字段被忽略或透传（策略明确）。
- [ ] **错误事件结构化**：异常/错误有统一结构（type/message/optional stack/optional code）。
- [ ] **尺寸/上限**：单事件大小有上限策略（截断/摘要/拒绝），并且可测（避免 1 条事件写爆磁盘）。
- [ ] **字段一致性**：同一类事件在不同代码路径产出的字段一致（避免“有时叫 X、有时叫 Y”）。
- [ ] **顺序语义**：严格顺序写入或可恢复语义二选一；对应策略必须可测。
- [ ] **幂等写入**：同一事件不会被重复写入（重试/恢复路径尤其需要测）。
- [ ] **可检索性**：每个 session 有稳定 `session_id`；每次 run 有 `run_id`（推荐）。
- [ ] **敏感信息脱敏**：trace 中不出现 API key/token/私钥内容/cookie（可测）。
- [ ] **编码/Unicode**：emoji、组合字符、中文、不同 NFC/NFD 规范化差异仍可 round-trip。
- [ ] **Date 编码策略明确**：epoch/ISO8601/毫秒单位一致；不依赖系统 locale/timezone。

### 3.2 Runtime 核心循环（query loop / tool loop）

- [ ] **0 工具调用**：模型直接返回最终文本，loop 正常结束并落盘完整事件。
- [ ] **1 工具调用**：一次 tool.use → tool.result → 最终文本；事件顺序与关联正确。
- [ ] **多工具串行**：A → B → C 调用顺序稳定；任何一步失败行为可预测（继续/终止策略可测）。
- [ ] **工具返回非 JSON**：tool.result 仍可存储并可回放；不会导致解析崩溃。
- [ ] **取消/中断**：中途取消会话不会留下半行 JSON；恢复策略明确（例如标记 aborted/cancelled）。
- [ ] **超时**：provider 超时、tool 超时分别处理；错误分类准确、可重试策略正确。
- [ ] **重试幂等**：若有重试，确保不会对有副作用的 tool 重复执行（或有幂等 key）。
- [ ] **并发语义（若支持）**：并发 tool calls 结果合并稳定；事件可解释且可恢复。
- [ ] **最大步数/熔断**：防止无限 tool call（max tool calls/max depth）并可测。
- [ ] **递归/再入保护**：tool 内触发二次 query 的策略明确且可测。
- [ ] **异常边界**：未捕获异常应产生可解释错误事件（或明确崩溃策略）并确保资源回收。
- [ ] **资源回收**：会话结束后不遗留后台 Task；多次运行无明显泄漏（粗粒度 smoke）。

> Swift 并发提示：必须测试 `Task` 取消路径，确保 `CancellationError` 不被吞掉、不会导致死等或半写入。

### 3.3 Tools 协议与边界（tool plumbing）

- [ ] **参数校验**：缺字段、类型错、超长字符串、非法 Unicode、深层嵌套 JSON 都不会 crash。
- [ ] **schema 语义一致**：oneOf/enum/optional/default 与工具实现一致。
- [ ] **工具不存在**：请求未知 tool 时，按策略拒绝并落盘可解释错误事件。
- [ ] **工具返回大 payload**：能被安全截断/摘要；不会把 session 写爆。
- [ ] **工具异常**：抛异常时 tool.result 仍结构化落盘；loop 按策略继续或终止。
- [ ] **工具注册/覆盖**：同名工具覆盖/禁止覆盖策略明确；可测。
- [ ] **allowed_tools**：allow-list 生效且默认安全；跨轮/compaction 后不丢。
- [ ] **参数容错**：arguments 可能是 JSON 字符串、类型被转成字符串、或包含额外字段；行为明确且可测。
- [ ] **工具输出通道**：tool.result 覆盖结构化 JSON、纯文本；若支持二进制则必须 base64/mime/size limit。
- [ ] **副作用工具防重放**：有幂等 key/nonce 或明确禁止 resume 后重放。
- [ ] **工具隔离**：工具失败不污染其他工具上下文；避免共享可变全局状态。

### 3.4 Permission Gate（人类在环 / 权限门）

- [ ] **allow 模式**：工具正常执行，事件记录完整。
- [ ] **deny 模式**：工具不执行；事件记录包含拒绝原因/策略来源；loop 行为可预测。
- [ ] **prompt 模式**：有交互回答器可继续；无交互时不死等（快速失败/返回错误）。
- [ ] **bypass/always-allow（若存在）**：仅在明确配置下生效；默认不越权。
- [ ] **安全默认**：schema 解析失败、未知工具、未知策略时不默认放行。
- [ ] **策略作用域**：全局/会话/单次调用级优先级明确且可测。
- [ ] **可审计性**：每次 allow/deny 都落事件（策略 id、匹配理由、用户回答（若有））。
- [ ] **拒绝后行为**：deny 后是继续对话、返回错误、还是要求模型改计划？策略明确可测。

### 3.5 Hooks（可插拔改写/拦截）

- [ ] **触发点覆盖**：Before/AfterModelCall、Pre/PostToolUse、UserPromptSubmit（按实现）。
- [ ] **改写生效**：hook 修改消息/提示词/工具参数后，provider 输入与 tool.use 记录符合预期。
- [ ] **hook 拒绝/短路**：hook 中止时，事件记录完整且会话状态一致。
- [ ] **hook 异常隔离**：hook 报错不应“无记录地”打死会话；有事件证据或策略化失败。
- [ ] **hook 顺序稳定**：多个 hook 执行顺序固定且可配置（或明确“注册顺序即执行顺序”）。
- [ ] **并发安全**：多会话并发时 hook 不互相污染（建议用 `actor` 或避免共享可变全局）。
- [ ] **hook 不能越权**：hook 增删工具、改写参数也必须经过 permissions/allowed_tools。

### 3.6 Sessions / Resume（持久化与恢复）

- [ ] **落盘目录**：默认目录 + 自定义目录都可用；目录不存在时创建或报错清晰。
- [ ] **写入原子性**：崩溃/断电后已写入行仍可读；截断/坏行恢复策略明确且可测。
- [ ] **resume 一致性**：恢复后继续跑得到与不中断一致的关键事件（允许 timestamp 等噪声不同）。
- [ ] **不重放副作用**：恢复时不会重复执行已执行过的副作用工具（除非明确设计要重放）。
- [ ] **多会话隔离**：不同 session id 不串；并发写不会互相覆盖（或明确拒绝并发并报错清晰）。
- [ ] **事件膨胀防护**：长对话下 trace 规模可控（compaction 或上限策略可测）。
- [ ] **平台差异**：macOS/Linux vs iOS（沙箱/权限/路径）差异不破坏语义；必要时测试用 `temporaryDirectory`。
- [ ] **路径与 Unicode**：中文路径、特殊字符、长路径仍可读写。
- [ ] **跨版本迁移**：旧版本 events 新版本能读；新版本 events 旧版本至少能跳过未知字段/类型。
- [ ] **只读恢复（推荐）**：resume 支持只读模式，避免覆盖原 trace。

> Swift 文件 IO 提示：建议测试 `.atomic` 写入策略（或等价做法）以及 `FileHandle` 写入下的崩溃边界，避免半行 JSONL。

### 3.7 Compaction / Summarization（如有）

- [ ] **可控触发**：token/轮数/大小阈值可配置；离线用例可强制触发。
- [ ] **硬约束不丢**：allowed_tools、permission 策略、安全提示词约束不因 compaction 消失。
- [ ] **可解释事件**：compaction 前后有明确事件记录（原因、输入范围、输出摘要）。
- [ ] **resume 后不漂移**：恢复后不发生不可预测状态漂移（例如重复 compaction）。
- [ ] **工具结果保留策略**：tool.result 摘要/保留/丢弃规则明确；hard invariants 建议保留最小证据链。
- [ ] **压缩失败处理**：compaction 失败不破坏会话；有回退策略与事件记录。

### 3.8 Provider 抽象与适配

- [ ] **ScriptedProvider 一等公民**：离线 E2E 不依赖真实网络/真实 LLM。
- [ ] **错误分类**：鉴权失败、限流、超时、连接失败、响应字段缺失/变形都有覆盖。
- [ ] **响应解析鲁棒**：提供方新增字段/顺序变化不崩溃；缺字段有清晰错误。
- [ ] **重试与退避**：仅对可重试错误重试；次数/间隔可配置且可测（用 fake clock 避免测试变慢）。
- [ ] **流式协议解析（如有）**：SSE/chunked JSON 在半包/粘包、空行、非法 JSON 下行为可预测且不写坏 session。
- [ ] **HTTP 细节**：重定向、代理、TLS 错误、证书问题、DNS 失败都能分类清楚（至少不要吞错）。
- [ ] **请求幂等**：重试时不会把同一请求写成两个 run；run_id/trace 关联清晰。
- [ ] **可观测性**：provider 提供 request_id/response_id 时写入 trace（脱敏后）。

> Swift 网络提示：建议把 `URLSession` 抽象成协议以便离线 stub；流式读取建议覆盖“中途断开/非 UTF-8/非 JSON”的错误分支。

### 3.9 配置与跨平台一致性（Swift 生态常见坑）

- [ ] **环境变量/配置优先级**：参数 vs env vs 默认，优先级固定且可测（注意 iOS 环境变量可用性有限）。
- [ ] **路径规范化**：`..`、绝对/相对路径、符号链接跳转，不能突破 sandbox 根目录（canonical path 校验）。
- [ ] **编码与换行**：LF/CRLF 不影响解析；对文本工具输出的换行策略一致。
- [ ] **序列化库语义**：`Codable` 对缺字段/默认值/`null` 的语义差异必须覆盖（`null` vs 缺字段尤其关键）。
- [ ] **数字语义**：JSON 数字到 `Int`/`Double` 的精度与溢出策略明确（必要时把大整数当字符串处理）。
- [ ] **时区/locale**：`Date` 编码/解析不受 locale 影响。
- [ ] **并发隔离模型**：`actor`/`Sendable` 边界明确；避免在并发场景下共享可变对象导致竞态。

### 3.10 安全（默认不越权）

- [ ] **默认拒绝高风险工具**：写文件/执行命令/网络请求等，除非明确 allow。
- [ ] **敏感信息不落盘**：API keys、tokens、私钥内容、cookie 等不得写入 events（或可配置脱敏）。
- [ ] **提示词注入对抗**：用户试图绕过 allowed_tools/permissions 时仍不越权（离线硬不变量必须覆盖）。
- [ ] **SSRF/内网访问控制（如有网络工具）**：默认禁止访问内网/本机/metadata IP；策略可测。
- [ ] **路径注入**：符号链接/junction/alias 不能逃逸 sandbox 根目录。
- [ ] **日志注入/控制字符**：tool 输出含控制字符时，不破坏日志或 JSONL。
- [ ] **最小披露**：对外错误不包含敏感路径/密钥；内部 trace 也需脱敏。

### 3.11 可观测性与诊断（强烈建议也写离线用例）

- [ ] **错误定位**：失败时能从 trace 直接定位工具/call_id、权限策略、hook、provider 请求。
- [ ] **指标/计数（如有）**：tool 调用次数、拒绝次数、重试次数、compaction 次数一致且可断言。
- [ ] **日志与 trace 对齐**：日志含 correlation id，可从日志跳到对应 trace 事件（且不泄露 secrets）。

### 3.12 并发与多会话（建议至少有一组 smoke）

- [ ] **同进程多会话并发**：两个 session 同时跑时 trace 不串、tool 结果不串、权限策略不串、hook 状态不串。
- [ ] **共享资源争用**：同 session store 根目录下并发写入不会覆盖（或明确拒绝并发并报错清晰）。
- [ ] **背压与队列**：大量 tool calls 时不会无限堆积内存（有队列上限/拒绝策略）。

### 3.13 兼容性与“对齐 Python 参考实现”（推荐）

- [ ] **同脚本、同工具、同配置**：Swift 端与 Python 端产出的关键事件集合一致（允许噪声字段不同）。
- [ ] **决策一致**：permission/allowed_tools 的决策一致；拒绝原因可对齐或至少可映射。
- [ ] **resume 语义一致**：恢复后不重复执行副作用工具（除非明确设计要重放）。
- [ ] **规范化一致**：字段命名、`null` vs 缺字段、默认值填充策略一致（或在 normalizer 中明确差异）。

### 3.14 Skills / Commands / Project 兼容（如 Swift 端要做功能对齐）

- [ ] **发现与加载**：能从预期目录发现 `SKILL.md`/commands 配置；目录不存在行为明确。
- [ ] **解析鲁棒性**：空文件/超大文件/非法 front matter 不 crash；模板变量缺失有明确策略。
- [ ] **安全边界**：加载不应越界读取任意路径；skills/commands 不能绕过 permissions/allowed_tools。
- [ ] **可追溯性**：skill/command 的加载/执行可在 trace 中定位到来源（路径/名称/版本 hash，脱敏后）。

---

## 4. “从 Checklist 到 套件”的落地打法（建议执行顺序）

1) 先实现 `ScriptedProvider` + 真 session store + 真 permission gate 的最小闭环（3～5 个用例）。
2) 把 **3.1～3.6** 中最关键的硬不变量补齐到 25～40 个离线用例（每个用例都断言 trace）。
3) 再加 “最小追溯门禁脚本”：suite 清单必须与 PRD/plan 的矩阵一致。
4) 最后再考虑在线/随机性套件（nightly/手动 + pass-rate）。

### 4.1 建议的离线用例“目录”（可直接抄成 40～80 个）

下面给一个更“可直接落成文件名”的清单（不要求一次写完，但建议按优先级逐步填满）。  
每个用例都尽量做到：**固定输入脚本 + 固定工具 + 固定权限策略 + 断言 trace**。

**事件与落盘**
- [ ] `offline_events_jsonl_roundtrip_unicode`
- [ ] `offline_events_no_delta_persistence`
- [ ] `offline_events_call_id_bijection`
- [ ] `offline_events_strict_required_fields`
- [ ] `offline_events_redaction_no_secrets`
- [ ] `offline_events_unknown_fields_forward_compat`
- [ ] `offline_events_seq_monotonic`
- [ ] `offline_events_dedup_on_retry`

**runtime/tool loop**
- [ ] `offline_loop_zero_tool_calls`
- [ ] `offline_loop_single_tool_call_success`
- [ ] `offline_loop_multi_tool_calls_serial`
- [ ] `offline_loop_tool_raises_exception`
- [ ] `offline_loop_tool_returns_non_json`
- [ ] `offline_loop_max_tool_calls_fuse`
- [ ] `offline_loop_cancel_mid_run_no_partial_jsonl`
- [ ] `offline_loop_timeout_provider_vs_tool_classification`
- [ ] `offline_loop_unhandled_exception_becomes_error_event`

**tools / plumbing**
- [ ] `offline_tool_args_missing_field`
- [ ] `offline_tool_args_wrong_type`
- [ ] `offline_tool_args_unknown_properties`
- [ ] `offline_tool_args_json_string_instead_of_object`
- [ ] `offline_tool_output_large_payload_truncate_or_summarize`
- [ ] `offline_tool_registry_duplicate_name_policy`
- [ ] `offline_allowed_tools_enforced_across_turns`
- [ ] `offline_allowed_tools_preserved_after_compaction`

**permission gate**
- [ ] `offline_permission_allow_all`
- [ ] `offline_permission_deny_records_reason`
- [ ] `offline_permission_prompt_no_answerer_fails_fast`
- [ ] `offline_permission_prompt_answerer_happy_path`
- [ ] `offline_permission_default_deny_on_schema_parse_error`
- [ ] `offline_permission_scope_precedence`

**hooks**
- [ ] `offline_hooks_before_model_call_mutates_messages`
- [ ] `offline_hooks_pre_tool_use_mutates_args`
- [ ] `offline_hooks_order_is_stable`
- [ ] `offline_hooks_exception_is_recorded_and_isolated`
- [ ] `offline_hooks_cannot_bypass_permissions`

**sessions/resume**
- [ ] `offline_session_resume_continues_without_replaying_side_effect_tool`
- [ ] `offline_session_truncated_line_recovery_policy`
- [ ] `offline_session_concurrent_sessions_isolation`
- [ ] `offline_session_custom_home_dir`
- [ ] `offline_session_unicode_paths`

**compaction（如有）**
- [ ] `offline_compaction_trigger_and_records_event`
- [ ] `offline_compaction_preserves_permissions_and_allowed_tools`
- [ ] `offline_compaction_failure_fallback`

**provider 适配（离线模拟即可）**
- [ ] `offline_provider_timeout_is_classified`
- [ ] `offline_provider_rate_limit_backoff_uses_fake_clock`
- [ ] `offline_provider_invalid_json_response_is_handled`
- [ ] `offline_provider_stream_parse_half_packet`

**安全（如有相关工具）**
- [ ] `offline_security_path_traversal_blocked`
- [ ] `offline_security_symlink_escape_blocked`
- [ ] `offline_security_ssrf_blocked_default`
- [ ] `offline_security_control_chars_do_not_break_jsonl`

---

## 5. 评审者用 Checklist（你给 Swift 同学 Code Review 时可用）

- [ ] 离线套件是否真的不依赖真实网络/真实 LLM？
- [ ] 失败时能否快速定位：SDK 回归 vs 外部波动/模型随机性？
- [ ] 断言是否主要基于 trace/tool.result/落盘，而不是最终自然语言？
- [ ] sessions/resume 是否覆盖截断/坏行/中断恢复与“不重放副作用”？
- [ ] permission/allowed_tools 是否默认安全、拒绝可解释且可审计？
- [ ] hooks/tool plumbing 是否覆盖缺字段/类型错/超大 payload/异常等边界？
- [ ] 是否有追溯矩阵门禁，防止套件膨胀后失控？
- [ ] Swift 并发取消路径是否有用例（避免吞掉取消导致死等/泄漏/半写入）？

---

## 6. 附录：单个离线用例的“模板断言清单”

建议每个离线 hard-invariant 用例都按下面的顺序组织，保证“可读、可复用、可定位”：

### 6.1 Given / When / Then 模板（建议）

- **Given**
  - 固定 fake clock（若有）与固定 seed（若有随机）。
  - `TempSessionDir`：会话根目录在临时路径（iOS/macOS 沙箱内）。
  - 固定工具集合（尽量用标准 `ToolTestDoubles`）。
  - 固定 permission 策略（allow/deny/prompt + 固定回答器）。
  - 固定 hooks（如用到）。
  - 固定 `ScriptedProvider` 脚本（明确每轮返回的 tool calls/最终文本）。
- **When**
  - 运行一次 query/run（建议只跑一轮，避免一个用例覆盖太多语义）。
- **Then**
  - 断言运行结果（状态/返回值）。
  - 断言 trace（事件序列）与 session 文件内容（若落盘）。

### 6.2 每个用例都建议包含的 trace 断言（最小集）

- [ ] 有且只有一个 `session_id`（或等价 session 标识）。
- [ ] `user_message`/`assistant_message` 的角色/内容字段完整（按实现）。
- [ ] 每个 `tool_use`：`call_id` 存在且唯一；tool name 与 arguments 可解释。
- [ ] 每个 `tool_result`：能关联到对应 `call_id`；成功/失败状态明确。
- [ ] 不出现任何 streaming delta 事件（`*_delta`）。
- [ ] trace 中不出现 secrets（敏感字段黑名单断言）。
- [ ] 事件顺序满足基本因果（或具备可恢复语义）。

### 6.3 建议的“失败消息”规范（提高排障速度）

- [ ] 断言失败时输出：`session_id`、`run_id`（若有）、`call_id`、事件 `seq`/索引、对应事件的最小 JSON 摘要。
- [ ] 对字段缺失/类型错误/未知事件给出明确提示（例如：`missing required field: call_id in tool_use`）。

---

## 7. 附录：高级测试（强烈建议，但不必一开始做全）

### 7.1 Property-based / Fuzz（解析与鲁棒性）

- [ ] **tool arguments fuzz**：随机生成 JSON（深度/宽度/类型混合/超长字符串/非法 Unicode），保证不 crash，并返回结构化可解释错误或被规范化。
- [ ] **events.jsonl fuzz**：随机插入截断行、非法 JSON、超大行、控制字符，确保读取/恢复策略可预测且不会死循环。
- [ ] **schema 演进 fuzz**：对工具 schema 做可选字段增删/默认值变更/顺序变化，验证向后兼容策略。

### 7.2 Chaos / Cancellation（并发取消与资源回收）

- [ ] 在随机时刻触发取消（provider 请求中、tool 执行中、写 trace 中），确保：
  - [ ] 不产生半行 JSON；
  - [ ] 文件句柄关闭；
  - [ ] 后台 Task/线程不泄漏；
  - [ ] trace 有可解释的“中断/取消”证据（若选择记录）。

### 7.3 Metamorphic（同义变形不改变硬语义）

- [ ] 同一脚本的 tool arguments 字段顺序不同、多余空白、等价数字表示（若允许）下，hard-invariant 结果应一致。

---

## 8. 附录：Swift 生态高频坑与必测点

- [ ] **`null` vs 缺字段**：`Codable` 默认值与缺字段处理差异，容易导致“看似一样但语义不同”。
- [ ] **取消被吞**：`CancellationError` 被 catch 后没重新抛，导致资源不回收或 trace 卡死。
- [ ] **actor/Sendable 误用**：`@unchecked Sendable` 掩盖竞态；必须用并发 smoke 抓出来。
- [ ] **文件系统差异**：iOS 沙箱、文件协调（如 iCloud 场景）、原子写入边界；session store 必测。
- [ ] **URLSession 行为差异**：重定向、TLS、代理、超时、后台会话等导致错误分类混乱；contract 测试别偷懒。
- [ ] **日志泄露 secrets**：debug 日志输出 headers/token；必须用测试断言 trace/log 不含敏感字段。

