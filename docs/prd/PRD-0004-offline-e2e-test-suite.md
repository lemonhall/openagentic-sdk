# PRD-0004 — Offline E2E Test Suite（离线端到端测试套件）

## Vision

在**不依赖外网**、不需要 `RIGHTCODE_API_KEY` 的情况下，也能用自动化 E2E 测试覆盖 SDK 的核心用户流程（Core / Tool / Streaming / Resume），让重构（尤其是 runtime 拆分）有“整条链路”级别的回归保护。

## Background / Motivation

当前 `e2e_tests/` 属于“真实网络 E2E”（需要配置 API Key，且可能产生费用），不适合作为默认的端到端回归门禁。

我们需要一套**离线可重复**的 E2E 套件：
- 能在 Windows / WSL2 环境都跑；
- 不需要外部服务；
- 仍然走 `openagentic_sdk.run()` 等真实入口，覆盖真实 tool loop 与 session/resume 逻辑。

## Non-Goals

- 不把 `e2e_tests/` 改成离线（它仍然是“真实网络 E2E”）。
- 不追求覆盖所有工具/所有 provider 协议细节（先覆盖最核心的 4 条用户流程）。
- 不引入新的第三方测试框架（继续使用 `unittest`）。

## Requirements

### REQ-0004-001 — 新增离线 E2E 目录与运行方式

- 新增目录：`e2e_tests_offline/`
- 提供可重复运行命令（无环境变量依赖）：
  - `python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v`

### REQ-0004-002 — Core：离线 quickstart E2E

作为开发者，我可以调用 `openagentic_sdk.run()`，得到：
- 非空 `session_id`
- `final_text` 有值（且符合预期字符串）

### REQ-0004-003 — Tool：离线 tool-loop E2E（TodoWrite）

作为开发者，我可以在一次 run 中完成：
- 模型返回 `TodoWrite` tool call
- Runtime 执行 tool 并把 tool output 作为 `function_call_output` 继续喂给 provider
- 最终得到 `final_text`（符合预期字符串）

### REQ-0004-004 — Streaming：离线 streaming E2E

作为开发者，我可以在 streaming 模式下（provider 具备 `stream()`）得到：
- `final_text` 为拼接后的增量文本（符合预期字符串）

### REQ-0004-005 — Resume/Threading：离线 previous_response_id E2E

作为开发者，我可以在同一个 session 中连续 run 两次，并验证：
- 第二次 provider 收到的 `previous_response_id` 等于第一次返回的 `response_id`

### REQ-0004-006 — 文档说明

- `e2e_tests_offline/README.md` 说明“离线 E2E”与“真实网络 E2E”的区别、各自的运行命令与注意事项。

## Acceptance (DoD)

必须全部满足：

1) WSL2：`wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` exit code = 0
2) Windows：`python -m unittest -q tests.test_query_messages_tool_loop_blocks` exit code = 0
3) Windows：`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v` exit code = 0
4) 离线 E2E 不读取 `RIGHTCODE_*` 环境变量、不发真实网络请求
