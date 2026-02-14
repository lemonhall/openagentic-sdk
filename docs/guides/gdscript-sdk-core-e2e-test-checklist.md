# GDScript SDK（核心模块 / 不含 CLI）E2E 测试 Checklist

面向：正在把 `openagentic-sdk` 的核心能力移植到 Godot/GDScript（插件或内嵌 SDK）的同学。  
目标：把“SDK 回归”与“模型随机性/网络波动”拆开，用一套**离线、确定性、可追溯**的 E2E 把核心模块的硬不变量钉死。

> 约定：本文不覆盖 CLI；这里的“SDK”指在 Godot 工程内运行的核心模块：runtime/tool loop、tools、permissions、hooks、sessions/resume、provider 适配层，以及（如有）skills/commands/project 兼容层。

---

## 0. 成功标准（强烈建议）

- **离线硬不变量套件**（offline hard invariants）：
  - 必须 **100% 通过**，失败基本等价于“SDK 回归/协议破坏”。
  - 必须可在 CI **每次 PR** 自动跑（建议用 headless Godot 运行测试）。
  - 不依赖真实网络、不依赖真实 LLM、不依赖人类交互、不依赖编辑器 UI。
  - **零 flake（不抖动）**：同样输入多跑一致；不依赖帧率/计时器/调度顺序。
  - **失败可解释**：能定位到哪个硬不变量被破坏。
  - **断言以 trace 为主**：用事件/落盘做断言，而不是最终自然语言。
- **在线/随机性套件**（online / stochastic flows）：
  - 可 nightly/手动/阈值门禁（pass-rate）。
  - 失败更多是外部变化，不应掩盖 SDK 回归。

### 0.1 非目标（避免误测）

- 不测编辑器 UI 与交互（面板、Dock、Inspector、输入法等）。
- 不把“模型是否会规划工具/写得好”当硬门禁（除非愿意承担随机性）。
- 不把“渲染帧/物理帧”相关不确定性引入 hard invariants。

### 0.2 支持目标（建议显式声明，否则很难写“无遗漏”的用例）

在写测试清单与 suite 之前，建议先在仓库里明确你们要支持什么（不支持的就直接写“不支持”，避免隐式承诺）：

- [ ] **Godot 版本**：例如仅支持 Godot 4.2/4.3（不同版本的 HTTP/文件/线程细节可能不完全一致）。
- [ ] **运行形态**：
  - [ ] 作为 Godot 插件（EditorPlugin）使用
  - [ ] 作为游戏/应用运行时内嵌 SDK（runtime-only）
- [ ] **导出目标**（强烈建议逐项写清）：
  - [ ] Desktop：Windows / macOS / Linux
  - [ ] Mobile：Android / iOS
  - [ ] Web：HTML5/Web（IndexedDB、CORS、限制更多）
- [ ] **持久化介质**：
  - [ ] 文件系统（`user://`）
  - [ ] Web 导出（IndexedDB/虚拟 FS）
  - [ ] 纯内存（不落盘）
- [ ] **网络能力**（若 SDK 提供在线 provider）：
  - [ ] 允许直连互联网
  - [ ] 允许配置代理
  - [ ] Web 导出是否需要走同源/后端代理（CORS）

---

## 1. 测试分层建议（套件结构）

### A) Offline Hard Invariants（必做）

核心思路：提供一个 `ScriptedProvider`（或等价回放 provider），按脚本返回 tool calls 与最终文本。  
断言重点放在：事件序列、权限门、落盘与恢复、hooks、工具协议边界。

### B) Online Contract（可选但很有价值）

只测 provider 适配/网络错误分类/响应解析，不测模型质量。  
建议用本地 stub server 或 Godot 的 `HTTPServer`（如有）/自建简单服务。

### C) Stochastic Model-Driven Flows（可选）

只测体验流：多次运行 + pass-rate + 失败归因报告落盘。

---

## 2. 必备测试基础设施（GDScript 侧建议先做）

### 2.1 ScriptedProvider（离线确定性）

Checklist：
- [ ] 支持按脚本输出 `tool_calls`（name + arguments）与最终文本。
- [ ] 支持多轮脚本：第 N 轮输出按轮次或按输入历史决定。
- [ ] 支持模拟 provider 错误：timeout、rate limit、非 2xx、响应字段缺失/变形。
- [ ] 支持流式与非流式两条路径（流式不应落盘 delta）。
- [ ] 支持脚本断言：能断言 runtime 发送给 provider 的输入（messages/system/tool schemas）符合预期。
- [ ] 支持确定性调度：测试中不依赖真实计时器/帧推进。

> Godot 提示：尽量避免在 hard-invariant 测试里依赖 `await get_tree().create_timer(...)` 的真实时间；建议注入 fake clock 或改成显式推进。

### 2.2 Golden Trace（关键事件对齐 / 追溯）

建议产物：
- `events.jsonl`（或等价）：每行一个 JSON 事件（推荐 JSONL，因为可增量写入、崩溃后更易恢复）。
- 规范化比较器：忽略 timestamp 等噪声字段，严格比较关键语义字段与关联关系。

Checklist：
- [ ] 允许新增字段但不允许删除/改名核心字段（兼容策略明确且可测）。
- [ ] 未知事件类型/字段不导致崩溃（安全忽略或透传）。
- [ ] 有严格模式（hard invariants 使用）：缺字段即失败、关键语义漂移即失败。
- [ ] tool.use/tool.result 可关联（call_id 或等价字段）。
- [ ] 禁止落盘任何 streaming delta（`*_delta`）。

> GDScript 提示：Godot 的 `Dictionary` key 顺序不稳定；断言必须基于“解析后结构”的 canonicalization，而非字符串化后的原始 JSON key 顺序。

### 2.3 最小追溯门禁（防止套件失控）

- [ ] 文档里维护 traceability matrix（suite → module/invariant）。
- [ ] CI 脚本检查 suite 清单与文档矩阵一致（缺失/重复/引用不存在即 fail）。
- [ ] suite 标签分层（offline/online/stochastic），决定 CI 触发频率。

### 2.4 最小测试夹具（强烈建议）

- [ ] `FakeClock`：可控时间（或至少可控“推进步数/轮次”）。
- [ ] `TempSessionDir`：测试写入 `OS.get_user_data_dir()` 下的临时子目录，或使用 CI 提供的 temp。
- [ ] `EventAsserts`：统一断言（事件序列、关联关系、脱敏、禁止 delta 等）。
- [ ] `ToolTestDoubles`：成功/失败/慢/大输出/非 JSON 输出/副作用工具。
- [ ] `NetworkStubs`：替换 HTTP 请求层（例如包装 `HTTPRequest`/`HTTPClient` 以便 stub）。
- [ ] `JsonCanonicalizer`：对 `Dictionary`/`Array` 做 canonicalization（排序 key、规范化缺字段语义），避免 key 顺序导致抖动。
- [ ] `MainThreadAsserts`：断言“只能主线程调用的 Godot API”没有在子线程被误用（否则经常是随机崩）。
- [ ] `DeterministicRunner`：把“多轮对话/多 tool call”的推进变成显式 step（不要依赖帧/Timer）。
- [ ] `FileIoHelpers`：封装 JSONL 的原子写入/flush/读取坏行诊断（避免每个用例自己造轮子）。
- [ ] `RedactionAsserts`：统一断言 trace/log 不包含敏感字段（token/密钥/cookie）。

---

## 3. 核心模块 E2E Checklist（离线硬不变量优先）

### 3.1 事件协议（trace/events）硬不变量

- [ ] JSONL 行协议：每行一个 JSON；换行/特殊字符不破坏行边界。
- [ ] 事件类型稳定：user/assistant/tool.use/tool.result/hook/compaction（按实现）。
- [ ] tool.use/result 可关联：`call_id` 必须存在且唯一；并发/乱序可还原因果。
- [ ] 禁止落盘 streaming delta：任何 `*_delta` 或等价分片事件不得持久化。
- [ ] 未知字段容忍：新增字段不崩溃；策略明确（忽略/透传）。
- [ ] 错误事件结构化：错误有 type/message/optional stack/optional code。
- [ ] 尺寸/上限：单事件大小有截断/摘要/拒绝策略且可测。
- [ ] 敏感信息脱敏：trace 中不出现 token/密钥/cookie。
- [ ] Unicode round-trip：中文/emoji/组合字符可恢复。
- [ ] `null` vs 缺字段：在 Godot JSON/Dictionary 里表现不同；必须写 hard-invariant 钉死语义（尤其是“字段缺失是否等价于 null”）。
- [ ] 数字语义：整数/浮点/超大数字（被转成 float 导致精度丢失）如何处理必须明确且可测。
- [ ] 事件顺序语义：至少 `tool_use` 在对应 `tool_result` 之前（或有 `seq`/时间戳/索引能恢复因果）。
- [ ] 事件幂等：重试/恢复路径不应重复写入同一语义事件（或必须可去重）。
- [ ] 可诊断性：坏行/截断行时，读取器能给出“第几行坏了”的可解释输出。
- [ ] 兼容性：旧版本写出的 events，新版本可读；新版本新增字段旧版本至少能跳过而不崩溃。

### 3.2 Runtime 核心循环（query loop / tool loop）

- [ ] 0 工具调用：直接最终文本，loop 正常结束并落盘。
- [ ] 1 工具调用：tool.use → tool.result → 最终文本；顺序与关联正确。
- [ ] 多工具串行：A→B→C；失败策略（继续/终止）明确可测。
- [ ] 工具返回非 JSON：仍可落盘与回放。
- [ ] 中断/取消：不会写出半行 JSON；有可解释中断证据（如记录）。
- [ ] 超时：provider vs tool 超时分类准确，策略可测。
- [ ] 最大步数/熔断：防止无限 tool call。
- [ ] 异常边界：未捕获异常不应“无记录地”把会话打死。
- [ ] backpressure：工具输出/事件写入很快很大时，不应无限堆内存（要么限流、要么截断、要么拒绝）。
- [ ] re-entrancy：tool 执行过程中再次触发 query（若允许）有明确策略；若不允许，能安全拒绝并落事件。
- [ ] 主线程边界：涉及 Godot 主线程 API 的路径，runtime 不应在子线程触发（或明确全部在主线程）。
- [ ] 资源回收：会话结束后不遗留 `Thread`/`WorkerThreadPool` 任务；失败/取消后也能收敛。
- [ ] deterministic stepping：相同脚本在不同机器/不同帧率下行为一致（不依赖 `delta`、不依赖 Timer 实时）。

### 3.3 Tools 协议与边界（tool plumbing）

- [ ] 参数校验：缺字段/类型错/超长/深层嵌套不 crash。
- [ ] unknown tool：按策略拒绝并落盘可解释错误。
- [ ] 大输出：截断/摘要可测，不写爆磁盘。
- [ ] 工具异常：tool.result 结构化落盘；loop 按策略继续/终止。
- [ ] allowed_tools：allow-list 生效且默认安全；跨轮/compaction 后不丢。
- [ ] 参数容错：arguments 为 JSON 字符串、类型被转成字符串、额外字段等场景有覆盖。
- [ ] 副作用工具：resume 不重放（或明确重放策略 + 幂等 key）。
- [ ] 工具名匹配：大小写/别名策略明确（避免不同平台/脚本写法导致“同名不同 tool”）。
- [ ] schema 演进：工具 schema 新增字段/默认值变更不破坏旧脚本（或明确版本门禁）。
- [ ] 输出类型覆盖：结构化 JSON、纯文本；若支持二进制则必须 base64/mime/size limit，并写用例钉死。
- [ ] tool 超时：单个 tool 执行过慢的处理策略明确（超时→取消→结果事件）。
- [ ] 工具隔离：一个工具失败不会污染其他工具上下文（避免共享全局可变状态）。
- [ ] 工具写文件类能力：路径必须 canonicalize，禁止目录穿越；符号链接/快捷方式逃逸必须覆盖。

### 3.4 Permission Gate（权限门）

- [ ] allow：正常执行，事件完整。
- [ ] deny：不执行；拒绝原因/策略来源写入事件。
- [ ] prompt：有回答器继续；无回答器不死等（快速失败）。
- [ ] 安全默认：未知策略/解析失败不默认放行。
- [ ] 策略作用域优先级：全局/会话/单次明确可测。
- [ ] 决策可审计：每次 allow/deny 都有足够证据（匹配的规则 id、理由、触发点）。
- [ ] 拒绝后行为：deny 后是继续、返回错误、还是要求模型改计划？必须明确并写用例。
- [ ] 缓存与会话作用域（如有）：一次允许是否能自动扩展到后续调用？默认应最小授权并可测。
- [ ] prompt 输入边界：回答为空/超长/包含控制字符/包含 JSON 时，行为明确且不崩溃。

### 3.5 Hooks（可插拔改写/拦截）

- [ ] 触发点覆盖：Before/AfterModelCall、Pre/PostToolUse、UserPromptSubmit（按实现）。
- [ ] 改写生效：改写 messages/tool args 后，provider 输入与 tool.use 记录符合预期。
- [ ] hook 异常隔离：hook 报错有证据、不会 silent fail。
- [ ] hook 不能越权：hook 改写也必须过 permission/allowed_tools。
- [ ] hook 顺序：多个 hook 的执行顺序固定且可配置，并可测。
- [ ] hook 幂等：同一事件因重试/恢复可能重复触发时，hook 行为仍安全（或明确不支持）。
- [ ] hook 并发安全：并发 session 下 hook 状态不串（建议避免共享可变全局）。
- [ ] hook 性能：hook 过慢不会拖死会话（至少可取消/可超时）。

### 3.6 Sessions / Resume（持久化与恢复）

- [ ] 落盘目录：默认 + 自定义目录都可用。
- [ ] 写入原子性：崩溃后已写入行可读；截断/坏行策略明确可测。
- [ ] resume 一致性：恢复后语义一致（允许 timestamp 噪声不同）。
- [ ] 不重放副作用：恢复不重复执行已执行工具（除非明确设计重放）。
- [ ] 并发写：明确支持或明确拒绝；拒绝时错误清晰。
- [ ] iOS/Android/桌面平台差异（若导出）：路径、权限、可写目录差异不破坏语义。
- [ ] Web 导出：`user://` 可能落到 IndexedDB/虚拟 FS；写入失败/容量限制/清理策略必须可测。
- [ ] flush 策略：关键事件是否 flush（至少在测试中能观察到“写到第 N 行就崩溃时的边界”）。
- [ ] 只读恢复（推荐）：resume 支持只读模式，避免覆盖原 trace。
- [ ] 多 session 隔离：两个 session id 不串；同一 session 多次 run 的追加语义明确。
- [ ] 升级/迁移：旧 trace 恢复到新版本时，未知事件/字段策略明确（忽略/报错/诊断）。

### 3.7 Compaction（如有）

- [ ] 可控触发：阈值可配置，测试可强制触发。
- [ ] 硬约束不丢：permissions/allowed_tools/安全提示词约束不丢。
- [ ] 可解释事件：记录原因、范围、输出摘要。
- [ ] 失败回退：compaction 失败不破坏会话。
- [ ] tool 证据链：compaction 后仍保留最小证据链（至少能解释“执行过哪些工具、结果摘要是什么”）。
- [ ] compaction 不变量：compaction 前后 permissions/allowed_tools/session_id/tool registry 等核心状态不漂移。

### 3.8 Provider 适配

- [ ] ScriptedProvider 一等公民：离线不依赖网络。
- [ ] 错误分类：鉴权/限流/超时/连接失败/响应变形都有覆盖。
- [ ] 流式解析（如有）：半包/粘包/非法 JSON 下不写坏 session。
- [ ] 重试/backoff：可注入 fake clock，不让测试变慢。
- [ ] Godot HTTP 层差异：`HTTPRequest` vs `HTTPClient`（若两条路径都支持）各自的错误分类一致且可测。
- [ ] TLS/证书错误：可分类并可解释（不要一律“网络失败”）。
- [ ] 代理（如支持）：设置/不设置代理时行为明确；错误可诊断。
- [ ] Web 导出限制：CORS、同源、SSE 支持度差异；需要后端代理时必须在文档与测试里体现。
- [ ] request_id/trace 关联：若 provider 返回 request id，写入 trace（脱敏后）便于排障。

### 3.9 配置与跨平台一致性（Godot/GDScript 常见坑）

- [ ] `null` vs 缺字段：JSON.parse 返回 `null` 与缺字段语义差异要在测试里钉死。
- [ ] CRLF/LF：文本与 JSONL 在 Windows/Unix 下可解析。
- [ ] 沙箱路径：写文件只能在允许根目录内；canonical path 校验（含符号链接/快捷方式）。
- [ ] 线程与信号：如果用 Thread/WorkerThreadPool，必须有并发 smoke，避免竞态。
- [ ] ProjectSettings/导出配置：关键配置来自 ProjectSettings/环境变量/代码默认值的优先级固定且可测。
- [ ] 资源路径（`res://`）与用户路径（`user://`）混用：必须明确哪些写入只能发生在 `user://`。
- [ ] Web 导出：文件 API 与权限不同；所有“写文件工具/落盘”必须有降级或明确不支持。
- [ ] Android/iOS：后台/前台切换、应用被系统杀死后恢复边界明确（至少写一条恢复语义用例）。

### 3.10 安全（默认不越权）

- [ ] 默认拒绝高风险工具（写文件/网络/执行命令等）除非明确 allow。
- [ ] secrets 不落盘：trace/log 不包含 token/密钥。
- [ ] SSRF（如有网络工具）：默认禁止访问内网/metadata；策略可测。
- [ ] 控制字符/日志注入：工具输出含控制字符不破坏 JSONL。
- [ ] 目录穿越：`../`、绝对路径、符号链接逃逸都不能突破 sandbox 根。
- [ ] Web 导出：禁止访问 `localhost`/内网段（若你们把网络工具暴露给模型），避免“浏览器侧 SSRF/内网探测”。
- [ ] 最小披露：错误信息不包含敏感路径/密钥；内部 trace 也必须脱敏。

### 3.11 可观测性与诊断

- [ ] 失败能从 trace 定位到：tool/call_id、权限策略、hook、provider 请求。
- [ ] 指标/计数（如有）可断言：tool 次数、拒绝次数、重试次数、compaction 次数。

### 3.12 并发与多会话（至少一组 smoke）

- [ ] 两个 session 并发跑：trace 不串、工具结果不串、权限不串、hook 状态不串。

### 3.13 对齐 Python 参考实现（推荐）

- [ ] 同脚本/同配置：关键事件集合一致（允许噪声字段不同）。
- [ ] permission/allowed_tools 决策一致或可映射。
- [ ] resume 不重放副作用语义一致。

### 3.14 Skills / Commands / Project 兼容（如要做功能对齐）

- [ ] 发现与加载：从工程目录发现 `SKILL.md`/commands；不存在时行为明确。
- [ ] 解析鲁棒：空文件/非法 front matter 不 crash。
- [ ] 安全边界：加载不越界读取路径；不得绕过 permissions/allowed_tools。
- [ ] 可追溯：trace 中能定位 skill/command 来源（路径/名称/hash）。

### 3.15 测试运行方式（建议也覆盖成“可验证”的用例/脚本）

- [ ] headless 运行：能在无图形界面下跑完 offline hard invariants（CI 友好）。
- [ ] 最小日志：失败时输出可读的“用例名 + session_id + call_id + 事件索引/摘要”。
- [ ] 清理策略：每次用例结束清理临时目录（或失败时保留并打印路径用于排障）。
- [ ] 与编辑器隔离：hard invariants 不依赖 editor-only API（否则 CI/headless 容易挂）。

---

## 4. 落地执行顺序（建议）

1) `ScriptedProvider` + session store + permission gate 最小闭环（3～5 用例）。
2) 把 3.1～3.6 的硬不变量填到 25～40 个离线用例（每个用例断言 trace）。
3) 加追溯矩阵门禁脚本。
4) 再做 online/stochastic（nightly/手动 + pass-rate）。

### 4.1 建议的离线用例“目录”（可直接抄成 40～80 个）

每个用例尽量做到：**固定脚本 + 固定工具 + 固定权限策略 + 断言 trace**。  
Godot 侧建议：用 headless 运行测试（避免 UI/帧率抖动），并确保每个用例不会依赖真实计时器。

**事件与落盘**
- [ ] `offline_events_jsonl_roundtrip_unicode`
- [ ] `offline_events_no_delta_persistence`
- [ ] `offline_events_call_id_bijection`
- [ ] `offline_events_required_fields_strict`
- [ ] `offline_events_redaction_no_secrets`
- [ ] `offline_events_unknown_fields_forward_compat`
- [ ] `offline_events_control_chars_do_not_break_jsonl`

**runtime/tool loop**
- [ ] `offline_loop_zero_tool_calls`
- [ ] `offline_loop_single_tool_call_success`
- [ ] `offline_loop_multi_tool_calls_serial`
- [ ] `offline_loop_tool_raises_error_is_recorded`
- [ ] `offline_loop_tool_returns_non_json_is_supported`
- [ ] `offline_loop_max_tool_calls_fuse`
- [ ] `offline_loop_cancel_mid_run_no_partial_jsonl`
- [ ] `offline_loop_timeout_provider_vs_tool_classification`

**tools/plumbing**
- [ ] `offline_tool_args_missing_field`
- [ ] `offline_tool_args_wrong_type`
- [ ] `offline_tool_args_unknown_properties`
- [ ] `offline_tool_args_json_string_instead_of_object`
- [ ] `offline_tool_output_large_payload_truncate_or_summarize`
- [ ] `offline_allowed_tools_enforced_across_turns`

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
- [ ] `offline_session_custom_home_dir`
- [ ] `offline_session_truncated_line_recovery_policy`
- [ ] `offline_session_resume_without_replaying_side_effect_tool`
- [ ] `offline_session_unicode_paths`
- [ ] `offline_session_concurrent_sessions_isolation`（如支持并发）

**compaction（如有）**
- [ ] `offline_compaction_trigger_and_records_event`
- [ ] `offline_compaction_preserves_permissions_and_allowed_tools`
- [ ] `offline_compaction_failure_fallback`

**provider（离线模拟）**
- [ ] `offline_provider_rate_limit_backoff_uses_fake_clock`
- [ ] `offline_provider_invalid_json_response_is_handled`
- [ ] `offline_provider_stream_parse_half_packet`（如有流式）

**安全**
- [ ] `offline_security_path_traversal_blocked`
- [ ] `offline_security_symlink_escape_blocked`
- [ ] `offline_security_ssrf_blocked_default`（如有网络工具）
- [ ] `offline_security_secrets_not_in_trace_or_log`
- [ ] `offline_security_web_export_no_localhost_access`（如有网络工具）

### 4.2 套件划分建议（避免越写越乱）

- [ ] `offline_smoke`：最小闭环（10～15 个），每次 PR 必跑，<1 分钟。
- [ ] `offline_hard_invariants`：完整硬不变量（25～80 个），每次 PR 必跑。
- [ ] `online_contract`：provider 适配/网络错误分类（可 nightly 或手动）。
- [ ] `stochastic_flows`：模型规划体验流（多次运行 + pass-rate，nightly/手动）。

---

## 5. 评审者用 Checklist（给 GDScript 同学 Code Review）

- [ ] hard invariants 是否真的不依赖网络/真实 LLM/帧率？
- [ ] 断言是否主要基于 trace/tool.result/落盘，而不是最终自然语言？
- [ ] session/resume 是否覆盖截断/坏行/中断与“不重放副作用”？
- [ ] permission/allowed_tools 是否默认安全、拒绝可解释？
- [ ] hooks/tool plumbing 是否覆盖缺字段/类型错/超大输出/异常？
- [ ] 是否有追溯矩阵门禁防止套件失控？

---

## 6. 附录：单个离线用例的“模板断言清单”

建议每个离线 hard-invariant 用例按下面模板组织，保证“可读、可复用、可定位”。

### 6.1 Given / When / Then 模板（建议）

- **Given**
  - 固定 fake clock（或固定推进步数/轮次），避免真实 `Timer`。
  - `TempSessionDir`：会话根目录在临时路径（确保测试结束清理）。
  - 固定工具集合（尽量使用标准 `ToolTestDoubles`）。
  - 固定 permission 策略（allow/deny/prompt + 固定回答器）。
  - 固定 hooks（如用到）。
  - 固定 `ScriptedProvider` 脚本。
- **When**
  - 运行一次 query/run（建议只跑一轮）。
- **Then**
  - 断言返回值/状态。
  - 断言 trace（事件序列）与落盘文件内容。

### 6.2 每个用例建议包含的 trace 断言（最小集）

- [ ] 有且只有一个 `session_id`。
- [ ] `tool_use`：`call_id` 存在且唯一；tool name/args 可解释。
- [ ] `tool_result`：能关联到 `call_id`；成功/失败状态明确。
- [ ] 不出现任何 `*_delta`（禁止落盘分片）。
- [ ] trace/log 不包含 secrets。
- [ ] 基本因果成立（tool_use 在 tool_result 之前，或具备可恢复语义）。

### 6.3 建议的失败消息规范

- [ ] 输出：`session_id`、`call_id`、事件索引/seq、以及对应事件的最小 JSON 摘要。
- [ ] 对“缺字段/类型错/未知事件”给出明确提示。

---

## 7. 附录：高级测试（强烈建议，但不必一开始做全）

- [ ] fuzz tool arguments / events.jsonl（随机 JSON、截断、非法 JSON、超大行、控制字符）确保不 crash 且诊断清晰。
- [ ] chaos cancellation（随机时刻取消）确保不写半行 JSON、资源回收、不泄漏线程。
- [ ] metamorphic（字段顺序/空白变化）不改变硬语义。

---

## 8. 附录：Godot/GDScript 生态高频坑与必测点

- [ ] **`await` + 取消**：GDScript `await` 没有“默认取消传播”概念时，容易出现“取消了但还在继续跑”；必须用例覆盖并定义语义。
- [ ] **线程与主线程限制**：很多 Godot API 只能主线程调用；tools/hook 若误用线程，会出现隐性崩溃或挂起。
- [ ] **Dictionary 顺序不稳定**：不要把 JSON 字符串化后的 key 顺序当断言依据；必须 canonicalize。
- [ ] **文件系统与导出平台差异**：iOS/Android/HTML5 导出时可写目录、权限、路径分隔符不同；session store 语义必须钉死。
- [ ] **HTTPClient/HTTPRequest 行为差异**：重定向、TLS、代理、超时、错误码分类容易被吞；contract 测试要覆盖。
- [ ] **日志泄露 secrets**：debug 输出 headers/token；测试必须断言 trace/log 不含敏感字段。
