# v24 Index

## Vision

补齐 Windows 11 原生终端的 CLI 回归能力：优先交付可回归的 Windows 原生交互式 e2e；ConPTY（真 TTY）作为默认驱动，stdio pipes 作为对照/降级。

## Milestones

- **M1: Windows 11 ConPTY CLI E2E (v24)**
  - Plan: `docs/plan/v24-windows-cli-conpty-e2e.md`
  - PRD: `docs/prd/PRD-0024-windows-cli-conpty-e2e-v24.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0024-001 → `docs/plan/v24-windows-cli-conpty-e2e.md` → `e2e_cli_win_tests/README.md` → Evidence in plan
- REQ-0024-002 → `docs/plan/v24-windows-cli-conpty-e2e.md` → ConPTY（`packages/conpty-expect/` + `e2e_cli_win_tests/_conpty.py`）默认 / stdio pipes（`e2e_cli_win_tests/_pipes.py`）对照 → Evidence in plan
- REQ-0024-003 → `docs/plan/v24-windows-cli-conpty-e2e.md` → `e2e_cli_win_tests/e2e_win_repl_help_exit.py` → Evidence in plan
- REQ-0024-004 → `docs/plan/v24-windows-cli-conpty-e2e.md` → `e2e_cli_win_tests/e2e_win_repl_help_exit.py` → Evidence in plan
- REQ-0024-005 → `docs/plan/v24-windows-cli-conpty-e2e.md` → `e2e_cli_win_tests/e2e_win_repl_paste_modes.py` → Evidence in plan

## ECN

- ECN-0024-001（2026-02-12）：v24 默认驱动先落到 stdio pipes（可回归），ConPTY harness 保留为后续加强项。
- ECN-0024-002（2026-02-12）：ConPTY（真 TTY）通过 `conpty-expect` 稳定化后升级为默认驱动；pipes 保留对照/降级。

## Deltas (Vision vs Reality)

- ConPTY（真 TTY）现已覆盖核心路径；仍需持续补齐更多“真实终端行为”用例（例如响应中 typeahead、粘贴/编辑键、极端编码等）。
