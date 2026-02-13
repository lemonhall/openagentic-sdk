# v2 Index — Runtime Spaghetti Refactor

## Vision

见：`docs/prd/PRD-0002-runtime-spaghetti-refactor.md`

## Milestones

- M1: runtime.py 拆分完成（REQ-0002-001/002/004）
  - DoD:
    - `openagentic_sdk/runtime.py` 明显变薄（兼容层）
    - 新增 `openagentic_sdk/runtime_core/` 并完成模块拆分
    - `python3 -m unittest -q`（WSL2）通过
- M2: 行为证据链（REQ-0002-003）
  - DoD:
    - WSL2 全量 `python3 -m unittest -q` 通过
    - Windows 范围回归通过：`python -m unittest -q tests.test_runtime_tool_loop tests.test_runtime_streaming tests.test_reply_prompt_rendering tests.test_slash_command_templating tests.test_user_slash_command_execution`

## Plan Index

- `docs/plan/v2-runtime-refactor.md`

## Traceability Matrix

| Req ID | Plan | Tests | Evidence |
|---|---|---|---|
| REQ-0002-001 | v2-runtime-refactor.md | `tests/test_runtime_tool_loop.py` 等现有回归 | `wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` |
| REQ-0002-002 | v2-runtime-refactor.md | `tests/test_runtime_tool_loop.py` + 新增 API smoke | 同上 |
| REQ-0002-003 | v2-runtime-refactor.md | 全套 `tests/` | 同上 |
| REQ-0002-004 | v2-runtime-refactor.md | review + 回归 | 同上 |

## ECN Index

（v2 暂无）

## Deltas / Follow-ups

- `openagentic_sdk/runtime_core/query_loop.py` 仍偏大（~700+ 行）；后续可继续把 provider call / tool-call plumbing / MCP setup 再拆细到更小的 mixins（保持 tests 作为证据）。
