# v6 Index

## Vision

继续扩充离线 E2E 回归门禁：覆盖 AskUserQuestion / SlashCommand(tool) / tool error serialization 三个核心边界链路。

## Milestones

- **M1: Offline E2E core tooling expansion** — AQ/SlashTool/Error
  - Plan: `docs/plan/v6-offline-e2e-more-core-tooling.md`
  - PRD: `docs/prd/PRD-0006-offline-e2e-more-core-tooling.md`
  - DoD（命令证据）：
    - `wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"`
    - `python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0006-001 → `docs/plan/v6-offline-e2e-more-core-tooling.md` → `e2e_tests_offline/e2e_ask_user_question.py` → Evidence in plan
- REQ-0006-002 → `docs/plan/v6-offline-e2e-more-core-tooling.md` → `e2e_tests_offline/e2e_slash_command_tool_parts.py` → Evidence in plan
- REQ-0006-003 → `docs/plan/v6-offline-e2e-more-core-tooling.md` → `e2e_tests_offline/e2e_tool_error_serialization.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- ✅ 已达成：新增 AskUserQuestion / SlashCommand(tool) / tool error serialization 的离线 E2E
