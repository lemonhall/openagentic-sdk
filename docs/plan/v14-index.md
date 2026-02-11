# v14 Index

## Vision

继续扩大真实网络 E2E 的核心覆盖面，优先夯实 `runtime_core` 在协议 fallback 触发 compaction 时的事件语义与可观测性。

## Milestones

- **M1: Real-network E2E (compaction auto + summary pivot)** — marker + summary + supports_previous_response_id
  - Plan: `docs/plan/v14-real-network-e2e-compaction-auto-summary-pivot.md`
  - PRD: `docs/prd/PRD-0014-real-network-e2e-compaction-auto-summary-pivot.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0014-001 → `docs/plan/v14-real-network-e2e-compaction-auto-summary-pivot.md` → `e2e_tests/e2e_compaction_auto_summary_pivot_real.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- right.codes 网关在 Responses compaction 输入中不接受 ChatCompletions 字段（如 `tool_calls`），已在 `runtime_core/provider_input.py` 的 compaction transcript 构建阶段做净化为纯 role/content 文本，避免 400 unknown_parameter。
