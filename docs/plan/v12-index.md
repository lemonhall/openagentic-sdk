# v12 Index

## Vision

继续扩大真实网络 E2E 的核心覆盖面，优先夯实 `Skill` 的加载、优先级与错误语义，确保可回归、可机读。

## Milestones

- **M1: Real-network E2E (Skill core)** — overrides / not-found / project_dir
  - Plan: `docs/plan/v12-real-network-e2e-skill-core.md`
  - PRD: `docs/prd/PRD-0012-real-network-e2e-skill-core.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0012-001 → `docs/plan/v12-real-network-e2e-skill-core.md` → `e2e_tests/e2e_skill_project_overrides_global_real.py` → Evidence in plan
- REQ-0012-002 → `docs/plan/v12-real-network-e2e-skill-core.md` → `e2e_tests/e2e_skill_not_found_error_real.py` → Evidence in plan
- REQ-0012-003 → `docs/plan/v12-real-network-e2e-skill-core.md` → `e2e_tests/e2e_skill_project_dir_argument_real.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- 为降低真实网络 LLM 行为波动，Skill 相关用例以 `HookEngine.after_model_call` 注入 tool_calls，并以 `tool.result` 输出作为硬断言（不依赖模型复述内容）。
