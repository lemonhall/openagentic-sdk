# PRD-0021 — Real-Network E2E (CLI PTY Suite v21)（真实网络 E2E：CLI 真 TTY/PTY 测试套件 v21）

## Vision

为 `openagentic_cli` 增加一套“更真”的 E2E：

- **真网络**：真实调用 Provider（读取本机 `.env` / 环境变量），覆盖真实链路（CLI → SDK → Provider）。
- **真交互**：在 **真 TTY**（POSIX `pty`）下驱动交互式 REPL（包含提示符、输入、命令分支等）。
- **强隔离**：测试运行不污染用户本机状态目录；不被用户全局 OpenCode/opencode 插件配置干扰。
- **独立套件**：不干扰 `e2e_tests/`，且不会在默认 `python -m unittest -q` 下自动运行。

## Non-Goals

- 不覆盖 Windows 原生 conhost 的 VT/输入模式差异（该类测试建议在 Windows 侧另立套件）。
- 不追求“网络故障复现”（429/断网/网关抖动）；本版聚焦“交互语义 + 落盘证据 + 可回归”。
- 不把模型输出当唯一证据：优先使用 **落盘 events.jsonl** 与确定性输出做断言，避免模型波动带来脆弱测试。

## Requirements

### REQ-0021-001 — CLI PTY e2e suite is isolated and opt-in（独立且强隔离）

新增 `e2e_cli_tests/`：
- 需要 POSIX `pty`（WSL2/Linux/macOS），Windows 原生自动 skip；
- 通过设置 `OPENAGENTIC_SDK_HOME` 等方式把会话落盘隔离到临时目录；
- 通过设置 `OPENCODE_TEST_HOME` / `XDG_CONFIG_HOME` 避免读取用户全局 opencode 插件配置导致测试不稳定；
- 仅在显式运行时执行（`python -m unittest discover -s e2e_cli_tests ...`）。

### REQ-0021-002 — In bypass permission mode, REPL must not prompt auto-approve question（稳定化启动交互）

在真 TTY 下运行 `oa chat` 时，如果 `OA_PERMISSION_MODE=bypass`：
- 必须 **不弹出** “Auto-approve Write/Edit/Bash … ? [y/N]” 的交互问题；
- 否则 PTY e2e 将被阻塞且行为不可回归。

### REQ-0021-003 — REPL /help and /exit work under PTY（基础交互回归）

在 PTY 下：
- `/help` 输出包含 `/exit`、`/paste`；
- `/exit` 退出且 exit code=0。

### REQ-0021-004 — Multi-turn chat persists to disk with a stable session_id（长会话落盘证据）

在一次 `oa chat` 中进行多轮对话：
- 只应产生一个 session 目录；
- `events.jsonl` 行数应随每轮交互增长（以落盘为证据）。

### REQ-0021-005 — `/new` starts a fresh session（会话切换）

在一次 REPL 中：
- 完成至少 1 轮对话后执行 `/new`；
- 再完成 1 轮对话；
- 应产生 **两个** session 目录，且两者事件互不混淆。

### REQ-0021-006 — Paste modes behave correctly under PTY（粘贴语义）

覆盖两类粘贴语义：

- `/paste ... /end`：多行输入应被合并为单个 user turn，并落盘为单条 `user.message`（text 中包含换行）。
- Bracketed paste markers（`\x1b[200~` ... `\x1b[201~`）：
  - 输入不得被当作 REPL 命令解析（即 pasted 的 `/help` 不能触发帮助）；
  - pasted 内容应落盘为 `user.message`。

### REQ-0021-007 — resume/logs interop with the created session（子命令互操作）

完成一次会话后：
- `oa logs <session_id>` 能输出非空摘要；
- `oa resume <session_id>` 能继续对话并向该 session 追加 events（以落盘为证据）。

## Acceptance (DoD)

必须全部满足：

1) WSL2/Linux/macOS 下：
   - `python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v` exit code=0
2) REQ-0021-001..007 都有对应测试或可复现证据链（Req → Plan → Tests）。

