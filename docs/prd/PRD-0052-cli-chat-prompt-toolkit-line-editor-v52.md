# PRD-0052 — `oa chat` Prompt Toolkit Line Editor (v52)（默认启用更完整的行编辑；保留 legacy 开关）

## Vision

把 `openagentic_cli chat` 的输入从“自研最小行编辑/依赖终端默认行编辑”升级为 **Prompt Toolkit** 驱动的行编辑器：

- Windows 11 + PowerShell 7.x + ConPTY 真 TTY 下，Backspace/DEL/CJK、方向键编辑、以及流式输出期间的 typeahead 不再出现“吞字/整行消失/删不干净”等经典坑；
- 继续保持现有的 ConPTY 在线 E2E 套件可回归（opt-in，不影响 SDK 其它 e2e/单测默认跑的集合）；
- 旧实现保留为 **legacy 后端**（便于对照回归/紧急回退），但默认走 Prompt Toolkit，并明确标记废弃计划。

## Non-Goals

- v52 不做完整 TUI（窗口分割/滚动区/输入区）与 rich layout。
- v52 不实现“多行编辑器 textarea”（仍以单行 turn 为主；多行依旧用 `/paste ... /end` 或 bracketed paste）。
- v52 不追求 100% 视觉一致性断言（屏幕是否闪烁/覆盖），验收以 **events.jsonl 证据链** + 关键提示符为主。

## Requirements

### REQ-0052-001 — 默认使用 Prompt Toolkit（TTY 条件满足时）

当 `stdin`/`stdout` 都是 TTY 且可用 Prompt Toolkit 时：

- `oa chat` 默认使用 Prompt Toolkit 读取用户输入（支持左右方向键等常见编辑能力）。
- 若不满足（非 TTY、缺少 `fileno()` 等），自动回退到 legacy 行读取实现，确保单元测试与非交互场景稳定。

### REQ-0052-002 — 可显式选择输入后端（保留 legacy）

新增环境变量：

- `OA_CLI_INPUT_BACKEND=prompt_toolkit|legacy`（默认 `prompt_toolkit`）

要求：

- `legacy` 模式仍可工作（含 Windows 旧的 raw-ish 输入实现），并输出一次性 deprecation 提示（不影响 e2e 断言）。

### REQ-0052-003 — Windows ConPTY：方向键编辑可用（且不泄漏 ESC 序列）

在 Windows ConPTY 真 TTY 下：

- 左/右方向键用于移动光标，能在行中间插入字符（e2e 以 `events.jsonl` 中 `user.message` 为准）。
- `events.jsonl` 中 `user.message.text` 不得出现 `\x1b`（ESC）控制序列泄漏。

### REQ-0052-004 — Windows ConPTY：Backspace/DEL 的单字符删除语义（含 CJK）

在 Windows ConPTY 真 TTY 下：

- Backspace/DEL 删除 **一个字符**，不得出现“按一次删掉一个词”的回归；
- CJK 字符删除后，最终落盘文本必须与编辑后的预期一致（不要求屏幕回显 100% 一致）。

### REQ-0052-005 — 流式输出期间 typeahead + backspace 仍可守住不丢 turn

在 Windows ConPTY 真 TTY 下：

- Turn1 流式输出期间输入 Turn2（不回车）并用 Backspace 编辑；
- Turn1 完成后回车提交 Turn2；
- `events.jsonl` 必须落盘 Turn2 的最终编辑文本（不丢、不合并）。

### REQ-0052-006 — Ctrl+C：prompt 与 in-flight 的行为保持可用

在 Windows ConPTY 真 TTY 下：

- prompt idle 时 Ctrl+C 不得形成 `user.message`；
- in-flight 时 Ctrl+C 能尽快回到 prompt，且下一 turn 仍能正常完成（以 e2e 断言为准）。

### REQ-0052-007 — 文档与套件隔离不混淆

- `e2e_cli_win_tests/` 与 `e2e_cli_tests/` 仍为独立 opt-in 套件（不并入 `e2e_tests/` 的默认 core suite）。
- `AGENTS.md` 需简要说明 v52 的输入后端与回退开关，避免与 SDK core e2e 混淆。

## Acceptance (DoD)

必须全部满足：

1) Windows 11 + PowerShell 7.x（ConPTY 可用）：
   - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
2) 关键单元测试（避免回归到非 TTY/fake IO）：
   - `python -m unittest -q tests.test_cli_repl_multiline_paste tests.test_cli_repl_thinking_hint tests.test_cli_prompt_styling tests.test_cli_repl_builtin_cwd`
3) REQ-0052-001..007 均有可追溯落地（Req → Plan → Code/Tests → Evidence）。

