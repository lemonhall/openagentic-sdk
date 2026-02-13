# v4 Index

## Vision

把“端到端回归”做成默认可跑、可重复、无外部依赖的一等公民：在不需要外网/Key 的情况下，也能验证 Core/Tool/Streaming/Resume 四条核心链路。

## Milestones

- **M1: Offline E2E test suite** — 覆盖核心用户流程（Core/Tool/Streaming/Resume）
  - Plan: `docs/plan/v4-offline-e2e-test-suite.md`
  - PRD: `docs/prd/PRD-0004-offline-e2e-test-suite.md`
  - DoD（命令证据）：
    - `wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"`
    - `python -m unittest -q tests.test_query_messages_tool_loop_blocks`
    - `python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0004-001 → `docs/plan/v4-offline-e2e-test-suite.md` → `e2e_tests_offline/*` → Evidence in plan
- REQ-0004-002 → `docs/plan/v4-offline-e2e-test-suite.md` → `e2e_tests_offline/e2e_quickstart.py` → Evidence in plan
- REQ-0004-003 → `docs/plan/v4-offline-e2e-test-suite.md` → `e2e_tests_offline/e2e_tool_loop_todowrite.py` → Evidence in plan
- REQ-0004-004 → `docs/plan/v4-offline-e2e-test-suite.md` → `e2e_tests_offline/e2e_streaming_text.py` → Evidence in plan
- REQ-0004-005 → `docs/plan/v4-offline-e2e-test-suite.md` → `e2e_tests_offline/e2e_resume_previous_response_id.py` → Evidence in plan
- REQ-0004-006 → `docs/plan/v4-offline-e2e-test-suite.md` → `e2e_tests_offline/README.md` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- ✅ 已达成：新增离线 E2E 套件（4 个用例），无需外网/Key
- ✅ 已达成：补强 message_query 的 tool-loop blocks 单测
