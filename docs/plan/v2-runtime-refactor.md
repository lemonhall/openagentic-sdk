# v2 Plan — Runtime 意大利面重构（拆分 runtime.py）

## Goal

把 `openagentic_sdk/runtime.py` 从“单文件大坨”拆成多个小模块（~200 行量级），保持 API/行为不变，并用测试证明。

## PRD Trace

- REQ-0002-001
- REQ-0002-002
- REQ-0002-003
- REQ-0002-004

## Scope

做：
- 把 runtime 的 helper / mixins / 核心循环拆到 `openagentic_sdk/runtime_core/`
- `openagentic_sdk/runtime.py` 改为 thin re-export（兼容 import）
- 新增 1 个 API smoke test，防止 refactor 意外破坏 import 面

不做：
- 不改行为、不改对外协议
- 不做大规模 lint/format

## Acceptance (DoD)

必须全部满足：

1) WSL2：`wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` exit code=0
2) Windows（范围回归）：`python -m unittest -q tests.test_runtime_tool_loop tests.test_runtime_streaming tests.test_reply_prompt_rendering tests.test_slash_command_templating tests.test_user_slash_command_execution` exit code=0
3) `from openagentic_sdk.runtime import AgentRuntime, RunResult` 仍可用（由测试锁定）
4) `openagentic_sdk/runtime.py` 明显变薄；核心逻辑迁移到 `openagentic_sdk/runtime_core/` 多文件中

## Files

预计创建：
- `openagentic_sdk/runtime_core/*`
- `tests/test_runtime_public_api_smoke.py`

预计修改：
- `openagentic_sdk/runtime.py`

## Steps（Strict）

1) TDD Red：新增 API smoke test，先运行确认会失败（在重构时短暂红）
2) TDD Green：分批抽离模块（helper → slash command → tool dispatch → query loop），每批都跑范围回归
3) Verify：WSL2 全量测试通过

