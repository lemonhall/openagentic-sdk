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
  - **零 flake（不抖动）**：同样输入在同机多跑结果一致；不依赖时间/随机数/调度顺序。
  - **失败可解释**：失败能直接定位到“哪个不变量被破坏”（而不是泛泛的断言失败）。
  - **断言以 trace 为主**：用 `events.jsonl`/关键事件做断言，而不是自然语言最终输出。
- **在线/随机性套件**（online / stochastic flows）：
  - 可以 nightly、手动触发或按阈值（pass-rate）门禁。
  - 失败更多是“环境/模型/提供方变化”，不应该掩盖 SDK 回归。

### 0.1 非目标（避免误测）

- 不测 CLI 交互（输入编辑、多行粘贴、TTY/PTY/ConPTY）。
- 不把“模型是否会规划工具/是否按提示词写得好”当成硬门禁（除非你们明确愿意承担随机性）。
- 不把“费用/速度优化”当成阻碍（你们可以做，但不要让它反过来降低信噪比）。

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
- [ ] 支持“脚本断言”：能断言 runtime 发给 provider 的输入（messages/system/tool schemas）与预期一致。
- [ ] 支持“确定性调度”：对并发/异步路径，至少在测试里能强制串行或固定顺序。
- [ ] 支持“可插入时钟/随机源”：用 fake clock、固定 seed，避免时间/随机导致 flake。
- [ ] 支持“响应变形器”：同一语义用不同字段顺序/空白/可选字段，验证解析鲁棒性。

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
- [ ] 有“事件规范化器”（normalizer）：可选择性忽略噪声字段（timestamp、duration、provider_request_id 等）。
- [ ] 有“严格模式”（strict）：用于 hard invariants，禁止缺失必需字段/禁止关键语义漂移。
- [ ] 有“序列号/单调递增顺序”（推荐）：每个事件有 `seq` 或等价字段，方便定位缺失/重复。
- [ ] 有“最小证据链”断言：每个 tool.use 必有对应 tool.result（除非被 permission deny）。

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
- [ ] `TempSessionDir`：所有测试写入临时目录，绝不污染 repo。
- [ ] `InMemorySessionStore`（可选）：用于极少数“只测事件逻辑不测 IO”的用例，但 hard invariants 仍建议走真实文件 IO。
- [ ] `EventAsserts`：统一断言工具（包含“事件序列”“关联关系”“字段存在性”“敏感信息脱敏”等）。
- [ ] `ToolTestDoubles`：一组标准工具（成功/失败/慢/大输出/非 JSON 输出/副作用工具），让边界测试可复用。

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
- [ ] **字段一致性**：同一类事件在不同代码路径产出的字段一致（避免“有时叫 X、有时叫 Y”）。
- [ ] **顺序语义**：
  - [ ] 如果是严格顺序：事件按发生顺序写入（至少 tool.use 在 tool.result 之前）。
  - [ ] 如果允许乱序：必须通过 `seq`/`call_id` 等字段恢复语义。
- [ ] **幂等写入**：同一事件不会被重复写入（重试/恢复路径尤其需要测）。
- [ ] **可检索性**：每个 session 有稳定的 `session_id`；每次 run 有 `run_id`（推荐）便于定位。
- [ ] **敏感信息脱敏**：trace 中不出现 API key/token/私钥内容/设备 token/cookie（可测）。
- [ ] **编码/Unicode**：包含 emoji、组合字符、中文、不同 NFC/NFD 规范化差异时仍可 round-trip。

### 3.2 Runtime 核心循环（query loop / tool loop）

- [ ] **0 工具调用**：模型直接返回最终文本，loop 正常结束并落盘完整事件。
- [ ] **1 工具调用**：一次 tool.use → tool.result → 最终文本；事件顺序与关联正确。
- [ ] **多工具串行**：A → B → C 调用顺序稳定；任何一步失败行为可预测（继续/终止策略可测）。
- [ ] **工具返回非 JSON**：tool.result 的内容仍可存储并可回放；不会导致解析崩溃。
- [ ] **取消/中断**：中途取消会话不会留下“半行 JSON”；恢复策略明确（例如标记 aborted）。
- [ ] **超时**：provider 超时、tool 超时分别处理；错误分类准确、可重试策略正确。
- [ ] **重试幂等**：若有重试，确保不会对有副作用的 tool 重复执行（或有幂等 key）。
- [ ] **并发语义（若支持）**：并发 tool calls 的结果合并稳定；事件可解释且可恢复。
- [ ] **最大步数/熔断**：防止模型/脚本输出无限 tool call（max tool calls、max depth）并可测。
- [ ] **递归/再入保护**：tool 调用过程中触发二次 query（若允许）有明确策略；若不允许，能安全拒绝。
- [ ] **异常边界**：任何未捕获异常都应产生可解释的错误事件（或明确“崩溃即失败”的策略）并确保资源回收。
- [ ] **资源回收**：会话结束后不会遗留后台协程/线程；多次运行不会累积内存泄漏（可做粗粒度 smoke）。
- [ ] **输入裁剪策略（如有）**：长历史裁剪/窗口化不会破坏 hard constraints（permissions/allowed_tools）。

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
- [ ] **schema 版本与演进**：工具 schema 的新增字段/默认值变更不会破坏旧脚本/旧事件解析。
- [ ] **参数容错**：arguments 来自模型时可能是 JSON 字符串而非对象、类型被转成字符串、或包含额外字段；行为必须明确且可测。
- [ ] **工具输出通道**：tool.result 同时覆盖结构化 JSON、纯文本；若支持二进制则必须有编码策略（base64 + mime + size limit）。
- [ ] **副作用工具防重放**：有“幂等 key/nonce”或明确禁止在 resume 后自动重放。
- [ ] **工具执行隔离**：一个工具失败不会污染其他工具上下文（例如共享状态/全局单例）。
- [ ] **工具日志**：工具内部日志不会泄露 secrets；日志与 trace 的关联可解释（最好有 correlation id）。

### 3.4 Permission Gate（人类在环 / 权限门）

- [ ] **allow 模式**：工具正常执行，事件记录完整。
- [ ] **deny 模式**：工具不执行；事件记录包含拒绝原因/策略来源；loop 行为可预测。
- [ ] **prompt 模式**：
  - [ ] 有交互 callback 时能得到答案并继续。
  - [ ] 无交互环境下不会死等；有清晰失败方式（可测）。
- [ ] **bypass/always-allow（若存在）**：仅在明确配置下生效；默认不越权。
- [ ] **安全默认**：schema 解析失败、未知工具、未知策略时不应默认放行。
- [ ] **策略作用域**：全局/会话级/单次调用级的优先级明确且可测。
- [ ] **可审计性**：每次 allow/deny 都应产生可审计的事件（策略 id、匹配理由、用户回答（若有））。
- [ ] **策略缓存（如有）**：相同工具重复请求时，缓存不会越权（例如“第一次 allow 不代表永久 allow”除非明确）。
- [ ] **拒绝后的行为**：deny 后 runtime 是继续对话、返回错误，还是要求模型改计划？策略明确且可测。
- [ ] **边界输入**：用户回答为空/超长/包含特殊字符/包含 JSON 时，prompt 模式仍稳定。

### 3.5 Hooks（可插拔改写/拦截）

- [ ] **触发点覆盖**：Before/AfterModelCall、Pre/PostToolUse、UserPromptSubmit（按实现）。
- [ ] **改写生效**：
  - [ ] hook 修改系统提示词/消息列表后，provider 输入确实变化（可通过 trace 断言）。
  - [ ] hook 修改 tool 参数后，tool.use 记录的是改写后的参数。
- [ ] **hook 拒绝/短路**：hook 决定中止时，事件记录完整且会话状态一致。
- [ ] **hook 异常隔离**：hook 报错不会把整个会话“无记录地”打死（要么落错误事件，要么策略化失败）。
- [ ] **hook 顺序**：多个 hook 的执行顺序固定且可配置（或明确“注册顺序即执行顺序”），并可测。
- [ ] **可重入/线程安全**：hook 在并发会话下不会互相污染（避免共享可变全局状态）。
- [ ] **幂等性**：同一事件因重试/恢复导致 hook 可能被重复触发时，hook 行为仍安全（或明确不支持）。
- [ ] **性能与超时**：hook 很慢时不会拖死整体（可设置 hook timeout 或至少保证可取消）。
- [ ] **hook 对工具列表的影响**：hook 增删工具时，allowed_tools 与 permission gate 仍然生效（不会被绕过）。

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
- [ ] **文件锁/并发写**：在 Windows/Linux/macOS 下表现一致（或明确只支持某些平台），并可测。
- [ ] **flush/fsync 策略**：关键事件是否 flush/fsync，崩溃恢复边界清晰（至少可通过测试观察）。
- [ ] **路径长度与 Unicode 路径**：长路径、中文路径、特殊字符路径下 session 仍可读写。
- [ ] **跨版本迁移**：旧版本写出的 events，新版本能读；新版本写出的 events，旧版本至少能跳过未知类型/字段。
- [ ] **只读恢复（推荐）**：resume 支持只读模式，避免无意间写入/覆盖原 trace。
- [ ] **校验与修复**：提供（或至少测试）对坏行/截断的诊断输出，便于定位具体哪一行坏了。

### 3.7 Compaction / Summarization（如有）

- [ ] **可控触发**：token/轮数/大小阈值可配置；离线用例可强制触发。
- [ ] **硬约束不丢**：allowed_tools、permission 策略、系统提示词中的安全约束不会因 compaction 消失。
- [ ] **可解释事件**：compaction 前后都有明确事件记录（原因、输入范围、输出摘要）。
- [ ] **resume 后不漂移**：恢复后不会二次 compaction 导致不可预测的状态漂移。
- [ ] **工具结果保留策略**：tool.result 是否被摘要/保留/丢弃必须明确；hard invariants 建议保留最小证据链。
- [ ] **可测试的“压缩不变量”**：压缩前后对外行为一致（permissions/allowed_tools/session_id/tool registry 不变）。
- [ ] **压缩失败处理**：compaction 过程失败时，不应破坏会话；有回退策略与事件记录。

### 3.8 Provider 抽象与适配

- [ ] **ScriptedProvider 是一等公民**：离线 E2E 不依赖真实网络/真实 LLM。
- [ ] **错误分类**：鉴权失败、限流、超时、连接失败、响应字段缺失/变形都有覆盖。
- [ ] **响应解析鲁棒**：提供方新增字段/顺序变化不会导致崩溃；缺字段有清晰错误。
- [ ] **重试与退避**：仅对可重试错误重试；次数/间隔可配置且可测。
- [ ] **流式协议解析**：SSE/chunked JSON 在半包/粘包、空行、非法 JSON 下行为可预测且不会写坏 session。
- [ ] **HTTP 细节**：重定向、代理、TLS 错误、证书问题、DNS 失败都能分类清楚（至少不要被吞掉）。
- [ ] **请求幂等**：重试时不会把同一请求写成两个 run；run_id/trace 关联清晰。
- [ ] **速率限制与 backoff**：对 429/503 等按策略退避；退避可注入 fake clock 以避免测试变慢。
- [ ] **可观测性**：provider 提供 request_id/response_id 时写入 trace（脱敏后），方便排障。

### 3.9 配置与跨平台一致性（Kotlin/Java 生态常见坑）

- [ ] **环境变量优先级**：参数 vs env vs 默认，优先级固定且可测。
- [ ] **路径规范化**：`..`、绝对/相对路径、Windows 盘符、分隔符差异都能正确处理。
- [ ] **目录穿越防护**：任何写文件类工具不得写出允许的根目录（canonical path 校验）。
- [ ] **时区/locale**：时间戳采用稳定格式（建议 epoch 或 ISO-8601 + 固定时区）；locale 不影响解析。
- [ ] **大文本**：超长 prompt、超长 tool 输出、超长历史不会 OOM（至少有上限与可测退化策略）。
- [ ] **编码与换行**：LF/CRLF 不影响解析；对文本工具输出的换行策略一致。
- [ ] **协程取消**：取消异常不会被吞掉导致资源泄漏；取消后 trace 仍可解释。
- [ ] **线程池/调度器**：不同调度器下行为一致；测试中尽量使用单线程调度器确保确定性。
- [ ] **序列化库差异**：对 `null`、缺字段、默认值的语义差异有覆盖（尤其是 `null` vs 缺字段）。
- [ ] **浮点与大整数**：JSON 数字解析为 `Long`/`Double` 时不产生不可逆漂移（或明确禁止某些类型）。

### 3.10 安全（默认不越权）

- [ ] **默认拒绝高风险工具**：写文件/执行命令/网络请求等，除非明确 allow。
- [ ] **敏感信息不落盘**：API keys、tokens、私钥内容、cookie 等不得写入 events（或可配置脱敏）。
- [ ] **提示词注入对抗**：用户试图绕过 allowed_tools/permissions 时仍不越权（离线硬不变量必须覆盖）。
- [ ] **SSRF/内网访问控制（如有网络工具）**：默认禁止访问内网/本机/metadata IP；策略可测。
- [ ] **命令注入（如有 exec 工具）**：参数严格分离；禁止拼接 shell；Windows/Unix 都可测。
- [ ] **路径注入**：盘符/UNC、`/etc/`、符号链接跳转都不能突破 sandbox 根目录。
- [ ] **日志注入/控制字符**：tool 输出包含控制字符时，不会污染日志系统或破坏 JSONL。
- [ ] **最小披露**：错误信息对外不包含敏感路径/密钥内容；内部 trace 可有更多信息但需脱敏。

### 3.11 可观测性与诊断（强烈建议也写离线用例）

- [ ] **错误定位**：失败时能从 trace 直接定位哪个工具/哪个 call_id、哪个权限策略、哪个 hook、哪个 provider 请求。
- [ ] **指标/计数（如有）**：tool 调用次数、拒绝次数、重试次数、compaction 次数一致且可断言。
- [ ] **日志与 trace 对齐**：日志包含 correlation id，可从日志跳到对应 trace 事件（且不泄露 secrets）。

### 3.12 并发与多会话（建议至少有一组 smoke）

- [ ] **同进程多会话并发**：两个 session 同时跑时 trace 不串、tool 结果不串、权限策略不串、hook 状态不串。
- [ ] **共享资源争用**：同一个 session store 根目录下并发写入不会互相覆盖（或明确拒绝并发并报错清晰）。
- [ ] **背压与队列**：大量 tool calls 时不会无限堆积内存（有队列上限/拒绝策略）。

### 3.13 兼容性与“对齐 Python 参考实现”（推荐）

- [ ] **同脚本、同工具、同配置**：Kotlin 端与 Python 端产出的关键事件集合一致（允许噪声字段不同）。
- [ ] **决策一致**：permission/allowed_tools 的决策一致；拒绝原因可对齐或至少可映射。
- [ ] **resume 语义一致**：恢复后不会重复执行副作用工具（除非明确设计要重放）。
- [ ] **规范化一致**：字段命名、`null` vs 缺字段、默认值填充策略一致（或在 normalizer 中明确差异）。

### 3.14 Skills / Commands / Project 兼容（如 Kotlin 端要做功能对齐）

如果 Kotlin SDK 也要承接 `.claude/` 的 commands/skills 兼容层（或任何“从项目目录加载行为模板”的能力），建议至少覆盖：

- [ ] **发现与加载**：
  - [ ] 能从预期目录发现 `SKILL.md`/commands 配置；目录不存在行为明确。
  - [ ] 文件编码（UTF-8）、CRLF/LF、BOM 差异不影响解析。
  - [ ] 缓存策略明确：文件变更后是否自动 reload、是否需要显式刷新；行为可测。
- [ ] **解析鲁棒性**：
  - [ ] `SKILL.md` 内容为空/超大/包含非法前言（front matter）时不会 crash。
  - [ ] 模板变量替换（如有）对缺失变量有明确策略（报错/留空/默认值）。
- [ ] **安全边界**：
  - [ ] 项目内加载不应越界读取任意路径（路径规范化 + sandbox 根目录约束）。
  - [ ] Skills/commands 不得绕过 permissions/allowed_tools（即使模板里“要求你执行危险工具”也必须过门）。
- [ ] **可追溯性**：
  - [ ] 每次 skill/command 被加载/执行，都能在 trace 中定位到来源（文件路径/skill 名/版本 hash，脱敏后）。

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
- [ ] `offline_events_call_id_bijection`（tool.use ↔ tool.result 一一对应）
- [ ] `offline_events_strict_required_fields`
- [ ] `offline_events_redaction_no_secrets`
- [ ] `offline_events_unknown_fields_forward_compat`
- [ ] `offline_events_seq_monotonic`（如有 seq）
- [ ] `offline_events_dedup_on_retry`（重试不重复写事件）

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
- [ ] `offline_allowed_tools_preserved_after_compaction`（如有 compaction）

**permission gate**
- [ ] `offline_permission_allow_all`
- [ ] `offline_permission_deny_records_reason`
- [ ] `offline_permission_prompt_no_answerer_fails_fast`
- [ ] `offline_permission_prompt_answerer_happy_path`
- [ ] `offline_permission_default_deny_on_schema_parse_error`
- [ ] `offline_permission_scope_precedence`（全局/会话/单次）

**hooks**
- [ ] `offline_hooks_before_model_call_mutates_messages`
- [ ] `offline_hooks_pre_tool_use_mutates_args`
- [ ] `offline_hooks_order_is_stable`
- [ ] `offline_hooks_exception_is_recorded_and_isolated`
- [ ] `offline_hooks_cannot_bypass_permissions`（hook 改写也必须过权限）

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
- [ ] `offline_provider_stream_parse_half_packet`（如有 stream）

**安全（如有相关工具）**
- [ ] `offline_security_path_traversal_blocked`
- [ ] `offline_security_symlink_escape_blocked`
- [ ] `offline_security_ssrf_blocked_default`
- [ ] `offline_security_command_injection_not_possible`
- [ ] `offline_security_control_chars_do_not_break_jsonl`

---

## 5. 评审者用 Checklist（你给 Kotlin 同学 Code Review 时可用）

- [ ] 离线套件是否真的**不依赖**真实网络/真实 LLM？
- [ ] 失败时能否快速定位：是“SDK 回归”还是“外部波动/模型随机性”？
- [ ] 用例断言是否主要基于 **trace/tool.result/落盘**，而不是基于最终自然语言？
- [ ] sessions/resume 是否覆盖了截断/坏行/中断恢复？
- [ ] permission/allowed_tools 是否默认安全、拒绝可解释？
- [ ] hooks/tool plumbing 的边界条件是否覆盖了“缺字段/类型错/超大 payload/异常”？
- [ ] 是否有追溯矩阵门禁，防止套件膨胀后失控？

---

## 6. 附录：单个离线用例的“模板断言清单”

建议每个离线 hard-invariant 用例都按下面的顺序组织，保证“可读、可复用、可定位”：

### 6.1 Given / When / Then 模板（建议）

- **Given**
  - 固定 `FakeClock`（若有）与固定 seed（若有随机）。
  - `TempSessionDir`：会话根目录在临时路径。
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
- [ ] 每个 `tool_use`：
  - [ ] `call_id` 存在且唯一；
  - [ ] tool name 与 arguments 可读、可解释（不依赖字段顺序）。
- [ ] 每个 `tool_result`：
  - [ ] 能关联到对应 `call_id`；
  - [ ] 成功/失败状态明确（`ok`/`error`/`denied` 等）。
- [ ] 不出现任何 streaming delta 事件（`*_delta`）。
- [ ] trace 中不出现 secrets（可用“敏感字段黑名单”断言）。
- [ ] 事件顺序满足基本因果（至少 `tool_use` 在对应 `tool_result` 之前，或具备可恢复语义）。

### 6.3 建议的“失败消息”规范（提高排障速度）

- [ ] 断言失败时输出：`session_id`、`run_id`（若有）、`call_id`、事件 `seq`/索引、以及对应事件的最小 JSON 摘要。
- [ ] 对“字段缺失/类型错误/未知事件”给出明确提示（例如：`missing required field: call_id in tool_use`）。

---

## 7. 附录：高级测试（强烈建议，但不必一开始做全）

这些测试不是为了“增加数量”，而是为了覆盖**人类很难枚举**的边界输入与非预期组合，提高长期稳定性。

### 7.1 Property-based / Fuzz（解析与鲁棒性）

- [ ] **tool arguments fuzz**：随机生成 JSON（深度/宽度/类型混合/超长字符串/非法 Unicode），保证：
  - [ ] 不 crash；
  - [ ] 要么被规范化成合法参数，要么返回结构化、可解释的错误。
- [ ] **events.jsonl fuzz**：随机插入：
  - [ ] 截断行；
  - [ ] 非法 JSON；
  - [ ] 超大行；
  - [ ] 混入控制字符；
  确保读取/恢复策略可预测（跳过/失败/诊断输出）且不会进入死循环。
- [ ] **schema 演进 fuzz**：对工具 schema 做“可选字段增删/默认值变更/字段顺序变化”，验证向后兼容策略。

### 7.2 Chaos / Cancellation（协程与资源回收）

- [ ] 在随机时刻触发取消（provider 请求中、tool 执行中、写 trace 中），确保：
  - [ ] 不产生半行 JSON；
  - [ ] 文件句柄关闭；
  - [ ] 后台协程/线程没有泄漏；
  - [ ] trace 有可解释的“中断/取消”证据（若你们选择记录）。

### 7.3 Metamorphic（同义变形不改变硬语义）

- [ ] 同一脚本的 tool arguments：
  - [ ] 字段顺序不同；
  - [ ] 多余空白；
  - [ ] 等价的数字表示（`1` vs `1.0`，若允许）；
  其 hard-invariant 结果应一致（事件关键字段一致、权限决策一致）。

---

## 8. 附录：Kotlin/Java 生态的“高频坑”与必测点

- [ ] **`null` vs 缺字段**：序列化/反序列化默认值差异会导致“看似一样但语义不同”，必须用 golden trace 约束。
- [ ] **协程取消被吞**：`CancellationException` 被 catch 后没重新抛，导致资源不回收或 trace 卡死；必须写取消类用例。
- [ ] **线程安全错觉**：单测总是串行跑，但真实 SDK 会多会话并发；至少写一个并发 smoke。
- [ ] **文件系统差异**：Windows 文件锁、路径大小写、符号链接/junction、长路径；session store 必测。
- [ ] **HTTP 客户端差异**：OkHttp/ktor 的重试、重定向、代理/TLS 行为；错误分类别混成一个“网络错误”。
- [ ] **日志泄露 secrets**：debug 日志把 headers/token 打出来；务必用测试断言“trace/log 不含敏感字段”。
