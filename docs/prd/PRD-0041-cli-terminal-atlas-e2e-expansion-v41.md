# PRD-0041 — CLI Terminal Atlas E2E Expansion (v41)（按“终端经典坑图谱”扩容 CLI 交互式 E2E）

## Vision

把 `docs/research/Terminal-Classic-Bugs-Atlas-Deep-Research.md` 里的“终端经典坑”清单，逐步落成 `openagentic_cli` 的**真终端**（Windows ConPTY + POSIX PTY）E2E 回归网：

- 让“终端语义类 bug”（吞键/删词/控制序列污染/粘贴误触发等）可复现、可回归、可守门；
- 断言尽量锚到**证据链**（`events.jsonl`），避免屏幕文案脆弱性；
- 套件保持独立、opt-in，不干扰 `e2e_tests/`（SDK 核心随机层/矩阵层）。

## Non-Goals

- 不在 v41 引入完整 line-editor（方向键编辑、history、Ctrl+Left/Right 等）。
- 不在 v41 做 IME（中文输入法）自动化覆盖（保留为探索/手工回归与后续专项）。
- 不在 v41 引入第三方依赖（继续保持纯 stdlib + 本仓库 `packages/conpty-expect`）。

## Requirements

### REQ-0041-001 — “图谱 → E2E Backlog”可追溯

- 在 v41 计划中明确：本轮覆盖图谱中的哪几个坑位（P0/P1）。
- 每个新增 E2E 用例必须能在计划里对应到一个“图谱坑位”描述（至少 1 条）。

### REQ-0041-002 — Windows ConPTY：特殊键序列不得污染用户输入（evidence: events.jsonl）

在 Windows ConPTY 真 TTY 下，注入常见特殊键序列（例如方向键 `ESC[D`/`ESC[C`）时：

- `events.jsonl` 的 `user.message.text` 不得包含 `\x1b`（ESC）等控制序列残留；
- 断言以 `events.jsonl` 为准（不依赖屏幕回显）。

> 说明：此处不要求实现“方向键编辑”，只要求“不会把控制序列当普通文本落盘/发送给模型”。

### REQ-0041-003 — Suites remain opt-in and isolated

- Windows：继续使用 `e2e_cli_win_tests/`，通过 `OPENAGENTIC_SDK_HOME`/`XDG_CONFIG_HOME` 等隔离；
- 运行命令保持不变：`python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v`。

## Acceptance (DoD)

必须全部满足：

1) Windows 11 + PowerShell 下：
   - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
2) REQ-0041-001..003 均有可追溯落地（Req → Plan → Tests → Evidence）。

