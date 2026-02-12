# PRD-0046 — Windows CLI ConPTY CR Output Competition (v46)（`\r` 覆盖型输出竞争：不丢输入、不丢 turn）

## Vision

把终端世界的经典坑“`\r` 覆盖型输出（progress/repaint）与用户输入竞争”做成 Windows ConPTY（真 TTY）下可守门的 E2E 回归：

- 当程序在流式阶段产生频繁的 `\r` 输出（模拟进度条/重绘），用户仍可在输出期间提前输入并使用 Backspace 编辑；
- Turn2 必须以“编辑后的最终文本”落盘到 `events.jsonl`（证据链），不得丢 turn、不得合并 turn。

## Non-Goals

- 不在 v46 做视觉一致性断言（屏幕是否闪烁/覆盖/整行消失），只守住功能证据链（events.jsonl）。

## Requirements

### REQ-0046-001 — With CR progress noise, typeahead+backspace still preserved (ConPTY)

在 ConPTY 真 TTY 下：

- Turn1：触发长回复（≥ 15000 chars）
- Turn1 进行中：输入 Turn2（不回车），并按 Backspace（DEL/BS 任一）修改最后一个字符
- Turn1 完成后：按回车提交 Turn2

验收：

- `events.jsonl` 存在 Turn1 与 Turn2 的 `user.message`
- Turn2 文本等于“编辑后的预期文本”

### REQ-0046-002 — CR 噪声注入是 opt-in（仅测试开启）

新增一个仅供测试的环境开关，用于在请求进行中向 stdout 注入 `\r` 噪声（模拟 progress/repaint）：

- 默认关闭（不影响正常用户）
- E2E 用例显式开启

## Acceptance (DoD)

必须全部满足：

1) Windows 11 下：
   - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
2) REQ-0046-001..002 均有可追溯落地（Req → Plan → Tests → Evidence）。

