# v5 Index

## Vision

扩展离线 E2E 覆盖到 Skill / SlashCommand / PermissionGate / Compaction，让 runtime/核心模块重构可持续推进且风险可控。

## Milestones

- **M1: Offline E2E expansion (core modules)** — Skill/Slash/Perm/Compaction
  - Plan: `docs/plan/v5-offline-e2e-suite-expansion.md`
  - PRD: `docs/prd/PRD-0005-offline-e2e-suite-expansion.md`
  - DoD（命令证据）：
    - `wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"`
    - `python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0005-001 → `docs/plan/v5-offline-e2e-suite-expansion.md` → `e2e_tests_offline/e2e_skill_tool.py` → Evidence in plan
- REQ-0005-002 → `docs/plan/v5-offline-e2e-suite-expansion.md` → `e2e_tests_offline/e2e_slash_command_direct_exec.py` → Evidence in plan
- REQ-0005-003 → `docs/plan/v5-offline-e2e-suite-expansion.md` → `e2e_tests_offline/e2e_permission_prompt_user_answerer.py` → Evidence in plan
- REQ-0005-004 → `docs/plan/v5-offline-e2e-suite-expansion.md` → `e2e_tests_offline/e2e_compaction_overflow_legacy.py` → Evidence in plan
- REQ-0005-005 → `docs/plan/v5-offline-e2e-suite-expansion.md` → `e2e_tests_offline/README.md` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- ✅ 已达成：离线 E2E 覆盖 Skill / SlashCommand / PermissionGate / Compaction
