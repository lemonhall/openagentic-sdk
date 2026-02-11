# v21 Index

## Vision

把 `openagentic_cli` 纳入真实网络 E2E 覆盖，并把“真交互”（TTY/PTY）纳入可回归证据：

- 用 POSIX `pty` 驱动 REPL（不是 pipe/非交互）；
- 断言以落盘 `events.jsonl` 为主，弱化模型输出不确定性；
- 强隔离（`OPENAGENTIC_SDK_HOME` / `OPENCODE_TEST_HOME` / `XDG_CONFIG_HOME`），避免本机配置污染测试。

## Milestones

- **M1: Real-network CLI PTY E2E Suite (v21)**
  - Plan: `docs/plan/v21-real-network-e2e-cli-pty.md`
  - PRD: `docs/prd/PRD-0021-real-network-e2e-cli-pty-v21.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v`
  - Status: doing（2026-02-11）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0021-001 → `docs/plan/v21-real-network-e2e-cli-pty.md` → `e2e_cli_tests/README.md` → Evidence in plan
- REQ-0021-002 → `docs/plan/v21-real-network-e2e-cli-pty.md` → `e2e_cli_tests/e2e_cli_repl_help_exit_tty.py` → Evidence in plan
- REQ-0021-003 → `docs/plan/v21-real-network-e2e-cli-pty.md` → `e2e_cli_tests/e2e_cli_repl_help_exit_tty.py` → Evidence in plan
- REQ-0021-004 → `docs/plan/v21-real-network-e2e-cli-pty.md` → `e2e_cli_tests/e2e_cli_repl_long_session_real.py` → Evidence in plan
- REQ-0021-005 → `docs/plan/v21-real-network-e2e-cli-pty.md` → (TBD) `e2e_cli_tests/e2e_cli_repl_new_session_real.py` → Evidence in plan
- REQ-0021-006 → `docs/plan/v21-real-network-e2e-cli-pty.md` → (TBD) `e2e_cli_tests/e2e_cli_repl_paste_modes_real.py` → Evidence in plan
- REQ-0021-007 → `docs/plan/v21-real-network-e2e-cli-pty.md` → `e2e_cli_tests/e2e_cli_resume_and_logs_real.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- v21 目标是把“CLI 真交互”纳入 E2E 证据链；当前已完成 PTY harness + 基础用例骨架，但 `/new` 与 paste 语义仍需补齐以满足 PRD 的全部 REQ。

