# v55 Index

## Vision

为 `oa chat` 增加一个 F12 打开的 session editor TUI：能在当前会话中直接修正历史 `user.message` / `assistant.message` 文本，并保证保存后的下一轮对话真实按编辑后的本地历史继续，而不是偷偷沿用旧的 provider 远端会话链路。

## Milestones

- **M1: oa chat F12 session editor v55**
  - Plan: `docs/plan/v55-oa-chat-f12-session-editor.md`
  - PRD: `docs/prd/PRD-0055-oa-chat-f12-session-editor-v55.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_session_edit_store tests.test_session_edit_resume_reset tests.test_cli_session_editor_model`
    - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_win_f12_session_editor_*.py" -v`
  - Status: todo

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0055-001 → `docs/plan/v55-oa-chat-f12-session-editor.md` → `tests.test_cli_session_editor_model` + `e2e_cli_win_tests/e2e_win_f12_session_editor_save_offline.py` → Evidence pending
- REQ-0055-002 → `docs/plan/v55-oa-chat-f12-session-editor.md` → `tests.test_cli_session_editor_model` → Evidence pending
- REQ-0055-003 → `docs/plan/v55-oa-chat-f12-session-editor.md` → `tests.test_session_edit_store` → Evidence pending
- REQ-0055-004 → `docs/plan/v55-oa-chat-f12-session-editor.md` → `tests.test_session_edit_resume_reset` + `e2e_cli_win_tests/e2e_win_f12_session_editor_save_offline.py` → Evidence pending
- REQ-0055-005 → `docs/plan/v55-oa-chat-f12-session-editor.md` → `tests.test_session_edit_store` + `tests.test_cli_session_editor_model` → Evidence pending
- REQ-0055-006 → `docs/plan/v55-oa-chat-f12-session-editor.md` → `tests.test_cli_session_editor_model` + `e2e_cli_win_tests/e2e_win_f12_session_editor_busy_guard_offline.py` → Evidence pending
- REQ-0055-007 → `docs/plan/v55-oa-chat-f12-session-editor.md` → 上述全部测试文件 + plan Evidence → Evidence pending

## ECN

- None

## Deltas (Vision vs Reality)

- 本轮尚未开始实现；当前仅完成 PRD / Plan 口径锁定。
- 最高风险点已前置写入 PRD：
  - 编辑后必须切断 `previous_response_id` 链路；
  - F12 真按键能力必须用 Windows ConPTY E2E 守门，而不是只靠 fake IO 单测。
