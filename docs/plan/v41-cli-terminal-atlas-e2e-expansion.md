# v41 Plan — CLI Terminal Atlas E2E Expansion（按“终端经典坑图谱”扩容 CLI 交互式 E2E）

## Goal

把 `docs/research/Terminal-Classic-Bugs-Atlas-Deep-Research.md` 的“终端经典坑”按优先级（P0→P1）落成可回归 E2E：先守住“不会污染输入/不会误触发/不会吞 turn”。

本轮（v41）聚焦：

- Windows ConPTY：特殊键序列不应污染用户输入（events.jsonl 证据链）

## PRD Trace

- REQ-0041-001..003（见 `docs/prd/PRD-0041-cli-terminal-atlas-e2e-expansion-v41.md`）

## Scope

做：

- 新增 1 条 Windows ConPTY 在线 E2E：验证方向键序列不会被当作普通文本写入 `events.jsonl`
- 在 `openagentic_cli` 的输入读取层做“最小消毒”（仅针对非 paste turn 的常见 VT 键序列），避免控制序列污染证据链
- 跑通 Windows suite gate 并写回 Evidence

不做：

- 不实现完整 line-editor（方向键编辑、history 等）
- 不新增第三方依赖
- 不把安全向终端注入（OSC/CSI）纳入默认 E2E（保留为后续 opt-in）

## Acceptance (DoD)

必须全部满足：

- `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
- 新增用例断言锚到 `events.jsonl`（不依赖屏幕回显）
- `docs/research/Terminal-Classic-Bugs-Atlas-Deep-Research.md` 中至少 1 个坑位被 v41 用例覆盖并在本计划中点名

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- Env: Windows 11 + PowerShell 7.x + ConPTY
- Command + Result:
  - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` → OK（Ran 9 tests, ~73s）

## Steps（Strict）

1) Red：新增 Windows ConPTY E2E（期望在未修复时失败）
2) Green：实现“最小消毒”并跑到绿
3) Verify：跑 suite gate，记录 Evidence
4) Review：把新增用例映射回图谱坑位（P0/P1 backlog 逐步推进）
