# v44 Index

## Vision

继续加厚 Windows ConPTY（真 TTY）下 `openagentic_cli chat` 的“终端语义”回归网：把更多特殊键/功能键的 VT 序列纳入 E2E 守门，确保不会污染输入与 `events.jsonl` 证据链。

## Milestones

- **M1: Windows ConPTY special keys matrix E2E v44**
  - Plan: `docs/plan/v44-win-cli-conpty-special-keys-matrix-e2e.md`
  - PRD: `docs/prd/PRD-0044-win-cli-conpty-special-keys-matrix-e2e-v44.md`
  - DoD：
    - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0044-001 → `docs/plan/v44-win-cli-conpty-special-keys-matrix-e2e.md` → `e2e_cli_win_tests/e2e_win_special_keys_matrix_real.py` + `openagentic_cli/repl.py` → Evidence in plan
- REQ-0044-002 → `docs/plan/v44-win-cli-conpty-special-keys-matrix-e2e.md` → `e2e_cli_win_tests/README.md` → Evidence in plan

## ECN

- None
