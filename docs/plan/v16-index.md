# v16 Index

## Vision

继续扩大真实网络 E2E 的核心覆盖面：以 `runtime_core/tools/hooks/permissions/skill/sessions` 为核心，把主路径与护栏路径都做成硬回归证据。

## Milestones

- **M1: Real-network E2E (core hardening v16)** — stream+tools / prune / resume / permission allow / hook lifecycle / non-injected edit
  - Plan: `docs/plan/v16-real-network-e2e-core-hardening.md`
  - PRD: `docs/prd/PRD-0016-real-network-e2e-core-hardening-v16.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-11）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0016-001 → `docs/plan/v16-real-network-e2e-core-hardening.md` → `e2e_tests/e2e_streaming_tool_loop_read_real.py` → Evidence in plan
- REQ-0016-002 → `docs/plan/v16-real-network-e2e-core-hardening.md` → `e2e_tests/e2e_compaction_prune_tool_outputs_real.py` → Evidence in plan
- REQ-0016-003 → `docs/plan/v16-real-network-e2e-core-hardening.md` → `e2e_tests/e2e_resume_after_fallback_no_threading_real.py` → Evidence in plan
- REQ-0016-004 → `docs/plan/v16-real-network-e2e-core-hardening.md` → `e2e_tests/e2e_permissions_prompt_allow_real.py` → Evidence in plan
- REQ-0016-005 → `docs/plan/v16-real-network-e2e-core-hardening.md` → `e2e_tests/e2e_hooks_lifecycle_observability_real.py` → Evidence in plan
- REQ-0016-006 → `docs/plan/v16-real-network-e2e-core-hardening.md` → `e2e_tests/e2e_tools_edit_roundtrip_real_no_injection.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- 为了让非注入 Edit happy-path 稳定通过：`EditTool` 将空字符串 `before/after` 视为未提供（兼容模型/Provider 常见输出）。
