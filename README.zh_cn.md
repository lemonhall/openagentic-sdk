# OpenAgentic SDK（Python）

纯 Python、开源的 Agent SDK，编程模型参考 Claude Agent SDK：支持多轮会话、工具调用、权限确认、会话持久化、以及从 `.claude/` 读取 skills / commands。

状态：早期阶段（API 可能变化），但核心 runtime + tool loop 已可用。

## 这个项目解决什么问题？

如果你想要一个“小而可改”的 Python 代码库，用来跑通日常 agent 工作流（而不是只做一个 `chat()` 包装器），这个项目提供：

- **最小可用的 agent runtime**：`run()` / 流式 `query()` / CAS 风格 `query_messages()`
- **多轮会话 + 可恢复**：生成 `session_id`，落盘 `events.jsonl`，支持 `resume=<session_id>`
- **真实工具链路**：模型发起 tool call → 权限门（prompt/callback/acceptEdits/bypass）→ 执行工具 → 回传结果 → 模型继续
- **默认面向人类的输出**（调试时可开 debug）
- **`.claude` 兼容**：项目记忆、slash commands、skills 都可以从磁盘加载
- **OpenAI / OpenAI-compatible provider**：示例默认使用一个真实的 OpenAI-compatible 后端（RIGHTCODE）

## 快速开始（uv 安装）

前置：Python 3.11+ 和 `uv`。

在一个新目录里安装并启动 CLI（PowerShell 示例）：

```powershell
mkdir oas_test
cd oas_test
uv init
uv add openagentic-sdk
$env:RIGHTCODE_API_KEY="..."  # 必需
$env:RIGHTCODE_BASE_URL="https://www.right.codes/codex/v1"  # 可选
$env:RIGHTCODE_MODEL="gpt-5.2"  # 可选
$env:RIGHTCODE_TIMEOUT_S="120"  # 可选
uv run oa chat
```

## 快速开始（本地）

前置：Python 3.11+。

（可选）以可编辑模式安装：

`pip install -e .`

设置环境变量（示例与 CLI 默认使用 RIGHTCODE）：

- `RIGHTCODE_API_KEY`（必需）
- `RIGHTCODE_BASE_URL`（可选，默认 `https://www.right.codes/codex/v1`）
- `RIGHTCODE_MODEL`（可选，默认 `gpt-5.2`）
- `RIGHTCODE_TIMEOUT_S`（可选，默认 `120`）

跑测试：

`python -m unittest -q`

跑示例：

- `python example/01_run_basic.py`
- 完整列表见 `example/README.md`

## `oa` 命令行（CLI）

安装（可编辑模式）：

`pip install -e .`

如果在 Windows 下安装后找不到 `oa` 命令，把 pip 输出的 scripts 目录加入 `PATH`（或直接运行 `python -m openagentic_cli chat`）。

使用 `uv` 安装并运行（推荐）：

```powershell
uv add openagentic-sdk
uv run oa --help
uv run oa chat
```

常用命令：

- `oa chat`（多轮 REPL；输入 `/help` 查看命令；TTY 下粘贴多行会作为一次输入，或使用 `/paste` ... `/end`）
- `oa run "prompt"`（支持 `--json`、`--no-stream`）
- `oa resume <session_id>`（等价于 `oa chat --resume <session_id>`）
- `oa logs <session_id>`（汇总 `events.jsonl`）

服务端与集成：

- `oa serve --port 4096`（本地 HTTP server）
- `oa --port 4096`（OpenCode VSCode 兼容：等价于 `oa serve --port 4096`）
- `oa acp`（ACP stdio server）
- `oa github install`（生成 GitHub Actions workflow）
- `oa github run`（GitHub Actions runner）

默认会话目录为 `~/.openagentic-sdk`（可用 `OPENAGENTIC_SDK_HOME` 覆盖）。

更多 OpenCode parity 的用户文档见：

- `docs/guides/opencode-parity-v2/README.md`

示例默认需要环境变量（至少要有 `RIGHTCODE_API_KEY`）。在 PowerShell 下可以这样检查：

- 是否存在：`Test-Path Env:RIGHTCODE_API_KEY`
- 查看值：`$env:RIGHTCODE_API_KEY`

## Provider / 环境变量（示例默认）

示例使用 `OpenAICompatibleProvider`，默认读取这些变量：

- `RIGHTCODE_API_KEY`（必需）
- `RIGHTCODE_BASE_URL`（可选，默认 `https://www.right.codes/codex/v1`）
- `RIGHTCODE_MODEL`（可选，默认 `gpt-5.2`）
- `RIGHTCODE_TIMEOUT_S`（可选）
- `RIGHTCODE_MAX_RETRIES` / `RIGHTCODE_RETRY_BACKOFF_S`（可选）

如果你要用 `WebSearch` / `WebFetch`（Tavily），需要：

- `TAVILY_API_KEY`
- `OPENAGENTIC_WEBFETCH_TAVILY_EXTRACT_DEPTH`（可选；`basic` / `advanced`，默认 `advanced`）

## 内置 Tools

默认包含：

- `Read`, `Write`, `Edit`
- `Glob`, `Grep`
- `Bash`
- `WebFetch`（直接走 Tavily Extract；需要 `TAVILY_API_KEY`）
- `WebSearch`（需要 `TAVILY_API_KEY`）
- `TodoWrite`
- `SlashCommand`（加载 `.claude/commands/<name>.md`）
- `Skill`（按 `name` 加载技能；可用技能列表在 tool description 里）

对 OpenAI-compatible provider，会把一套长文本 “tool 使用说明” 注入到 tool schema 的 `description` 里（opencode 风格），用来提升模型按规则调用工具的稳定性。

## `.claude` 兼容

当 `setting_sources=["project"]` 时，会索引：

- `CLAUDE.md` 或 `.claude/CLAUDE.md`
- `.claude/commands/*.md`

Skills 发现路径：

- 项目级（兼容）：`.claude/{skill,skills}/**/SKILL.md`
- 全局：`~/.openagentic-sdk/{skill,skills}/**/SKILL.md`（可用 `OPENAGENTIC_SDK_HOME` 覆盖）

当 `setting_sources=["project"]` 时，`query()` 会在 system prompt 中注入项目 memory + commands 索引（skills 通过 `Skill` tool description 暴露）。

## Console 输出（默认清爽，调试可开）

示例使用 `openagentic_sdk.console.ConsoleRenderer`：

- 默认只输出 assistant 文本（面向人类）
- 调试输出：`--debug` 或 `OPENAGENTIC_SDK_CONSOLE_DEBUG=1`

推荐先跑一个交互式 CLI 多轮示例（几乎能覆盖常用 tools）：

- `python example/45_cli_chat.py`



## OpenAgentic SDK 家族（兄弟项目）

本 Kotlin 仓库属于一个小型“SDK 家族”：大家共享同一套总体思想（可追溯的 sessions/events、默认安全的 tools、确定性的测试门禁），但分别面向不同的运行环境与产品形态。

### 1）`openagentic-sdk`（Python，最早的源头）

- 仓库：`https://github.com/lemonhall/openagentic-sdk`
- 家族最早的项目，也是**测试套件最强壮**的版本（据描述约 369 个测试）。
- 工具最全面，同时包含 CLI 工具等配套。
- 具备 TUI 的 sessions 观察窗（dashboard）用于查看 trace。

### 2）`openagentic-sdk-ts`（TypeScript，沙盒优先）

- 仓库：`https://github.com/lemonhall/openagentic-sdk-ts`
- 基于 Python 版本衍生，重点是**完整的沙盒系统**。
- 提供**浏览器内沙盒**；在 Linux 和浏览器环境下都非常安全。

基于 TS 项目进一步发展出的侧边栏助手：

- `WebMCP_Sidecar`：`https://github.com/lemonhall/WebMCP_Sidecar`
- 支持 WebMCP 的全功能浏览器侧边栏 AI 助手。

### 3）`openagentic-sdk-gdscript`（Godot 4.6，最复杂的一支）

- 仓库：`https://github.com/lemonhall/openagentic-sdk-gdscript`
- 面向 Godot 4.6 的 SDK，包含完整的 **VR Office（虚拟办公室）**、2D demo 等。
- 内置一整套 GDScript 的 **IRC client SDK**。
- 实现基于 IRC 的 RPC 协议，并在其上支持类似 OpenClaw 的多机架构。

### 4）`openagentic-sdk-kotlin`（面向 Android）

- 仓库：`https://github.com/lemonhall/openagentic-sdk-kotlin`
- 基于 Kotlin 的完整 Agent SDK 架构，主要面向 Android 的可复用核心。

### 未来计划（凑齐约 6 兄弟）

- Swift（Apple 平台）
- Rust（系统侧 + CLI/嵌入式方向）

功能分布未来可能会演进，但核心目标一致：**安全的 Agent runtime + 强可追溯测试**。


