# Agent Notes (openagentic-sdk)

面向在本仓库工作的 AI/新人贡献者：尽量用**可复制执行**的命令，做变更时确保**可验证**、避免**误删/泄露**。

## 项目概览

`openagentic-sdk` 是一个纯 Python 的 Agent SDK：提供多轮会话、工具调用（带权限门）、会话持久化（`events.jsonl`）、以及从 `.claude/` 加载 commands/skills 的兼容层。

## Quick Commands（PowerShell 7.x / Windows 优先）

- 安装（开发模式 + 开发依赖）：`uv pip install -e ".[dev]"`
- 运行 CLI（不依赖脚本入口）：`python -m openagentic_cli --help`
- Lint：`ruff check . --config ruff.toml`
  - 自动修复（谨慎，可能改动很多文件）：`ruff check . --config ruff.toml --fix`
  - 只修你改动的文件：`ruff check path/to/file.py --config ruff.toml --fix`
- 单元测试（不含 e2e）：`python -m unittest -q`
- e2e（真实 API、会产生费用）：`python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
- CLI 交互式 e2e（真实网络 + 真 TTY/pty；独立套件，WSL2/Linux/macOS 运行）：`wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v'`
- pre-commit（可选）：`pre-commit run -a`

> 如果你在 WSL2 里跑 bash 命令：在 PowerShell 中显式调用 `wsl -e bash -lc '...'`，其余命令保持 PowerShell 语法。
>
> 说明（与平台相关）：截至 `2026-02-11`，部分单元测试在 Windows 原生环境可能因**文件锁/权限位(POSIX mode)/路径表现差异(Windows vs WSL)**而失败；优先在 WSL2/Linux 复现并修复后再宣称“全绿”。

## 架构概览

### 主要目录

- SDK 核心：`openagentic_sdk/`
  - 入口 API：`openagentic_sdk/api.py`（`run/query/query_messages`）
  - Runtime/tool loop：`openagentic_sdk/runtime.py`
  - 权限门：`openagentic_sdk/permissions/`
  - Tools：`openagentic_sdk/tools/`
  - 会话/落盘：`openagentic_sdk/sessions/`（默认 `~/.openagentic-sdk`，见下）
  - Providers：`openagentic_sdk/providers/`
  - `.claude` 兼容：`openagentic_sdk/project/`、`openagentic_sdk/skills/`、`openagentic_sdk/commands.py`
- CLI：`openagentic_cli/`（脚本入口 `oa`，见 `pyproject.toml`）
- Gateway：`openagentic_gateway/`（脚本入口 `oag`；偏“控制面/路由”）
- 单元测试：`tests/`（`unittest`）
- 真实 API e2e：`e2e_tests/`（`unittest`；会产生真实请求/费用）
- 文档：`docs/`
- 示例：`example/`

### 核心模块定义（默认优先级最高）

为了避免每次对话都重复强调，这里把本项目的“核心中的核心”明确为：**能让 AI 对话、使用工具/Skill、并与人类交互**的最基础模块。默认情况下，讨论/对齐/加测试都应优先覆盖这些模块（除非用户明确要求关注 Gateway/MCP 等边缘模块）。

- **Runtime Core（对话/工具循环）**
  - `openagentic_sdk/runtime_core/`（query loop、tool plumbing、provider input、compaction、事件落盘/恢复的关键路径）
  - `openagentic_sdk/runtime.py`（对外 API 的兼容入口与 re-export）
- **Tools（工具系统）**
  - `openagentic_sdk/tools/`（Tool 定义、schema、registry、核心工具如 Read/Write/Edit/Skill/AskUserQuestion/TodoWrite/SlashCommand）
  - `openagentic_sdk/runtime_core/tool_runner.py`、`openagentic_sdk/runtime_core/query_loop_steps/tool_plumbing.py`（tool loop 的协议适配与序列化）
- **Skills / Commands（技能与命令加载）**
  - `openagentic_sdk/skills/`、`openagentic_sdk/tools/skill.py`
  - `openagentic_sdk/commands.py`（`/slash` 直执行与模板加载链路）
- **Hooks（可插拔改写/拦截）**
  - `openagentic_sdk/hooks/`（`HookEngine`、matcher/decision、Before/AfterModelCall、Pre/PostToolUse、UserPromptSubmit 等）
- **人类交互 & 权限门（Human-in-the-loop）**
  - `openagentic_sdk/permissions/`（`PermissionGate`、prompt/callback/bypass/deny 等模式）
  - `openagentic_sdk/runtime_core/tool_ask_user_question.py`（AskUserQuestion 通过 `user_answerer` 与人类交互）
- **Sessions / Resume（会话落盘与恢复）**
  - `openagentic_sdk/sessions/`（会话落盘：`events.jsonl`；恢复：`OpenAgenticOptions.resume` / 事件重建）
  - 关键约束：`events.jsonl` 只落“可回归、可解释”的关键事件（user/assistant message、tool.use/result、hook、compaction 等）；**不要落 streaming delta（assistant.delta / text_delta）**，否则会膨胀到 GB 级。

### 数据流（简图）

`openagentic_cli` / 你的代码
→ `OpenAgenticOptions`
→ `runtime`（循环：模型输出 tool calls）
→ `PermissionGate`（允许/拒绝）
→ `tools/*`（执行）
→ `sessions/*`（写入 `events.jsonl` / 恢复 session）

### 持久化/状态目录

- 默认会话目录：`~/.openagentic-sdk`
- 可通过环境变量覆盖：`OPENAGENTIC_SDK_HOME`

测试若需写文件，优先写到临时目录（`tempfile`）或显式的测试 fixture 目录，避免污染仓库根目录。

## 代码风格与约定

- Python：目标兼容 `>=3.11`（`ruff.toml` 目标 `py311`）。
- Lint：使用 Ruff（配置见 `ruff.toml`；当前规则集主要是 `E/F/I`）。
- 行宽：120（见 `ruff.toml`）。
- 新文件建议包含：`from __future__ import annotations`（仓库内普遍采用）。
- 尽量保持“纯 stdlib”倾向：引入新三方依赖前先在 PR/issue 中说明动机、替代方案与影响面。

## Shell / 环境约定（本仓库默认 PowerShell）

- 连续执行命令用 `;`，避免使用 `&&` / `||`（兼容性与可读性更稳）。
- 需要 `curl` / `wget` 时，优先用 `curl.exe` / `wget.exe`（避免命令别名导致行为变化）。
- 需要递归搜索文本优先用 `rg`；PowerShell 备用是 `Select-String`。
- 退出码判断：原生命令以 `$LASTEXITCODE` 为准；`$?` 仅作参考。

## 代理与网络（可选）

如需走本机代理（例：`127.0.0.1:7897`），可在当前会话临时设置：

```powershell
$env:HTTP_PROXY='http://127.0.0.1:7897'
$env:HTTPS_PROXY='http://127.0.0.1:7897'
```

Git 建议只做仓库级（避免污染全局）：

```powershell
git config --local http.proxy http://127.0.0.1:7897
git config --local https.proxy http://127.0.0.1:7897
```

## 安全与“不要这样做”

- 不要提交密钥/Token：例如 `RIGHTCODE_API_KEY`、`OPENAI_API_KEY`、`TAVILY_API_KEY`、cookie、私钥文件等。
- 不要提交 `.env`：把本机 `.env` 仅用于本地开发/测试，并确保在 `.gitignore` 中忽略。
- 不要默认运行 `e2e_tests/`：这些测试会请求真实 OpenAI-compatible API，可能产生费用与速率限制。
- 不要做危险删除：`Remove-Item -Recurse -Force` / `rm -rf` 这类操作前必须确认目标目录与影响范围。
- 改了行为就补测试：对你改动的模块，至少补/改对应的 `tests/` 用例；保证 `python -m unittest -q` 通过。

## 测试策略

- 单元测试（快速、本地）：`python -m unittest -q`
- 跑单个测试文件：`python -m unittest tests.test_cli_args -v`
- e2e（真实 API、成本相关）：`python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
- CLI PTY e2e（真实网络 + 真交互；不默认运行）：`python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v`（Windows 原生无 POSIX pty，建议 WSL2）

## Scope & Precedence（多份指令覆盖关系）

- 根目录 `AGENTS.md`：默认适用于全仓库。
- 子目录下的 `AGENTS.md`：仅对该子目录树生效，且覆盖同主题的根规则。
- 同目录下若存在 `AGENTS.override.md`：其优先于 `AGENTS.md`。
- 用户在聊天中给出的显式指令，优先级最高。
