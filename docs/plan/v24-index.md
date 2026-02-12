# v24 Index

## Vision

补齐 Windows 11 原生终端的 CLI 回归能力：优先交付可回归的 Windows 原生交互式 e2e；ConPTY（真 TTY）作为后续加强项。

## Milestones

- **M1: Windows 11 ConPTY CLI E2E (v24)**
  - Plan: `docs/plan/v24-windows-cli-conpty-e2e.md`
  - PRD: `docs/prd/PRD-0024-windows-cli-conpty-e2e-v24.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0024-001 → `docs/plan/v24-windows-cli-conpty-e2e.md` → `e2e_cli_win_tests/README.md` → Evidence in plan
- REQ-0024-002 → `docs/plan/v24-windows-cli-conpty-e2e.md` → `e2e_cli_win_tests/_pipes.py`（默认）/ `e2e_cli_win_tests/_conpty.py`（实验性） → Evidence in plan
- REQ-0024-003 → `docs/plan/v24-windows-cli-conpty-e2e.md` → `e2e_cli_win_tests/e2e_win_repl_help_exit.py` → Evidence in plan
- REQ-0024-004 → `docs/plan/v24-windows-cli-conpty-e2e.md` → `e2e_cli_win_tests/e2e_win_repl_help_exit.py` → Evidence in plan
- REQ-0024-005 → `docs/plan/v24-windows-cli-conpty-e2e.md` → `e2e_cli_win_tests/e2e_win_repl_paste_modes.py` → Evidence in plan

## ECN

- ECN-0024-001（2026-02-12）：v24 默认驱动先落到 stdio pipes（可回归），ConPTY harness 保留为后续加强项。

## Deltas (Vision vs Reality)

- v24 交付已覆盖 Windows 原生交互命令 + 在线真实网络链路；ConPTY（真 TTY）仍需后续迭代补齐（见 PRD/Plan 的“实施策略说明”）。
