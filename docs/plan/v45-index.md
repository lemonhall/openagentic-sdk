# v45 Index

## Vision

继续加厚 Windows ConPTY（真 TTY）下 `openagentic_cli chat` 的“输出竞争/吞键/吃字”回归：在 streaming 输出进行中，用户输入并按 Backspace 编辑，turn 仍要按编辑后的文本可靠落盘。

## Milestones

- **M1: Streaming + typeahead + backspace E2E v45**
  - Plan: `docs/plan/v45-win-cli-conpty-streaming-typeahead-backspace.md`
  - PRD: `docs/prd/PRD-0045-win-cli-conpty-streaming-typeahead-backspace-v45.md`
  - DoD：
    - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0045-001 → `docs/plan/v45-win-cli-conpty-streaming-typeahead-backspace.md` → `e2e_cli_win_tests/e2e_win_typeahead_backspace_during_response_real.py` → Evidence in plan
- REQ-0045-002 → `docs/plan/v45-win-cli-conpty-streaming-typeahead-backspace.md` → `e2e_cli_win_tests/README.md` → Evidence in plan

## ECN

- None
