# v3 Plan — Query Loop Decomposition（进一步拆分 query_loop）

## Goal

把 `openagentic_sdk/runtime_core/query_loop.py` 继续拆到子目录模块（目标：单文件 ~100 行上下），保持行为/API 不变，用测试证明。

## PRD Trace

- REQ-0003-001
- REQ-0003-002
- REQ-0003-003
- REQ-0003-004

## Scope

做：
- 新增 `openagentic_sdk/runtime_core/query_loop_steps/`，按职责拆分 query loop
- `openagentic_sdk/runtime_core/query_loop.py` 缩为 orchestrator

不做：
- 不改对外行为/协议
- 不做大规模 lint/format

## Acceptance (DoD)

必须全部满足：

1) `openagentic_sdk/runtime_core/query_loop.py` 显著变薄（目标 ~100 行上下；允许小幅偏差）
2) 关键步骤模块迁移到 `openagentic_sdk/runtime_core/query_loop_steps/`
3) WSL2：`wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` exit code=0
4) Windows（范围回归）：
   - `python -m unittest -q tests.test_runtime_tool_loop tests.test_runtime_streaming tests.test_hooks_user_prompt_submit tests.test_hooks_model_points tests.test_runtime_previous_response_id_fallback tests.test_runtime_tool_output_linking_fallback tests.test_runtime_tool_output_linking_fallback_with_hooks`

## Evidence（2026-02-11）

- Windows 范围回归：通过（7 tests OK）
- WSL2 全量：`python3 -m unittest -q` 通过（343 tests OK）

## Steps（Strict）

1) Baseline：在拆分前跑一次 Windows 范围回归，作为最小基线
2) Slice 1：抽 MCP setup（register tools / client lifecycle），跑范围回归
3) Slice 2：抽 session bootstrap/resume rebuild，跑范围回归
4) Slice 3：抽 prompt preprocess（hooks + skills/list-skills + slash command 直执行），跑范围回归
5) Slice 4：抽 model call（stream/complete + retry/fallback），跑范围回归
6) Slice 5：抽 tool call plumbing + finalize，跑范围回归
7) Verify：WSL2 全量 `python3 -m unittest -q` 通过

## Notes

- 这是“结构偿债”版本：不改功能，测试是唯一验收证据。
