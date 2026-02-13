# v49 Index

## Vision

resume 的 `events.jsonl` 一旦损坏/截断，必须立即失败并给出清晰可定位错误（不允许静默忽略）。

## Milestones

- **M1: resume corrupt events log fails clearly v49**
  - Plan: `docs/plan/v49-resume-corrupt-events-log-fails-clearly.md`
  - PRD: `docs/prd/PRD-0049-resume-corrupt-events-log-fails-clearly-v49.md`
  - DoD：
    - `python -m unittest -v e2e_tests.core_flows_sessions`
    - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
  - Status: done (2026-02-13)

## Traceability Matrix (Req → Plan → Code/Docs → Evidence)

- REQ-0049-001 → `docs/plan/v49-resume-corrupt-events-log-fails-clearly.md` → `openagentic_sdk/sessions/store.py` + `openagentic_sdk/sessions/errors.py` → Evidence in plan
- REQ-0049-002 → `docs/plan/v49-resume-corrupt-events-log-fails-clearly.md` → `e2e_tests/e2e_flow_resume_corrupt_events_log_fails_clearly_real_no_injection.py` → Evidence in plan
- REQ-0049-003 → `docs/plan/v49-resume-corrupt-events-log-fails-clearly.md` → `e2e_tests/core_flows_sessions.py` + `.openagentic_e2e_reports/...` → Evidence in plan

## ECN

- None
