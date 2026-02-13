# PRD-0045 — Windows CLI ConPTY Streaming + Typeahead + Backspace (v45)（流式输出期间输入编辑不丢 turn）

## Vision

把“流式输出期间（stdout 不断刷新）用户还在输入并按 Backspace 编辑 → 可能吃字/整行消失/turn 丢失”的经典坑，变成 Windows ConPTY（真 TTY）下可守门的在线 E2E 回归：

- Turn1 请求流式输出很长文本；
- Turn1 进行中用户提前输入 Turn2（不按回车），并按 Backspace 修改；
- Turn1 完成后再回车提交 Turn2：Turn2 必须按**编辑后的文本**落盘为 `user.message`（events.jsonl 证据链）。

## Non-Goals

- 不在 v45 做“视觉一致性”（屏幕上是否出现整行消失/重绘错位）的强断言：终端实现差异太大；本轮只守住**功能证据链**（turn 不丢、不合并、编辑结果正确）。

## Requirements

### REQ-0045-001 — Typeahead + backspace during streaming preserves edited text (ConPTY)

在 ConPTY 真 TTY 下：

- Turn1：触发长回复（≥ 12000 chars）
- Turn1 进行中：输入 Turn2 文本（不回车），按一次 Backspace（DEL/BS 任一）修改最后一个字符
- Turn1 完成后：按回车提交 Turn2

验收：

- `events.jsonl` 中存在 `user.message`=Turn1 与 Turn2；
- Turn2 的 `text` 必须等于“编辑后的预期文本”（例如 `...defY`），不得丢失整段、不得被截断、不得被合并进 Turn1。

### REQ-0045-002 — Suite remains isolated and opt-in

- 用例落在 `e2e_cli_win_tests/`，保持 opt-in；
- 运行命令：
  - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v`

## Acceptance (DoD)

必须全部满足：

1) Windows 11 下：
   - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
2) REQ-0045-001..002 均有可追溯落地（Req → Plan → Tests → Evidence）。

