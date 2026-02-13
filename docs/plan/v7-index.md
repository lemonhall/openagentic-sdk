# v7 Index

## Vision

把真实网络 E2E 做硬：覆盖 provider.complete/stream、runtime.query(delta)、session resume、slash direct smoke。

## Milestones

- **M1: Real-network E2E expansion** — provider/runtime core paths
  - Plan: `docs/plan/v7-real-network-e2e-expansion.md`
  - PRD: `docs/prd/PRD-0007-real-network-e2e-expansion.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0007-001 → `docs/plan/v7-real-network-e2e-expansion.md` → `e2e_tests/e2e_provider_complete.py` → Evidence in plan
- REQ-0007-002 → `docs/plan/v7-real-network-e2e-expansion.md` → `e2e_tests/e2e_provider_stream.py` → Evidence in plan
- REQ-0007-003 → `docs/plan/v7-real-network-e2e-expansion.md` → `e2e_tests/e2e_query_emits_deltas.py` → Evidence in plan
- REQ-0007-004 → `docs/plan/v7-real-network-e2e-expansion.md` → `e2e_tests/e2e_session_resume_smoke.py` → Evidence in plan
- REQ-0007-005 → `docs/plan/v7-real-network-e2e-expansion.md` → `e2e_tests/e2e_slash_direct_smoke.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- ✅ 已达成：真实网络 E2E 覆盖 provider.complete/stream、query(delta)、session resume、slash direct smoke
