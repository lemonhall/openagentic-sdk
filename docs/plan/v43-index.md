# v43 Index

## Vision

在 Windows ConPTY（真 TTY）下，把 `openagentic_cli chat` 的 P0 终端语义回归做厚：优先守住 Ctrl+C（空闲/请求中）不崩溃、不污染、可继续。

## Milestones

- **M1: Windows ConPTY Ctrl+C E2E v43**
  - Plan: `docs/plan/v43-win-cli-conpty-ctrlc-e2e.md`
  - PRD: `docs/prd/PRD-0043-win-cli-conpty-ctrlc-e2e-v43.md`
  - DoD：
    - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0043-001 → `docs/plan/v43-win-cli-conpty-ctrlc-e2e.md` → `e2e_cli_win_tests/e2e_win_ctrl_c_idle_real.py` → Evidence in plan
- REQ-0043-002 → `docs/plan/v43-win-cli-conpty-ctrlc-e2e.md` → `e2e_cli_win_tests/e2e_win_ctrl_c_during_response_real.py` → Evidence in plan
- REQ-0043-003 → `docs/plan/v43-win-cli-conpty-ctrlc-e2e.md` → `e2e_cli_win_tests/_harness.py` → Evidence in plan

## ECN

- None

