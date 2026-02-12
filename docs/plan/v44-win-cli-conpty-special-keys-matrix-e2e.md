# v44 Plan — Windows CLI ConPTY Special Keys Matrix E2E（特殊键序列不污染输入扩容）

## Goal

按 `docs/research/Terminal-Classic-Bugs-Atlas-Deep-Research.md` 的“特殊键/ESC 歧义/控制序列污染输入”坑位，把更多常见 VT 序列（CSI + SS3 F1-F4）纳入 Windows ConPTY 在线 E2E 回归。

## PRD Trace

- REQ-0044-001..002（见 `docs/prd/PRD-0044-win-cli-conpty-special-keys-matrix-e2e-v44.md`）

## Scope

做：

- 新增 1 条 Windows ConPTY 在线 E2E：特殊键矩阵序列不应进入 `events.jsonl`
- 必要时扩展非 paste turn 的 VT 序列消毒（如 SS3 F1-F4）
- 跑通 Windows suite gate 并记录 Evidence

不做：

- 不实现方向键编辑/光标移动，只守住“不污染输入”

## Acceptance (DoD)

必须全部满足：

- `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
- 新增用例断言锚到 `events.jsonl`
- Evidence 写入本计划

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- Env: Windows 11 + PowerShell 7.x + ConPTY + real-network
- Command + Result:
  - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` → OK（Ran 12 tests, ~100s）

## Steps（Strict）

1) Red：新增特殊键矩阵 E2E（若序列未被消毒应失败）
2) Green：必要时扩展消毒逻辑并跑到绿
3) Verify：跑 Windows suite 并写 Evidence
