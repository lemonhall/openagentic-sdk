# v10 Index

## Vision

继续扩大真实网络 E2E 的核心覆盖面，优先夯实 `hooks` 与 `permissions` 的关键语义与事件序列。

## Milestones

- **M1: Real-network E2E (hooks + permissions)** — post_tool_use override / PermissionDenied
  - Plan: `docs/plan/v10-real-network-e2e-core-hooks-permissions.md`
  - PRD: `docs/prd/PRD-0010-real-network-e2e-core-hooks-permissions.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0010-001 → `docs/plan/v10-real-network-e2e-core-hooks-permissions.md` → `e2e_tests/e2e_hooks_post_tool_use_override_real.py` → Evidence in plan
- REQ-0010-002 → `docs/plan/v10-real-network-e2e-core-hooks-permissions.md` → `e2e_tests/e2e_permissions_denied_tool_result_real.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- 为降低真实网络 LLM 行为波动，post_tool_use 用例使用 `HookEngine.after_model_call` 注入一次 Read 调用，确保 post_tool_use override 一定被执行；断言基于 `tool.result` 的输出内容。
