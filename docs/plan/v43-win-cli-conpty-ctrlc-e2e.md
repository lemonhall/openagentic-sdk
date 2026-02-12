# v43 Plan — Windows CLI ConPTY Ctrl+C E2E（Ctrl+C 中断语义回归）

## Goal

按 `docs/research/Terminal-Classic-Bugs-Atlas-Deep-Research.md` 的 P0 清单，把 Ctrl+C 的两个关键场景（空闲/请求中）做成 Windows ConPTY 在线 E2E，并以 `events.jsonl` 为证据链固化回归。

## PRD Trace

- REQ-0043-001..003（见 `docs/prd/PRD-0043-win-cli-conpty-ctrlc-e2e-v43.md`）

## Scope

做：

- 新增 2 条 Windows ConPTY 在线 E2E：
  - idle Ctrl+C：不产生 `user.message`，且可继续输入
  - in-flight Ctrl+C：中断请求并可继续下一 turn
- 跑通 suite gate 并记录 Evidence

不做：

- 不扩展到 POSIX PTY（另起 vN）
- 不覆盖 Ctrl+S/Ctrl+Q、关闭窗口等其它通道

## Acceptance (DoD)

必须全部满足：

- `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
- 两个用例都以 `events.jsonl` 为核心断言锚点（避免屏幕文案脆弱）
- Evidence 写入本计划

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- Env: Windows 11 + PowerShell 7.x + ConPTY + real-network
- Command + Result:
  - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` → OK（Ran 11 tests, ~94s）

## Steps（Strict）

1) Red：先加 2 条 e2e（预计在实现不完整时失败）
2) Green：必要时修复 Ctrl+C 行为（空闲/请求中）
3) Verify：跑全套 Windows suite，写回 Evidence
