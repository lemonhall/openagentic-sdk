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
  - Status: done（2026-03-26）

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

- 已完成：
  - `events.jsonl` / `transcript.jsonl` 的 message 文本原子改写
  - 编辑后清空 session 内 `result.response_id`，使下一轮 resume 不再沿用旧链路
  - Prompt Toolkit `F12` editor 接入
  - Windows ConPTY offline E2E（真按键 + 本地 stub provider）
- busy 路径的最终合同调整为：streaming 中按 `F12` 不得打开 editor；在支持的输入路径上可以提示 busy，但自动化门禁不再要求提示文案必须出现。
