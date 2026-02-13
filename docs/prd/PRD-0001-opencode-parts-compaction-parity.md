# PRD-0001: OpenCode Parity — Prompt Parts（@file/@agent）与 Compaction Overflow（v1）

## Vision

在 `openagentic-sdk` 中实现与 OpenCode 一致的两块核心行为：

1) **Prompt Parts**：对 slash command 模板中的 `@file` / `@agent` 引用，按 OpenCode 的 `resolvePromptParts()` 语义产出结构化 parts，并在渲染内容中包含文件内容（文本文件）与目录信息（目录引用），且 **URL 编码与路径解析行为稳定可测**。

2) **Compaction Overflow**：自动触发 compaction 的 overflow 判定与 OpenCode 一致（reserved 计算、>= 边界、input_limit 优先）。

非目标：本 PRD 不覆盖 JS/TS 插件执行、MCP OAuth、Server API 面、完整 OpenCode 测试套件对齐。

## Background / Context

本仓库已有 OpenCode 对齐基础与差异审计文档（历史）：
- `docs/plans/opencode-parity-v2-90-reaudit.md`

本 PRD 以“OpenCode 代码为真”的原则补齐两块阻塞级差异。

## Requirements

### REQ-0001-001 — SlashCommand 渲染返回结构化 parts（OpenCode 语义）

当 runtime 执行 `SlashCommand`（模型 tool call）或用户输入直接 `/cmd ...` 触发展开时：

- 必须返回 `parts: list[dict]`，至少包含：
  - `{"type":"text","text": <rendered_text_without_file_tool_transcripts>}`
  - 对每个唯一的 `@ref`：
    - 若 ref 在 worktree（`.git` 根）下存在文件：追加 `{"type":"file","url": "file://...", "filename": <ref>, "mime":"text/plain"}`
    - 若 ref 在 worktree 下存在目录：追加 `{"type":"file","url": "file://...", "filename": <ref>, "mime":"application/x-directory"}`
    - 若不存在但 ref 命中 agent 名称：追加 `{"type":"agent","name": <ref>}`
- `file` part 的 `url` 必须是 RFC3986 编码（例如文件名包含 `#` 时 URL 中应为 `%23`）。
- parts 发现顺序：`text` 在前，随后按 ref 在模板中出现顺序追加（去重后保留首次出现位置）。

验收：新增/调整 `tests/test_slash_command_*` 覆盖 URL 编码与 filename 保留。

### REQ-0001-002 — @file/@dir 引用内容注入（无“工具调用转录”文本）

渲染 SlashCommand 的最终 `content`（tool output 的 `content` 字段、以及用户 `/cmd` 展开后的最终 user content）必须：

- 包含被引用的文本文件内容（能在字符串中找到文件内容片段）
- 包含目录引用的列表信息（至少包含 List tool 的输出文本片段）
- **不得**包含类似 `Called the Read tool ...` / `Called the list tool ...` 这种“工具调用转录”前缀

说明：内部仍可通过已有 `Read`/`List` 工具执行读取（受权限门控制），但输出应为“内容本身”，而非“调用日志”。

### REQ-0001-003 — Subtask 命令不携带 file parts 且不注入文件内容

当命令 frontmatter 设置 `subtask: true` 时：

- `parts` 必须只包含一个 `{"type":"subtask", ...}`（与现有测试期望一致）
- 不得出现 `file` parts
- `content` 不得被 `@file` / `@dir` 展开注入

### REQ-0001-004 — Compaction overflow 判定与 OpenCode 一致

`would_overflow()` 必须满足：

- `context_limit <= 0` 时始终返回 False
- 计算 `max_output_tokens = min(global_output_cap, output_limit>0 ? output_limit : global_output_cap)`
- `reserved = compaction.reserved ?? min(20_000, max_output_tokens)`
- `usable = (input_limit ?? context_limit) - reserved`
- `count = usage.total_tokens ?? usage.input_tokens + usage.output_tokens + usage.cache_read_tokens`
- overflow 判定：`count >= usable`

验收：新增/调整单测覆盖 `>=` 边界与 reserved 推导。

### REQ-0001-005 — CLI/config 对齐：支持 compaction.reserved 与 input_limit

- `openagentic_cli.config.build_options()` 需支持从 OpenCode config 读取 `compaction.reserved`（并写入 options.compaction）
- 在 models metadata 可得时，派生 `compaction.input_limit`（若 metadata 中存在 limit.input 且用户未显式提供）

## Non-Goals

- 不实现 OpenCode JS/TS plugin 安装/执行
- 不实现 MCP OAuth 完整对齐
- 不实现 OpenCode 的完整 server surface

## Risks

- “parts” 的 provider 侧落地（Responses attachments）可能需要更大范围变更；v1 仅保证 runtime/测试与内容注入对齐。
- Windows 路径的 `file://` URI 编码/格式需用 `Path.as_uri()` 统一，避免手拼。

