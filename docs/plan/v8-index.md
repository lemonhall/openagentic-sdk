# v8 Index

## Vision

把核心模块（hooks/skill/runtime_core/tools/人类交互）在真实网络 E2E 上做硬回归门禁。

## Milestones

- **M1: Real-network E2E (core modules)** — hooks/skill/tools/runtime_core
  - Plan: `docs/plan/v8-real-network-e2e-core-modules.md`
  - PRD: `docs/prd/PRD-0008-real-network-e2e-core-modules.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0008-001 → `docs/plan/v8-real-network-e2e-core-modules.md` → `e2e_tests/e2e_skill_tool_real.py` → Evidence in plan
- REQ-0008-002 → `docs/plan/v8-real-network-e2e-core-modules.md` → `e2e_tests/e2e_ask_user_question_real.py` → Evidence in plan
- REQ-0008-003 → `docs/plan/v8-real-network-e2e-core-modules.md` → `e2e_tests/e2e_slash_command_tool_parts_real.py` → Evidence in plan
- REQ-0008-004 → `docs/plan/v8-real-network-e2e-core-modules.md` → `e2e_tests/e2e_hooks_before_model_call_rewrite_real.py` → Evidence in plan
- REQ-0008-005 → `docs/plan/v8-real-network-e2e-core-modules.md` → `e2e_tests/e2e_hooks_after_model_call_override_real.py` → Evidence in plan
- REQ-0008-006 → `docs/plan/v8-real-network-e2e-core-modules.md` → `e2e_tests/README.md` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- ✅ 已达成：核心模块真实网络 E2E 覆盖 Skill / AskUserQuestion / SlashCommand tool parts / hooks before+after model call
