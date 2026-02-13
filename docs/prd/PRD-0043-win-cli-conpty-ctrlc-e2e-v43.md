# PRD-0043 — Windows CLI ConPTY Ctrl+C E2E (v43)（Windows 11：Ctrl+C 中断语义端到端回归）

## Vision

把 `openagentic_cli chat` 在 Windows 11 原生终端（ConPTY 真 TTY）下的 **Ctrl+C** 行为变成可守门的回归：

- 空闲输入阶段按 Ctrl+C：不会生成脏 turn、不崩溃、能回到提示符继续输入；
- 请求进行中（真实网络调用）按 Ctrl+C：能中断当前请求并回到提示符，后续 turn 仍可继续。

断言策略：尽量锚到 **`events.jsonl` 证据链**（turn 是否落盘、是否污染），避免屏幕文案脆弱性。

## Non-Goals

- 不在 v43 覆盖 “Ctrl+S/Ctrl+Q（XON/XOFF）”“窗口关闭事件”等其它中断通道（后续按图谱推进）。
- 不在 v43 引入第三方依赖。

## Requirements

### REQ-0043-001 — Ctrl+C at idle does not create a user turn (ConPTY)

在 `oa> ` 等待输入时按 Ctrl+C：

- 程序不崩溃；
- 能回到 `oa> `；
- `events.jsonl` 中 **不会新增** `user.message`（不会把 Ctrl+C 当成文本落盘）。

### REQ-0043-002 — Ctrl+C during an in-flight request returns to prompt and remains usable (ConPTY)

在发起一个真实网络请求后（模型开始生成/流式输出中）按 Ctrl+C：

- 程序不崩溃；
- 终端能回到 `oa> `；
- 后续再发送一个新 turn 仍能成功完成（证明会话/输入状态未被污染）。

### REQ-0043-003 — Suite remains isolated and opt-in

- 用例落在 `e2e_cli_win_tests/`，保持 opt-in；
- 通过 `OPENAGENTIC_SDK_HOME`/`XDG_CONFIG_HOME` 等隔离，避免污染用户环境；
- 运行命令：
  - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v`

## Acceptance (DoD)

必须全部满足：

1) Windows 11 下：
   - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
2) REQ-0043-001..003 均有可追溯落地（Req → Plan → Tests → Evidence）。
