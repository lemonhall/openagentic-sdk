# v46 Index

## Vision

继续加厚 Windows ConPTY（真 TTY）下 `openagentic_cli chat` 的“输出竞争/吞键/吃字”回归：把 `\r` 覆盖型输出（progress/repaint）加入竞争场景，确保输入编辑与 turn 落盘不受影响。

## Milestones

- **M1: ConPTY CR output competition E2E v46**
  - Plan: `docs/plan/v46-win-cli-conpty-cr-output-competition.md`
  - PRD: `docs/prd/PRD-0046-win-cli-conpty-cr-output-competition-v46.md`
  - DoD：
    - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0046-001 → `docs/plan/v46-win-cli-conpty-cr-output-competition.md` → `e2e_cli_win_tests/e2e_win_cr_progress_noise_typeahead_backspace_real.py` → Evidence in plan
- REQ-0046-002 → `docs/plan/v46-win-cli-conpty-cr-output-competition.md` → `openagentic_cli/repl.py` → Evidence in plan

## ECN

- None
