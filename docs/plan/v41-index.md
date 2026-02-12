# v41 Index

## Vision

按 `docs/research/Terminal-Classic-Bugs-Atlas-Deep-Research.md` 的“终端经典坑”图谱，持续扩容 `openagentic_cli` 的真终端 E2E（Windows ConPTY / POSIX PTY），把终端语义类回归（吞键/删词/控制序列污染/粘贴误触发）变成可守门的自动化证据链。

## Milestones

- **M1: CLI terminal atlas e2e expansion v41**
  - Plan: `docs/plan/v41-cli-terminal-atlas-e2e-expansion.md`
  - PRD: `docs/prd/PRD-0041-cli-terminal-atlas-e2e-expansion-v41.md`
  - DoD：
    - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0041-001 → `docs/plan/v41-cli-terminal-atlas-e2e-expansion.md` → `docs/research/Terminal-Classic-Bugs-Atlas-Deep-Research.md` → Evidence in plan
- REQ-0041-002 → `docs/plan/v41-cli-terminal-atlas-e2e-expansion.md` → `e2e_cli_win_tests/e2e_win_special_keys_do_not_pollute_input_real.py` + `openagentic_cli/repl.py` → Evidence in plan
- REQ-0041-003 → `docs/plan/v41-cli-terminal-atlas-e2e-expansion.md` → `e2e_cli_win_tests/README.md` + `AGENTS.md` → Evidence in plan

## ECN

- None
