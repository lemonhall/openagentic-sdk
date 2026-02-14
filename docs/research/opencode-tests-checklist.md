# opencode（源头项目）核心测试套件清单（供 openagentic-sdk 对齐）

> 源头项目：`E:\development\opencode`  
> 评审范围：按 `openagentic-sdk` 根 `AGENTS.md` 所定义的 **核心模块**（Runtime Core / Tools / Skills&Commands / Hooks / Permissions(HITL) / Sessions&Resume）抽取与归类源头项目的测试用例。  
> 目标产物：一份“可直接照抄成 Python unittest”的 **测试清单**，用于指导 `openagentic-sdk` 后续补齐/对齐测试套件。

---

## 1) Runtime Core（对话/工具循环的基础能力）

### 1.1 Agent/模式/默认权限（强相关：PermissionGate + Tool loop）

源头测试文件：`packages/opencode/test/agent/agent.test.ts`

建议清单（P0 优先）：

- [ ] 默认 agent 列表存在且稳定（无配置时返回内置 agents）
- [ ] `build/plan/explore/general/compaction` 等默认 agent 的权限与属性符合预期（尤其是写/编辑/patch/todo/tool 的 deny/ask/allow）
- [ ] 自定义 agent 可新增；自定义配置可覆盖内置 agent 属性
- [ ] 支持禁用 agent；禁用后不出现在可选列表
- [ ] agent 级 permission 与全局 permission 的合并策略正确（合并顺序/覆盖规则/“最后匹配 wins”一致）
- [ ] `default_agent` 选择逻辑正确：指向子 agent/隐藏 agent/不存在 agent 时抛错
- [ ] “外部目录白名单”与 `Truncate.GLOB` 这类特殊 pattern 的例外策略可被测试锁定（避免回归）

### 1.2 Scheduler 作用域（全局/实例）

源头测试文件：`packages/opencode/test/scheduler.test.ts`

建议清单（P1）：

- [ ] 默认按目录 Instance scope：同目录多次实例化不重复执行一次性任务
- [ ] Global scope：跨实例只执行一次（并验证线程/并发安全）

### 1.3 Abort/资源泄漏（稳定性）

源头测试文件：`packages/opencode/test/memory/abort-leak.test.ts`

建议清单（P1）：

- [ ] WebFetch/网络类工具在大量调用下不泄漏（至少对“闭包捕获 vs bind”这类常见泄漏模式有回归测试）

---

## 2) Tools（工具系统：schema/执行/截断/安全）

### 2.1 Tool Registry（自定义工具加载）

源头测试文件：`packages/opencode/test/tool/registry.test.ts`

建议清单（P0）：

- [ ] 支持从项目内的工具目录加载（源头：`.opencode/tool` 与 `.opencode/tools` 两种路径）；对齐到本项目的工具加载约定（如 `.claude/` 兼容层/本地 tools 目录）
- [ ] 自定义工具在存在外部依赖（`package.json`）时不会导致加载崩溃（Python 对应：第三方依赖导入失败时的隔离/错误提示）

### 2.2 Read Tool（读文件/读目录/附件/截断 + external_directory 权限）

源头测试文件：`packages/opencode/test/tool/read.test.ts`

建议清单（P0）：

- [ ] 允许读取：项目目录内绝对路径、子目录文件
- [ ] 读取项目外绝对路径/`../` 相对逃逸时，必须触发 `external_directory` 权限询问（并验证 pattern 粒度：文件 vs 目录 `*`）
- [ ] 读取项目内文件/目录时不触发 external_directory
- [ ] 大文件截断：按 bytes 截断并标记 `truncated=true`；按 lines(limit) 截断；小文件不截断
- [ ] offset 参数：正确偏移；offset 越界报错且信息包含“范围/行数”
- [ ] 目录分页：最后一页不应标记 truncated；输出不应误报“Showing N of M”
- [ ] 超长单行截断（避免极端长行导致输出爆炸）
- [ ] 图片读取：以附件形式返回且 `truncated=false`（含“大图片 fixture”）
- [ ] `.fbs`（FlatBuffers schema）应按文本读取，不应被当成图片
- [ ] 指令加载：读取子目录文件时会加载最近的 `AGENTS.md`（并在 metadata 标注 loaded 路径）

### 2.3 Grep/Ripgrep Tool（跨平台行尾与输出规范）

源头测试文件：`packages/opencode/test/tool/grep.test.ts`、`packages/opencode/test/file/ripgrep.test.ts`

建议清单（P0/P1）：

- [ ] 基础搜索：命中行/文件路径/行号格式稳定
- [ ] 无匹配时输出明确且不报错
- [ ] CRLF/Unix/Mixed 行尾：输出解析与分行逻辑一致（Windows/WSL2 兼容）
- [ ] hidden 参数行为：默认包含 hidden；显式关闭则排除 hidden（源头：`ripgrep.test.ts`）

### 2.4 Bash/Shell Tool（权限模式 + external_directory + 截断落盘）

源头测试文件：`packages/opencode/test/tool/bash.test.ts`

建议清单（P0）：

- [ ] 基础命令执行成功，stdout/stderr 与退出码被正确采集
- [ ] 生成的 permission pattern 正确：单命令、多命令、包含重定向符号等
- [ ] `cd ..`/workdir 项目外/文件参数项目外：触发 external_directory 权限
- [ ] 项目内 `rm` 等操作不应误触发 external_directory（但仍应触发“危险操作”权限/确认策略——按本项目设计）
- [ ] always patterns（自动批准白名单）生成规则稳定：空格+通配符的边界行为被测试锁定
- [ ] 仅 `cd` 时不应要求 bash permission（源头行为）
- [ ] 输出截断：超行/超字节会截断，并将完整输出落盘到文件（并返回落盘位置）

### 2.5 ApplyPatch / Patch 解析与执行（高风险必测）

源头测试文件：  
- `packages/opencode/test/tool/apply_patch.test.ts`（Tool 层）  
- `packages/opencode/test/patch/patch.test.ts`（解析与执行逻辑层）

建议清单（P0）：

- [ ] 参数校验：缺 patchText、空 patch、格式非法均拒绝
- [ ] 组合 patch：一次 patch 中 add/update/delete 同时存在仍正确应用
- [ ] 多 hunk/多 chunk：同文件多次上下文修改稳定
- [ ] insert-only hunk（纯插入）可用；update 自动补 trailing newline
- [ ] move 文件：移动到新目录；覆盖已有目标文件
- [ ] add 覆盖已有文件：策略明确且可测
- [ ] update/delete 目标不存在应拒绝；delete 目标为目录应拒绝
- [ ] hunk header/context 缺失/歧义时拒绝（且失败不产生副作用）
- [ ] EOF anchor：从 EOF 优先匹配；端点锚定稳定
- [ ] heredoc 包裹 patch（含/不含 `cat`）可解析
- [ ] 容忍差异：尾随空白/前导空白/Unicode 标点差异的匹配策略有测试

### 2.6 Truncation（通用截断组件 + 清理策略 + 权限提示）

源头测试文件：`packages/opencode/test/tool/truncation.test.ts`

建议清单（P0/P1）：

- [ ] JSON/文本按 bytes/lines 维度截断（head 默认、tail 可选）
- [ ] 未超限不改动内容
- [ ] 单行超大：走 bytes 截断并有清晰提示文案
- [ ] 截断时将完整输出写入文件；未截断不写文件
- [ ] 清理策略：删除 7 天前的旧截断文件、保留近期文件
- [ ] “Task 工具提示”是否展示：取决于 agent 是否具备 task 权限（本项目如无 Task 概念，可改为“建议改用子任务/分步”的提示）

### 2.7 WebFetch（附件 vs 文本：图片/SVG/纯文本）

源头测试文件：`packages/opencode/test/tool/webfetch.test.ts`

建议清单（P1）：

- [ ] 图片响应：以 file attachment 返回
- [ ] SVG：保留为文本输出（不要误当二进制附件）
- [ ] text/plain 等：保持文本输出

### 2.8 external_directory 归一化（权限请求 canonical glob）

源头测试文件：`packages/opencode/test/tool/external-directory.test.ts`

建议清单（P0）：

- [ ] 空 target：不触发询问（no-op）
- [ ] target 在项目内：不触发询问
- [ ] target 在项目外：只询问一次且 patterns 归一化为 canonical glob
- [ ] kind=directory：pattern 使用目录级 `dir/*`
- [ ] bypass=true：跳过 prompting（用于已授权场景）

### 2.9 路径穿越防护（必须独立单测）

源头测试文件：`packages/opencode/test/file/path-traversal.test.ts`

建议清单（P0）：

- [ ] 允许项目内路径
- [ ] 拒绝 `../` 穿越、拒绝项目外绝对路径
- [ ] prefix collision（如 `/repo-a` vs `/repo`）不误判
- [ ] 深层穿越、列目录、读取敏感文件（类 `/etc/passwd`）都被拒绝
- [ ] “monorepo 子目录工作区”场景：worktree 与 directory 不同仍能正确判断
- [ ] 非 git 项目不会因为 worktree 退化成 `/` 而放开任意路径

---

## 3) Skills / Commands（技能与命令加载）

### 3.1 SkillTool（读取 skill 内容块 + 列出文件 + 触发 permission）

源头测试文件：`packages/opencode/test/tool/skill.test.ts`

建议清单（P0）：

- [ ] Tool description 中包含 skill 的 location URL（便于 UI/日志回溯）
- [ ] execute 返回 `<skill_content>` 块，并列出技能目录下文件路径
- [ ] execute 触发 `skill` 权限询问：patterns/always 包含 skill 名称

### 3.2 Skill 发现（多目录：项目/兼容/.agents/全局）

源头测试文件：`packages/opencode/test/skill/skill.test.ts`

建议清单（P0）：

- [ ] 从项目目录发现：`.opencode/skill/`（源头）→ 对齐本项目的 project skill 路径
- [ ] 兼容发现：`.claude/skills/` 与 `.agents/skills/`（含全局 `~/.claude/skills/`、`~/.agents/skills/`）
- [ ] 缺 frontmatter 的技能被跳过（而不是崩溃）
- [ ] 多技能同时存在的排序/去重规则稳定
- [ ] “skills live in 的目录解析”正确（返回真实目录集合）

### 3.3 Skill 远程拉取/缓存（可选但很有价值）

源头测试文件：`packages/opencode/test/skill/discovery.test.ts`

建议清单（P1/P2，可选）：

- [ ] 从 Cloudflare URL 拉取 skill 索引（无尾斜杠也可）
- [ ] 非法 URL / 非 JSON 响应返回空数组且不抛异常
- [ ] 下载 SKILL.md 同时下载 reference files
- [ ] second pull 命中缓存（避免重复下载）

---

## 4) Hooks / Plugins（可插拔改写/拦截）

> 源头项目以 plugin 的形式覆盖部分 provider/auth 行为；本项目对应 `openagentic_sdk/hooks/` 与 provider 的可插拔层。

源头测试文件：`packages/opencode/test/plugin/auth-override.test.ts`、`packages/opencode/test/plugin/codex.test.ts`

建议清单（P1）：

- [ ] 用户插件可覆盖内置 provider 的认证逻辑（优先级/选择器/命中条件明确）
- [ ] 解析 token/JWT 的健壮性：非法结构/非法 base64/非法 JSON 均返回 undefined，不崩溃

---

## 5) Permissions & Human-in-the-loop（权限门 + 人类交互）

### 5.1 PermissionNext：规则解析/合并/评估/禁用工具

源头测试文件：`packages/opencode/test/permission/next.test.ts`

建议清单（P0）：

- [ ] fromConfig：string/object/mixed/empty 的解析；`~`、`$HOME` 展开规则（中间的 `~` 不展开）
- [ ] merge：拼接/新增/同权限规则拼接；空 ruleset no-op；顺序保持；config 覆盖默认 ask/allow
- [ ] evaluate：exact/wildcard/glob；未知 permission 默认 ask；“last match wins”；specific 与 wildcard permission 的组合策略
- [ ] disabled：deny 规则会禁用 tool；edit deny 会连带禁用 edit/write/patch/multiedit（按本项目工具集合对齐）
- [ ] ask/reply：allow 立即通过；deny 抛 Rejected；ask 返回 pending；reply 一次性 resolve；reject 取消同 session 所有 pending
- [ ] ask：多 pattern 逐一检查，遇到 deny 立即停止；全部 allow 才通过

### 5.2 permission-task（若本项目没有 Task，可作为“子任务工具”概念对照）

源头测试文件：`packages/opencode/test/permission-task.test.ts`

建议清单（P1）：

- [ ] task permission 的默认行为（无规则时 ask）
- [ ] task tool 的 disabled 规则：全局 wildcard deny 的影响、specific allow 的覆盖、last match wins
- [ ] 从 config 加载 task permission 并参与 evaluate（与其他工具混合配置）

### 5.3 PermissionArity（命令前缀匹配）

源头测试文件：`packages/opencode/test/permission/arity.test.ts`

建议清单（P2，可选）：

- [ ] 未知命令默认取首 token；多 token 命令；nested 前缀“最长匹配 wins”；边界 case

### 5.4 Question 系统（AskUserQuestion 的“pending/resolve/reject”语义）

源头测试文件：`packages/opencode/test/question/question.test.ts`、`packages/opencode/test/tool/question.test.ts`

建议清单（P0）：

- [ ] ask：返回 pending；加入 pending 列表
- [ ] reply：resolve pending，移除 pending；未知 requestID no-op
- [ ] reject：抛 RejectedError，移除 pending；未知 requestID no-op
- [ ] 支持 multiple questions；list 返回所有 pending
- [ ] tool.question：参数有效时调用 Question.ask；header 超过 12 但 < 30 仍可通过（源头曾放宽验证）

---

## 6) Sessions / Resume（会话落盘/恢复/消息规范/压缩/重试）

### 6.1 Session 事件顺序（started/update）

源头测试文件：`packages/opencode/test/session/session.test.ts`

建议清单（P0）：

- [ ] session 创建时产生 `session.started`
- [ ] `session.started` 必须在 `session.updated` 之前（顺序不变）

### 6.2 指令加载（AGENTS.md layering / config dir 优先）

源头测试文件：`packages/opencode/test/session/instruction.test.ts`

建议清单（P0）：

- [ ] 项目根已有 AGENTS.md 时不重复加载（已在 systemPaths）
- [ ] 子目录 AGENTS.md 可被加载（不在 systemPaths）
- [ ] 直接读取 AGENTS.md 不触发“再次加载”
- [ ] `OPENCODE_CONFIG_DIR`（对照本项目相关 env）优先于全局 AGENTS.md
- [ ] config dir 无 AGENTS.md 时回退全局；未设置时使用全局

### 6.3 Message V2：消息拆分/过滤/工具结果序列化/错误归类

源头测试文件：`packages/opencode/test/session/message-v2.test.ts`

建议清单（P0）：

- [ ] 过滤无 parts 的消息；过滤仅含 ignored parts 的消息
- [ ] 注入 synthetic text parts（保证协议兼容）
- [ ] user text/file parts 转换，并注入 compaction/subtask prompts（按本项目 prompt 架构对齐）
- [ ] assistant 工具完成：转换为 tool-call + tool-result，attachments 正确
- [ ] provider metadata：assistant model 不同则省略
- [ ] compacted tool output：替换为 placeholder（避免上下文爆炸）
- [ ] 工具报错：转换为 error-text tool result
- [ ] 非 abort 错误的 assistant 消息过滤策略
- [ ] aborted assistant：仅在包含非 step-start/reasoning 内容时保留
- [ ] step-start 边界切分；仅含 step-start 的消息丢弃
- [ ] pending/running 的 tool call：转成 error result，避免 dangling `tool_use`
- [ ] context overflow：序列化为 ContextOverflowError；并能从 provider 错误消息中识别
- [ ] error codes 序列化；Copilot 403 映射到 reauth 引导
- [ ] 429 无 body 不误判为 context overflow
- [ ] 未知 inputs 的序列化有兜底

### 6.4 Compaction：触发条件/计费/缓存 token 统计（含已知 BUG 用例）

源头测试文件：`packages/opencode/test/session/compaction.test.ts`

建议清单（P0/P1）：

- [ ] token 超出 usable context 触发 compaction；未超则不触发
- [ ] token 统计包含 cache.read；Anthropic cache write metadata 处理正确
- [ ] input caps（limit.input）时的触发边界被锁定（源头包含多条 BUG 回归用例，建议择要引入）
- [ ] reasoning tokens/可选字段缺失时不崩溃
- [ ] cost 计算公式正确（按本项目 models 配置来源对齐）

### 6.5 Retry：退避/Retry-After/错误码分类

源头测试文件：`packages/opencode/test/session/retry.test.ts`

建议清单（P0）：

- [ ] 退避上限（例如 30s）与 retry-after 优先级正确（ms/seconds/http-date）
- [ ] 非法/过去时间 retry hints 被忽略
- [ ] sleep delay 上限避免溢出（32-bit signed integer cap）
- [ ] provider 错误 JSON message → retryable 分类（too_many_requests/overloaded 等）
- [ ] context overflow 不重试
- [ ] ECONNRESET retryable；OpenAI 404 retryable（按本项目策略可调整，但要可测）

### 6.6 Prompt 边界：缺失文件 / 特殊字符 / agent variant

源头测试文件：  
- `packages/opencode/test/session/prompt-missing-file.test.ts`  
- `packages/opencode/test/session/prompt-special-chars.test.ts`  
- `packages/opencode/test/session/prompt-variant.test.ts`

建议清单（P0/P1）：

- [ ] prompt 中 file part 丢失不导致整体失败
- [ ] 文件名含 `#` 等特殊字符时可正确处理/引用
- [ ] agent variant 仅在使用 agent model 时生效（避免误影响通用 model）

### 6.7 Structured Output（单测 + 可选真 API 集成）

源头测试文件：  
- `packages/opencode/test/session/structured-output.test.ts`（强烈建议做等价单测）  
- `packages/opencode/test/session/structured-output-integration.test.ts`（可选，需 API key）

建议清单（P0）：

- [ ] format 解析：text/json_schema；默认 retryCount；自定义 retryCount；非法 type/缺 schema/负 retryCount 拒绝
- [ ] StructuredOutputError：结构化字段完整，可序列化 toObject
- [ ] user message 可携带 outputFormat；assistant message 可携带 structured_output（均为 optional）
- [ ] schema 生成 tool：id/description/inputSchema；剥离 `$schema` 字段
- [ ] execute：onSuccess 收到合法 args；nested object/array 支持
- [ ] schema 验证：缺 required/wrong type 在 execute 前失败（本项目使用的验证器可能不同，但需要等价覆盖）

建议清单（P2，可选集成）：

- [ ] 有 API key 时跑：简单 schema/nested schema/text 模式；验证 structured 字段写入与 error 为空（注意成本与速率）

### 6.8 Revert + Compact 的组合状态机

源头测试文件：`packages/opencode/test/session/revert-compact.test.ts`

建议清单（P1）：

- [ ] revert 后执行 compact：状态机正确、不会污染后续 compaction message
- [ ] 创建 compaction message 前会清理 revert state（避免残留）

---

## 7) 存储迁移（可选参考：稳态演进）

源头测试文件：`packages/opencode/test/storage/json-migration.test.ts`

说明：本项目以 `events.jsonl` 为核心持久化形态，但“迁移/兼容/损坏容忍”的测试思想非常值得借鉴。

建议清单（P2，可选）：

- [ ] 旧格式 → 新格式迁移：幂等（跑两次不重复）
- [ ] orphaned 数据跳过；部分损坏文件不中断迁移并记录错误统计
- [ ] 列表类数据保持顺序（如 todos position）

---

## 8) 备注：如何把这份清单落到 openagentic-sdk 的 unittest

- Fixture：源头大量依赖 `tmpdir({ git, config, init })`；Python 对应建议用 `tempfile.TemporaryDirectory()` + 辅助函数（可选初始化 git、写入 config、自动清理）。
- 权限门/HITL：源头通过注入 `ctx.ask(...)` 捕获权限请求；Python 对应建议把 `PermissionGate`/`user_answerer` 做成可注入依赖，在测试里用 fake/spies 记录请求。
- 网络/E2E：Structured Output integration 属于“有 key 才跑”的测试；Python 里建议同样用 env gating（避免默认跑出费用）。

