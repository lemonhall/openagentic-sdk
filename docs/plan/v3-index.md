# v3 Index — Query Loop Decomposition

## Vision

见：`docs/prd/PRD-0003-query-loop-decomposition.md`

## Milestones

- M1: query_loop 拆分完成（REQ-0003-001/004）
  - DoD:
    - 新增 `openagentic_sdk/runtime_core/query_loop_steps/`
    - `openagentic_sdk/runtime_core/query_loop.py` 变薄（orchestrator）
    - Windows 范围回归通过（见 v3 plan）
- M2: 行为证据链（REQ-0003-002/003）
  - DoD:
    - WSL2 全量 `python3 -m unittest -q` 通过

## Plan Index

- `docs/plan/v3-query-loop-decomposition.md`

## Traceability Matrix

| Req ID | Plan | Tests | Evidence |
|---|---|---|---|
| REQ-0003-001 | v3-query-loop-decomposition.md | `tests/test_runtime_tool_loop.py` 等回归 | `wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` |
| REQ-0003-002 | v3-query-loop-decomposition.md | 全套 `tests/` | 同上 |
| REQ-0003-003 | v3-query-loop-decomposition.md | hooks/previous_response_id/tool loop 相关测试 | 同上 |
| REQ-0003-004 | v3-query-loop-decomposition.md | review + 回归 | 同上 |

## Evidence（2026-02-11）

- Windows：`python -m unittest -q tests.test_runtime_tool_loop tests.test_runtime_streaming tests.test_hooks_user_prompt_submit tests.test_hooks_model_points tests.test_runtime_previous_response_id_fallback tests.test_runtime_tool_output_linking_fallback tests.test_runtime_tool_output_linking_fallback_with_hooks` ✅
- WSL2：`wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` ✅

## ECN Index

（v3 暂无）
