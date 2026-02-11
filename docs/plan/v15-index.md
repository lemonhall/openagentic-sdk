# v15 Index

## Vision

继续扩大真实网络 E2E 的核心覆盖面，优先夯实 `runtime_core` 在 Responses 增量模式下的鲁棒性（工具输出关联/回退重试）。

## Milestones

- **M1: Real-network E2E (responses tool output link fallback)** — prepend function_call on retry
  - Plan: `docs/plan/v15-real-network-e2e-responses-tool-output-link-fallback.md`
  - PRD: `docs/prd/PRD-0015-real-network-e2e-responses-tool-output-link-fallback.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0015-001 → `docs/plan/v15-real-network-e2e-responses-tool-output-link-fallback.md` → `e2e_tests/e2e_responses_tool_output_link_fallback_real.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- 通过 provider wrapper 注入网关错误文本，稳定触发 runtime_core 的 `No tool call found for function call output` 回退重试；断言基于 provider 输入形态与 Result metadata。
