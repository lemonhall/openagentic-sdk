# v46 Plan — Windows CLI ConPTY CR Output Competition（`\r` 覆盖型输出竞争回归）

## Goal

按 `docs/research/Terminal-Classic-Bugs-Atlas-Deep-Research.md` 的“`\r` 覆盖/重绘竞争”坑位，把 `openagentic_cli chat` 在 ConPTY 真 TTY 下的“输出噪声 + typeahead + backspace 编辑”守成可回归 E2E（以 `events.jsonl` 为证据链）。

## PRD Trace

- REQ-0046-001..002（见 `docs/prd/PRD-0046-win-cli-conpty-cr-output-competition-v46.md`）

## Scope

做：

- 增加一个测试专用开关：请求进行中向 stdout 注入 `\r` 噪声（模拟 progress/repaint）
- 新增 1 条 Windows ConPTY 在线 E2E：开启噪声后，typeahead + backspace 编辑仍必须可靠落盘
- 跑通 Windows suite gate 并记录 Evidence

不做：

- 不做视觉一致性断言（只守住 events.jsonl）

## Acceptance (DoD)

必须全部满足：

- `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
- 新增用例断言锚到 `events.jsonl`
- Evidence 写入本计划

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- Env: Windows 11 + PowerShell 7.x + ConPTY + real-network
- Command + Result:
  - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` → OK（Ran 14 tests, ~163s）

## Steps（Strict）

1) Red：先加 E2E（若 turn 丢失/编辑丢失则失败）
2) Green：实现 `\r` 噪声注入开关（默认关闭）并跑到绿
3) Verify：跑全套 Windows suite，写 Evidence
