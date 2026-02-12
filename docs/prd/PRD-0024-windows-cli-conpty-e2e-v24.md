# PRD-0024 — Windows CLI ConPTY E2E (v24)（Windows 11：CLI 真交互 ConPTY 端到端测试 v24）

## Vision

补齐 `openagentic_cli` 在 **Windows 11 原生终端**下的“真交互”回归：

- 通过 **ConPTY (Pseudo Console)** 驱动 `oa chat`，覆盖真实 `isatty`、VT input、提示符渲染、粘贴模式等路径；
- 作为 v21（POSIX pty）测试的补充，专门捕捉 Windows console 语义差异导致的 bug；
- 套件独立、强隔离、可回归：不污染用户目录、不被用户全局 opencode 配置影响。

> 实施策略说明（v24 现实约束）：
>
> - Windows 原生的“真 TTY/ConPTY 驱动”在纯 stdlib 环境下存在较高不确定性与排障成本；
> - v24 首先交付一套 **Windows 原生、在线、可回归** 的 CLI e2e（基于 stdio pipes 驱动），优先把 CLI + SDK + Provider 的真实链路跑通；
> - ConPTY harness 作为后续加强项保留在套件内（实验性），在找到稳定 attach/读写模型后再升级为默认驱动。

## Non-Goals

- 不支持 Windows 10（本版仅 Windows 11；后续版本再扩展最低版本探测/兼容）。
- 不追求网络故障类不稳定复现（429/断网）；本版聚焦交互语义与可回归证据链。

## Requirements

### REQ-0024-001 — Windows ConPTY E2E suite is isolated and opt-in

新增 `e2e_cli_win_tests/`：
- 仅在 `sys.platform == "win32"` 下运行，其它平台自动 skip；
- 通过 `OPENAGENTIC_SDK_HOME` 强隔离 session/auth/shares；
- 通过 `OPENCODE_TEST_HOME` / `XDG_CONFIG_HOME` 隔离 opencode 全局配置；
- 默认不会被 `python -m unittest -q` 或 `e2e_tests/` 触发，需显式运行。

### REQ-0024-002 — ConPTY harness can run `oa chat` and exchange input/output

提供纯 stdlib（`ctypes`）实现的 ConPTY harness：
- 可启动子进程 `python -m openagentic_cli chat`
- 可写入输入（包含 `\r\n`、ESC 序列）
- 可读取输出并支持 `read_until()` 超时断言

并提供 Windows 稳定驱动（本版默认）：
- 基于 stdio pipes 的驱动，可稳定运行 `openagentic_cli chat` 并进行交互断言（在线、真实网络）。

### REQ-0024-003 — `OA_PERMISSION_MODE=bypass` does not show auto-approve startup prompt (TTY)

在 ConPTY（真 TTY）下运行 `oa chat`，当 `OA_PERMISSION_MODE=bypass`：
- 不得出现 “Auto-approve Write/Edit/Bash … ? [y/N]” 启动提示；
- 否则会导致自动化阻塞且行为不可回归。

### REQ-0024-004 — `/help` and `/exit` work under ConPTY

在 ConPTY 下：
- `/help` 输出包含 `/exit`、`/paste`
- `/exit` 退出且 exit code=0

### REQ-0024-005 — Windows multiline input paths are stable under ConPTY

覆盖两类多行输入：
- `/paste` + `/end`：多行应合并为一个 turn，且不被当作 REPL 命令解析；
- Bracketed paste markers（`ESC[200~`…`ESC[201~`）：输入块必须作为 prompt 文本发送到模型（不触发 REPL `/help` 等命令分支）。

## Acceptance (DoD)

必须全部满足：

1) Windows 11 下：
   - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
2) REQ-0024-001..005 都有对应测试或可复现证据链（Req → Plan → Tests → Evidence）。
