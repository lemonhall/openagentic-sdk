# v27 Index

## Vision

把“resume + permission prompt + tools 落盘”固化为高频 smoke 证据，确保核心对话循环跨进程恢复不掉链子。

## Milestones

- **M1: Real-network e2e (resume + permission persistence v27)**
  - Plan: `docs/plan/v27-real-network-e2e-resume-permission-persistence.md`
  - PRD: `docs/prd/PRD-0027-real-network-e2e-resume-permission-persistence-v27.md`
  - DoD：
    - `python -m unittest -v e2e_tests.e2e_sessions_resume_permission_prompt_write_then_read_real_no_injection`
    - `python -m unittest -v e2e_tests.smoke_core`
  - Status: done（2026-02-12）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0027-001 → `docs/plan/v27-real-network-e2e-resume-permission-persistence.md` → `e2e_tests/e2e_sessions_resume_permission_prompt_write_then_read_real_no_injection.py` → Evidence in plan
- REQ-0027-002 → `docs/plan/v27-real-network-e2e-resume-permission-persistence.md` → `e2e_tests/e2e_sessions_resume_permission_prompt_write_then_read_real_no_injection.py` → Evidence in plan

## ECN

- None
