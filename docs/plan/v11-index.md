# v11 Index

## Vision

继续扩大真实网络 E2E 的核心覆盖面，优先夯实 `runtime_core` 工具环路在拒绝/阻断/错误场景下的稳定语义与事件可观测性。

## Milestones

- **M1: Real-network E2E (runtime_core tool loop guards)** — ToolNotAllowed / HookBlocked / Permission prompt / tool exception
  - Plan: `docs/plan/v11-real-network-e2e-runtime-core-tool-loop-guards.md`
  - PRD: `docs/prd/PRD-0011-real-network-e2e-runtime-core-tool-loop-guards.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0011-001 → `docs/plan/v11-real-network-e2e-runtime-core-tool-loop-guards.md` → `e2e_tests/e2e_runtime_tool_not_allowed_real.py` → Evidence in plan
- REQ-0011-002 → `docs/plan/v11-real-network-e2e-runtime-core-tool-loop-guards.md` → `e2e_tests/e2e_runtime_hook_blocks_tool_real.py` → Evidence in plan
- REQ-0011-003 → `docs/plan/v11-real-network-e2e-runtime-core-tool-loop-guards.md` → `e2e_tests/e2e_runtime_permission_prompt_denies_real.py` → Evidence in plan
- REQ-0011-004 → `docs/plan/v11-real-network-e2e-runtime-core-tool-loop-guards.md` → `e2e_tests/e2e_runtime_tool_error_serialization_real.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- 为降低真实网络 LLM 行为波动，护栏类用例使用 `HookEngine.after_model_call` 注入工具调用与收尾 assistant_text；验证基于事件序列与 `tool.result` 错误语义。
