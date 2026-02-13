# v52 Index

## Vision

把 `oa chat` 的输入升级为 Prompt Toolkit 行编辑器：在 Windows ConPTY 真 TTY 下稳定支持方向键/Backspace/CJK/typeahead，并保留 legacy 回退开关。

## Milestones

- **M1: Prompt Toolkit line editor for oa chat v52**
  - Plan: `docs/plan/v52-cli-chat-prompt-toolkit-line-editor.md`
  - PRD: `docs/prd/PRD-0052-cli-chat-prompt-toolkit-line-editor-v52.md`
  - DoD：
    - `python -m unittest -q tests.test_cli_repl_multiline_paste tests.test_cli_repl_thinking_hint tests.test_cli_prompt_styling tests.test_cli_repl_builtin_cwd`
    - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-13）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0052-001 → `docs/plan/v52-cli-chat-prompt-toolkit-line-editor.md` → `openagentic_cli/repl_chat.py` + `pyproject.toml` → Evidence in plan
- REQ-0052-002 → `docs/plan/v52-cli-chat-prompt-toolkit-line-editor.md` → `openagentic_cli/repl_chat.py` + `AGENTS.md` → Evidence in plan
- REQ-0052-003 → `docs/plan/v52-cli-chat-prompt-toolkit-line-editor.md` → `e2e_cli_win_tests/e2e_win_arrow_keys_editing_real.py` → Evidence in plan
- REQ-0052-004 → `docs/plan/v52-cli-chat-prompt-toolkit-line-editor.md` → `e2e_cli_win_tests/e2e_win_backspace_input_sequence_real.py` + `e2e_cli_win_tests/e2e_win_backspace_cjk_input_real.py` → Evidence in plan
- REQ-0052-005 → `docs/plan/v52-cli-chat-prompt-toolkit-line-editor.md` → `e2e_cli_win_tests/e2e_win_typeahead_backspace_during_response_real.py` → Evidence in plan
- REQ-0052-006 → `docs/plan/v52-cli-chat-prompt-toolkit-line-editor.md` → `e2e_cli_win_tests/e2e_win_ctrl_c_idle_real.py` + `e2e_cli_win_tests/e2e_win_ctrl_c_during_response_real.py` → Evidence in plan
- REQ-0052-007 → `docs/plan/v52-cli-chat-prompt-toolkit-line-editor.md` → `AGENTS.md` → Evidence in plan

## ECN

- None
