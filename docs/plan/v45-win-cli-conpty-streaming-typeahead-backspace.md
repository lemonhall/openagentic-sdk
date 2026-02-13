# v45 Plan — Windows CLI ConPTY Streaming + Typeahead + Backspace（流式输出期间输入编辑不丢 turn）

## Goal

按 `docs/research/Terminal-Classic-Bugs-Atlas-Deep-Research.md` 的 P0/P1 竞争类坑位，把“流式输出期间用户提前输入并按 Backspace 编辑”的场景做成 ConPTY 在线 E2E，用 `events.jsonl` 守住“turn 不丢、不合并、编辑结果正确”。

## PRD Trace

- REQ-0045-001..002（见 `docs/prd/PRD-0045-win-cli-conpty-streaming-typeahead-backspace-v45.md`）

## Scope

做：

- 新增 1 条 Windows ConPTY 在线 E2E：streaming 时 typeahead + backspace 编辑 → Turn2 按编辑后文本落盘
- 跑通 Windows suite gate 并记录 Evidence

不做：

- 不做“视觉一致性”强断言（整行消失/重绘错位只做功能证据链回归）

## Acceptance (DoD)

必须全部满足：

- `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
- 新增用例断言锚到 `events.jsonl`
- Evidence 写入本计划

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- Env: Windows 11 + PowerShell 7.x + ConPTY + real-network
- Command + Result:
  - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` → OK（Ran 13 tests, ~115s）

## Steps（Strict）

1) Red：新增 E2E（若 turn 丢失/合并/编辑丢失则失败）
2) Green：必要时修复输入/中断语义
3) Verify：跑全套 Windows suite，写 Evidence
