# TypeScript SDK（核心模块 / 不含 CLI）E2E 测试 Checklist

面向：正在把 `openagentic-sdk` 的核心能力移植到 TypeScript（Node.js / Browser / Deno 形态 SDK）的同学。  
目标：把“SDK 回归”与“模型随机性/网络波动”拆开，用一套**离线、确定性、可追溯**的 E2E 把核心模块的硬不变量钉死。

> 约定：本文不覆盖 CLI（TTY/PTY、输入编辑、多行粘贴等），只覆盖 SDK 核心模块：runtime/tool loop、tools、permissions、hooks、sessions/resume、provider 适配层，以及（如有）skills/commands/project 兼容层。

---

## 0. 成功标准（强烈建议）

- **离线硬不变量套件**（offline hard invariants）：
  - 必须 **100% 通过**，失败基本等价于“SDK 回归/协议破坏”。
  - 必须可在 CI **每次 PR** 自动跑。
  - 不依赖真实网络、不依赖真实 LLM、不依赖人类交互、不依赖系统 TTY。
  - **零 flake（不抖动）**：同样输入多跑一致；不依赖真实时间、随机数、事件循环调度。
  - **失败可解释**：能定位到哪个硬不变量被破坏。
  - **断言以 trace 为主**：用 `events.jsonl`/关键事件断言，而不是自然语言最终输出。
- **在线/随机性套件**（online / stochastic flows）：
  - 可以 nightly/手动/阈值门禁（pass-rate）。
  - 失败更多是外部变化，不应掩盖 SDK 回归。

### 0.1 非目标（避免误测）

- 不测 CLI 交互（输入编辑、多行粘贴、TTY/PTY）。
- 不把“模型是否会规划工具/是否按提示词写得好”当硬门禁（除非愿意承担随机性）。
- 不把“bundle/打包性能”当阻碍（可以优化，但不要降低信噪比）。

### 0.2 支持目标（建议显式声明，否则很难写“无遗漏”的用例）

TypeScript SDK 很容易“一份代码跑很多 runtime”。要想测试不遗漏，建议先在仓库里明确你们支持什么：

- [ ] **运行时目标**（逐项写清是否支持）：
  - [ ] Node.js（版本范围：例如 18/20/22）
  - [ ] Browser（Chrome/Firefox/Safari？是否需要兼容 WebView）
  - [ ] Deno（如支持）
  - [ ] Edge/Workers（如 Cloudflare Workers / Vercel Edge / Service Worker）
  - [ ] Bun（如支持）
- [ ] **模块系统/构建形态**：
  - [ ] ESM
  - [ ] CJS
  - [ ] 双产物（conditional exports）
  - [ ] bundler（webpack/vite/rollup/esbuild）是否要求可用
- [ ] **存储形态（sessions/trace）**：
  - [ ] Node：文件系统
  - [ ] Browser：IndexedDB / OPFS / localStorage（不推荐）/ 内存
  - [ ] Workers：KV/Durable Object/内存（按平台）
- [ ] **网络形态（provider）**：
  - [ ] `fetch`（标准 WHATWG）
  - [ ] Node fetch（undici）
  - [ ] SSE/stream：Web Streams / Node Streams

---

## 1. 测试分层建议（套件结构）

### A) Offline Hard Invariants（必做）

核心思路：提供 `ScriptedProvider`（回放 provider），按脚本返回 tool calls 与最终文本；断言重点是 trace/权限/落盘/恢复/边界。

### B) Online Contract（可选但很有价值）

只测 provider 适配（HTTP、SSE/stream、错误分类、响应解析、重试/超时），不测模型质量。

### C) Stochastic Model-Driven Flows（可选）

多次运行 + pass-rate + 失败归因报告落盘。

---

## 2. 必备测试基础设施（TypeScript 侧建议先做）

### 2.1 ScriptedProvider（离线确定性）

Checklist：
- [ ] 支持按脚本输出 `tool_calls`（name + arguments）与最终文本。
- [ ] 支持多轮脚本（按轮次或按输入历史决定）。
- [ ] 支持模拟 provider 错误：timeout、rate limit、非 2xx、响应字段缺失/变形。
- [ ] 支持流式与非流式两条路径（流式不应落盘 delta）。
- [ ] 支持脚本断言：断言 runtime 发给 provider 的输入（messages/system/tool schemas）与预期一致。
- [ ] 支持确定性调度：测试中固定 microtask/macrotask 顺序（尽量避免依赖真实 `setTimeout`）。
- [ ] 支持可插入时钟/随机源：fake timers、固定 seed。
- [ ] 支持响应变形器：字段顺序/空白/可选字段变体验证解析鲁棒性。

> TS 提示：建议把 `Date.now()`、`Math.random()`、`setTimeout`、`fetch`、`crypto.randomUUID()` 等全部抽象成依赖注入或统一 wrapper，测试里用 fake 实现。

### 2.2 Golden Trace（关键事件对齐 / 追溯）

建议产物：
- `events.jsonl`：每行一个 JSON 事件（Node 端写文件，Browser 端可写 IndexedDB 或内存，然后导出 JSONL 作为对齐）。
- 规范化比较器：忽略 timestamp/duration 等噪声字段，严格比较关键字段与关联关系。

Checklist：
- [ ] 允许新增字段但不允许删除/改名核心字段（兼容策略明确可测）。
- [ ] 未知事件类型/字段不崩溃（忽略/透传策略明确）。
- [ ] 有 strict 模式（hard invariants 使用）：缺字段即失败、语义漂移即失败。
- [ ] tool.use/tool.result 可关联（call_id 或等价字段）。
- [ ] 禁止落盘 streaming delta（`*_delta`）。
- [ ] `null` vs 缺字段语义被固定（非常关键：JSON 解析天然会丢掉 `undefined`）。

### 2.3 最小追溯门禁（防止套件失控）

- [ ] 文档里维护 traceability matrix（suite → module/invariant）。
- [ ] CI 脚本检查 suite 清单 ↔ 文档矩阵一致（缺失/重复/引用不存在即 fail）。
- [ ] suite 标签分层（offline/online/stochastic）并决定 CI 触发频率。

### 2.4 最小测试夹具（强烈建议）

- [ ] `FakeClock`：可控时间（fake timers）。
- [ ] `TempSessionDir`：测试写入临时目录（Node：`os.tmpdir()` + `fs.mkdtemp`；Browser：临时 storage）。
- [ ] `EventAsserts`：统一断言（序列、关联、脱敏、禁止 delta）。
- [ ] `ToolTestDoubles`：成功/失败/慢/大输出/非 JSON 输出/副作用工具。
- [ ] `NetworkStubs`：替换 `fetch`（undici/mock、MSW、或自建 stub server）。
- [ ] `AbortAsserts`：统一断言取消/超时路径（AbortController 必测）。
- [ ] `DeterministicScheduler`：统一“任务调度策略”（microtask/macrotask/nextTick），避免事件循环差异导致 flake。
- [ ] `JsonCanonicalizer`：对事件 JSON 做 canonicalization（递归排序 key、规范化 `null` vs 缺字段语义）。
- [ ] `FsSandbox`（Node）：所有写文件限定到 sandbox 根目录；路径规范化/符号链接逃逸在夹具层提供断言。
- [ ] `StorageAdapters`（Browser/Workers）：统一抽象 sessions 存储，使 hard invariants 可复用同一套断言。
- [ ] `RedactionAsserts`：统一断言 trace/log 不含敏感字段（token/密钥/cookie）。

---

## 3. 核心模块 E2E Checklist（离线硬不变量优先）

### 3.1 事件协议（trace/events）硬不变量

- [ ] JSONL 行协议：每行一个 JSON；换行/特殊字符不破坏行边界。
- [ ] 事件类型稳定：user/assistant/tool.use/tool.result/hook/compaction（按实现）。
- [ ] tool.use/result 可关联：call_id 唯一且可恢复语义。
- [ ] 禁止落盘 streaming delta：任何 `*_delta` 不得持久化。
- [ ] 未知字段容忍：新增字段不崩溃；策略明确。
- [ ] 错误事件结构化：type/message/optional stack/code。
- [ ] 尺寸上限：超大事件截断/摘要策略可测。
- [ ] 敏感信息脱敏：trace/log 不含 token/密钥/cookie。
- [ ] Unicode round-trip：中文/emoji/组合字符可恢复。
- [ ] `undefined` vs `null` vs 缺字段：必须定义并测试（JS/JSON 天然会丢 `undefined`）。
- [ ] 数字语义：大整数/浮点精度/NaN/Infinity（若出现）如何处理必须明确并可测（推荐禁止 NaN/Infinity 进入 trace）。
- [ ] 事件顺序语义：至少 `tool_use` 在对应 `tool_result` 之前（或有 `seq`/索引可恢复因果）。
- [ ] 幂等写入：重试/恢复路径不应重复写入同一语义事件（或可去重）。
- [ ] 兼容性：旧版本 events 新版本能读；新字段旧版本至少能跳过不崩溃。
- [ ] 可诊断性：坏行/截断行能定位“第几行/哪条事件坏了”，而不是泛泛报错。

### 3.2 Runtime 核心循环（query loop / tool loop）

- [ ] 0 工具调用：直接最终文本，正常结束并落盘。
- [ ] 1 工具调用：tool.use → tool.result → 最终文本；顺序与关联正确。
- [ ] 多工具串行：失败策略（继续/终止）明确可测。
- [ ] 工具返回非 JSON：仍可落盘与回放。
- [ ] 取消/中断：不会写半行 JSON；取消信号能传播（AbortController/取消 token）。
- [ ] 超时：provider vs tool 超时分类准确；可重试策略正确。
- [ ] 最大步数/熔断：防止无限 tool call。
- [ ] 异常边界：未捕获异常不 silent；必须有可解释证据。
- [ ] backpressure：工具输出/事件写入很大很快时不应无限堆内存（限流/截断/拒绝策略明确可测）。
- [ ] re-entrancy：tool 执行中触发二次 query（若允许）策略明确；若不允许则安全拒绝并落事件。
- [ ] Node vs Browser 事件循环差异：相同脚本/相同 fake timers 下结果一致（避免依赖真实调度）。
- [ ] 资源回收：会话结束后无悬挂定时器/未关闭的 stream/未完成的 promise（可做粗粒度检测）。
- [ ] 未处理 rejection：在任何路径上都能被捕获并转成可解释错误事件（避免进程直接退出）。

### 3.3 Tools 协议与边界（tool plumbing）

- [ ] 参数校验：缺字段/类型错/超长/深层嵌套不 crash。
- [ ] unknown tool：拒绝并落盘可解释错误。
- [ ] 大输出：截断/摘要可测。
- [ ] 工具异常：tool.result 结构化落盘；loop 行为可预测。
- [ ] allowed_tools：allow-list 生效且默认安全；跨轮/compaction 后不丢。
- [ ] 参数容错：arguments 可能是 JSON 字符串、类型被转成字符串、额外字段；行为明确可测。
- [ ] 副作用工具：resume 不重放（或明确重放策略 + 幂等 key）。
- [ ] 工具名匹配：大小写/别名策略明确且可测（避免同名冲突/覆盖）。
- [ ] schema 演进：工具 schema 新增字段/默认值变更不破坏旧脚本（或明确版本门禁）。
- [ ] 输出类型覆盖：结构化 JSON、纯文本；若支持二进制则 base64/mime/size limit 并可测。
- [ ] 工具隔离：一个工具失败不污染其他工具上下文（避免共享全局可变状态）。
- [ ] Web 环境限制：在 Browser/Workers 下不应默认暴露 Node-only 高危工具（如写任意文件/执行命令）。

### 3.4 Permission Gate（权限门）

- [ ] allow/deny/prompt/bypass（如有）路径覆盖。
- [ ] deny：不执行 + 原因/策略来源写入事件。
- [ ] prompt：无回答器不死等（快速失败）。
- [ ] 安全默认：未知策略/解析失败不默认放行。
- [ ] 决策可审计：每次 allow/deny 都有足够证据（规则 id、匹配理由、用户回答（若有））。
- [ ] 拒绝后行为：deny 后继续/返回错误/要求模型改计划等策略明确可测。
- [ ] 缓存策略（如有）：一次允许是否扩大到后续调用？默认应最小授权并可测。

### 3.5 Hooks

- [ ] 触发点覆盖：Before/AfterModelCall、Pre/PostToolUse、UserPromptSubmit（按实现）。
- [ ] 改写生效：messages/tool args 改写后 trace 反映真实变化。
- [ ] hook 异常隔离：不 silent fail。
- [ ] hook 不能越权：必须过 permissions/allowed_tools。
- [ ] hook 顺序：多个 hook 执行顺序固定且可配置，并可测。
- [ ] hook 幂等：重试/恢复导致重复触发时仍安全（或明确不支持）。
- [ ] 并发安全：并发 session 下 hook 状态不串（避免共享全局可变对象）。
- [ ] 性能：hook 过慢不会拖死会话（至少可取消/可超时）。

### 3.6 Sessions / Resume（Node/Browser 双形态要分别覆盖）

- [ ] Node：文件落盘目录默认 + 自定义目录可用；崩溃后已写入行可读；截断/坏行策略明确可测。
- [ ] Browser：存储介质（IndexedDB/OPFS/内存）语义明确；导出/导入 trace 语义一致。
- [ ] resume 一致性：恢复后关键事件语义一致（允许 timestamp 噪声不同）。
- [ ] 不重放副作用：恢复不重复执行已执行工具（除非明确设计要重放）。
- [ ] 并发写：明确支持或明确拒绝；拒绝时错误清晰。
- [ ] Node：符号链接/路径穿越不能写出 sandbox 根目录（canonical path 校验）。
- [ ] Node：flush 边界明确（崩溃时“写到第 N 行”的可观察性）并可测。
- [ ] Browser：容量不足/清理策略/持久化失败时行为可解释且可测。
- [ ] Workers：如果支持无文件系统场景，必须有等价的 session store，并覆盖“恢复语义一致”。
- [ ] 只读恢复（推荐）：resume 支持只读模式，避免覆盖原 trace。

### 3.7 Compaction（如有）

- [ ] 可控触发；硬约束不丢；可解释事件；失败回退。

### 3.8 Provider 适配

- [ ] ScriptedProvider 一等公民：离线不依赖网络。
- [ ] 错误分类：鉴权/限流/超时/连接失败/响应变形都有覆盖。
- [ ] SSE/stream 解析（如有）：半包/粘包/空行/非法 JSON 下不写坏 session。
- [ ] 重试/backoff：使用 fake clock 不让测试变慢。
- [ ] Web Streams vs Node Streams：两条实现（若同时支持）对外语义一致（至少在你们支持的 runtime 上）。
- [ ] `fetch` 差异：不同实现的错误类型/错误消息不同，但必须能被你们统一分类并可测。
- [ ] TLS/证书/DNS：错误不要被吞掉；分类至少能区分“连接失败/超时/响应非法”。
- [ ] request_id/trace 关联：provider 若返回 request id，写入 trace（脱敏后）便于排障。

### 3.9 配置与跨平台一致性（TS 生态常见坑）

- [ ] ESM/CJS：构建产物与运行时差异不改变核心语义（至少在你们支持的形式上可测）。
- [ ] `undefined` vs `null`：JSON 序列化会丢 `undefined`；必须钉死字段缺失语义与 normalizer。
- [ ] CRLF/LF：JSONL 在 Windows/Unix 下可解析。
- [ ] 路径规范化：`..`、符号链接、UNC/盘符（Node）不能突破 sandbox 根目录。
- [ ] 数字语义：大整数精度（JS number）会丢精度；必要时把大整数当字符串处理并写用例约束。
- [ ] Web/Workers 环境限制：无 `process.env`、无 `fs`、无 TCP socket 的情况下，功能降级或明确不支持。
- [ ] 打包副作用：tree-shaking/条件导出可能改变初始化时序；至少断言“import 不产生副作用（不写文件/不发网）”。

### 3.10 安全（默认不越权）

- [ ] 默认拒绝高风险工具（写文件/网络/执行命令等）除非明确 allow。
- [ ] secrets 不落盘：trace/log 不包含 token/密钥。
- [ ] SSRF（如有网络工具）：默认禁止内网/metadata；策略可测。
- [ ] 控制字符/日志注入：工具输出含控制字符不破坏 JSONL。
- [ ] 原型污染（prototype pollution）：来自模型的 JSON arguments 不应污染对象原型（建议使用安全解析/深拷贝策略，并写用例）。
- [ ] Browser：CORS/同源策略下不应试图“绕过”浏览器安全边界；需要后端代理就显式要求。
- [ ] 最小披露：错误信息对外不包含敏感路径/密钥；内部 trace 也必须脱敏。

### 3.11 可观测性与诊断

- [ ] 失败能从 trace 定位到：tool/call_id、权限策略、hook、provider 请求。
- [ ] 指标/计数（如有）可断言：tool 次数、拒绝次数、重试次数、compaction 次数。

### 3.12 并发与多会话（至少一组 smoke）

- [ ] 两个 session 并发：trace 不串、工具结果不串、权限不串、hook 状态不串。

### 3.13 对齐 Python 参考实现（推荐）

- [ ] 同脚本/同配置：关键事件集合一致（允许噪声字段不同）。
- [ ] permission/allowed_tools 决策一致或可映射。
- [ ] resume 不重放副作用语义一致。

### 3.14 Skills / Commands / Project 兼容（如要做功能对齐）

- [ ] 发现与加载：从项目目录发现 `SKILL.md`/commands；不存在时行为明确。
- [ ] 解析鲁棒：空文件/非法 front matter 不 crash。
- [ ] 安全边界：加载不越界读取路径；不得绕过 permissions/allowed_tools。
- [ ] 可追溯：trace 中能定位 skill/command 来源（路径/名称/hash）。

### 3.15 测试运行方式（建议也覆盖成“可验证”的脚本/用例）

- [ ] Node：一条命令可跑完 offline hard invariants（CI 友好），失败时输出可读定位信息。
- [ ] Browser：若支持，至少有一条“headless 浏览器”跑 hard invariants 子集的路径（可选）。
- [ ] 清理策略：测试结束清理临时目录/临时存储；失败时保留并打印路径用于排障。
- [ ] 运行矩阵：Node 版本矩阵（例如 18/20/22）跑同一套 hard invariants，确保无行为漂移。

---

## 4. 落地执行顺序（建议）

1) ScriptedProvider + session store + permission gate 最小闭环（3～5 用例）。
2) 填满 3.1～3.6 到 25～40 个离线用例（每个断言 trace）。
3) 加追溯矩阵门禁脚本。
4) 再做 online/stochastic（nightly/手动 + pass-rate）。

### 4.1 建议的离线用例“目录”（可直接抄成 40～80 个）

每个用例尽量做到：**固定脚本 + 固定工具 + 固定权限策略 + 断言 trace**。  
建议把 Node 与 Browser 形态分别跑一遍（至少跑 hard invariants 的关键子集）。

**事件与落盘**
- [ ] `offline_events_jsonl_roundtrip_unicode`
- [ ] `offline_events_no_delta_persistence`
- [ ] `offline_events_call_id_bijection`
- [ ] `offline_events_required_fields_strict`
- [ ] `offline_events_redaction_no_secrets`
- [ ] `offline_events_unknown_fields_forward_compat`
- [ ] `offline_events_undefined_vs_null_semantics`
- [ ] `offline_events_control_chars_do_not_break_jsonl`

**runtime/tool loop**
- [ ] `offline_loop_zero_tool_calls`
- [ ] `offline_loop_single_tool_call_success`
- [ ] `offline_loop_multi_tool_calls_serial`
- [ ] `offline_loop_tool_throws_is_recorded`
- [ ] `offline_loop_tool_returns_non_json_is_supported`
- [ ] `offline_loop_max_tool_calls_fuse`
- [ ] `offline_loop_abort_mid_run_no_partial_jsonl`
- [ ] `offline_loop_timeout_provider_vs_tool_classification`
- [ ] `offline_loop_unhandled_rejection_becomes_error_event`

**tools/plumbing**
- [ ] `offline_tool_args_missing_field`
- [ ] `offline_tool_args_wrong_type`
- [ ] `offline_tool_args_unknown_properties`
- [ ] `offline_tool_args_json_string_instead_of_object`
- [ ] `offline_tool_output_large_payload_truncate_or_summarize`
- [ ] `offline_allowed_tools_enforced_across_turns`
- [ ] `offline_tool_registry_duplicate_name_policy`（如支持注册）

**permission gate**
- [ ] `offline_permission_allow_all`
- [ ] `offline_permission_deny_records_reason`
- [ ] `offline_permission_prompt_no_answerer_fails_fast`
- [ ] `offline_permission_prompt_answerer_happy_path`
- [ ] `offline_permission_default_deny_on_parse_error`
- [ ] `offline_permission_scope_precedence`

**hooks**
- [ ] `offline_hooks_before_model_call_mutates_messages`
- [ ] `offline_hooks_pre_tool_use_mutates_args`
- [ ] `offline_hooks_order_is_stable`
- [ ] `offline_hooks_exception_is_isolated`
- [ ] `offline_hooks_cannot_bypass_permissions`

**sessions/resume**
- [ ] `offline_session_custom_home_dir`（Node）
- [ ] `offline_session_truncated_line_recovery_policy`
- [ ] `offline_session_resume_without_replaying_side_effect_tool`
- [ ] `offline_session_node_fs_symlink_escape_blocked`（安全）
- [ ] `offline_session_browser_idb_roundtrip`（Browser）

**compaction（如有）**
- [ ] `offline_compaction_trigger_and_records_event`
- [ ] `offline_compaction_preserves_permissions_and_allowed_tools`
- [ ] `offline_compaction_failure_fallback`

**provider（离线模拟）**
- [ ] `offline_provider_rate_limit_backoff_uses_fake_clock`
- [ ] `offline_provider_invalid_json_response_is_handled`
- [ ] `offline_provider_stream_parse_half_packet`（如有 SSE）

**安全**
- [ ] `offline_security_path_traversal_blocked`
- [ ] `offline_security_ssrf_blocked_default`（如有网络工具）
- [ ] `offline_security_secrets_not_in_trace_or_log`
- [ ] `offline_security_prototype_pollution_blocked`

### 4.2 套件划分建议（避免越写越乱）

- [ ] `offline_smoke`：最小闭环（10～15 个），每次 PR 必跑，目标 <1 分钟。
- [ ] `offline_hard_invariants`：完整硬不变量（25～120 个），每次 PR 必跑。
- [ ] `offline_browser_smoke`（如支持 Browser）：只跑最关键的 10～20 个 hard invariants，防止平台漂移。
- [ ] `online_contract`：provider 适配/网络错误分类（可 nightly 或手动）。
- [ ] `stochastic_flows`：模型规划体验流（多次运行 + pass-rate，nightly/手动）。

---

## 5. 评审者用 Checklist（给 TypeScript 同学 Code Review）

- [ ] hard invariants 是否真的不依赖网络/真实 LLM/真实时间？
- [ ] 断言是否主要基于 trace/tool.result/落盘，而不是最终自然语言？
- [ ] Node/Browser 两形态的 session/resume 语义是否分别覆盖且一致？
- [ ] permission/allowed_tools 是否默认安全、拒绝可解释？
- [ ] hooks/tool plumbing 是否覆盖缺字段/类型错/超大输出/异常？
- [ ] 是否有追溯矩阵门禁防止套件失控？
- [ ] `undefined`/`null`/缺字段的语义是否被钉死并有 golden trace 约束？

---

## 6. 附录：单个离线用例的“模板断言清单”

### 6.1 Given / When / Then 模板（建议）

- **Given**
  - 固定 fake timers 与固定 seed（若有随机）。
  - `TempSessionDir`：Node 写临时目录；Browser 用临时存储（或内存）并可导出 JSONL。
  - 固定工具集合（标准 `ToolTestDoubles`）。
  - 固定 permission 策略（allow/deny/prompt + 固定回答器）。
  - 固定 hooks（如用到）。
  - 固定 `ScriptedProvider` 脚本。
- **When**
  - 运行一次 query/run（建议只跑一轮）。
- **Then**
  - 断言返回值/状态。
  - 断言 trace（事件序列）与落盘内容。

### 6.2 每个用例建议包含的 trace 断言（最小集）

- [ ] 有且只有一个 `session_id`。
- [ ] 每个 `tool_use`：`call_id` 唯一；tool name/args 可解释。
- [ ] 每个 `tool_result`：能关联 `call_id`；成功/失败状态明确。
- [ ] 不出现任何 `*_delta`（禁止落盘分片）。
- [ ] trace/log 不包含 secrets。
- [ ] 基本因果成立（tool_use 在 tool_result 之前，或具备可恢复语义）。
- [ ] `undefined` 不应被“悄悄转成缺字段/转成 null”而改变语义（normalizer/strict 策略必须明确且可测）。

### 6.3 建议的失败消息规范

- [ ] 输出：`session_id`、`call_id`、事件索引/seq、事件最小 JSON 摘要。
- [ ] 对“缺字段/类型错/未知事件”给出明确提示。

---

## 7. 附录：高级测试（强烈建议，但不必一开始做全）

- [ ] fuzz tool arguments / events.jsonl（随机 JSON、截断、非法 JSON、超大行、控制字符）确保不 crash 且诊断清晰。
- [ ] chaos cancellation（随机时刻 abort）确保不写半行 JSON、资源回收、无未处理 promise 拒绝。
- [ ] metamorphic（字段顺序/空白变化）不改变硬语义。

---

## 8. 附录：TypeScript/JS 生态高频坑与必测点

- [ ] **大整数精度**：JS number 会丢精度；协议里出现大整数时必须定义策略（字符串化/BigInt/禁止），并写用例钉死。
- [ ] **`undefined` 丢失**：JSON 序列化会丢 `undefined`；必须通过 strict/normalizer 明确定义缺字段语义并测试。
- [ ] **未处理的 Promise rejection**：在 Node/Browser 中可能导致进程退出或静默；hard invariants 必须把它变成可解释错误事件。
- [ ] **AbortController 语义不一致**：不同 runtime/fetch 实现对 abort 的错误类型/时序不同；必须抽象并统一分类。
- [ ] **ESM/CJS 与打包差异**：导入路径、条件导出、tree-shaking 可能改变副作用时序；至少对“初始化不产生副作用/不写文件/不发网络请求”写用例。
- [ ] **跨平台路径**：Windows 盘符/UNC、大小写不敏感、符号链接；路径穿越防护必须覆盖。
- [ ] **日志泄露 secrets**：debug 日志输出 headers/token；测试断言 trace/log 不含敏感字段。
