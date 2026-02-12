# v29 Index

## Vision

继续夯实核心 smoke：把最容易抖的“模型规划型”用例替换为 injected toolcalls 版本，保持真网络，同时让门禁更稳定、更像协议回归测试。

## Milestones

- **M1: Real-network e2e (smoke stability via injected toolcalls v29)**
  - Plan: `docs/plan/v29-real-network-e2e-smoke-stability-injected.md`
  - PRD: `docs/prd/PRD-0029-real-network-e2e-smoke-stability-injected-v29.md`
  - DoD：
    - `python -m unittest -v e2e_tests.smoke_core`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0029-001 → `docs/plan/v29-real-network-e2e-smoke-stability-injected.md` → `e2e_tests/e2e_perm_prompt_deny_then_allow_write_real_injected.py` → Evidence in plan
- REQ-0029-002 → `docs/plan/v29-real-network-e2e-smoke-stability-injected.md` → `e2e_tests/e2e_tool_loop_recover_read_missing_real_injected.py` → Evidence in plan

## ECN

- None
