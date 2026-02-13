# PRD-0007 — Real-Network E2E Expansion（真实网络 E2E 扩展）

## Vision

建立“真家伙”的回归门禁：基于 `e2e_tests/` 的真实网络 E2E（RIGHTCODE/OpenAI-compatible endpoint），对 provider 与 runtime 的关键链路提供端到端验证，并逐步扩展覆盖面，支撑后续与 opencode 的更深对齐（尤其是测试套件对齐）。

## Background / Motivation

离线 E2E 能保证 deterministic 回归，但无法覆盖：
- 真实网络 I/O、超时/重试、SSE streaming 数据形态差异
- 上游网关对 Responses API 的边界行为（response_id、usage、事件顺序等）

因此需要扩展 `e2e_tests/` 的真实网络 E2E，用更少、更硬、更稳定的断言，覆盖最核心的真实链路。

## Non-Goals

- 不默认运行真实网络 E2E（仍需显式 `discover -s e2e_tests`）。
- 不做“必须模型主动工具调用”的脆弱测试（除非能足够确定/约束），优先验证 provider/runtime 的网络与协议主干。
- 不引入 pytest/playwright 等新框架（继续 `unittest`）。

## Requirements

### REQ-0007-001 — Provider complete (Responses API)

新增 E2E：直接调用 `OpenAIResponsesProvider.complete()`，验证：
- 返回 `assistant_text` 非空
- `response_id` 非空

### REQ-0007-002 — Provider stream (SSE)

新增 E2E：直接调用 `OpenAIResponsesProvider.stream()`，验证：
- 至少收到 1 个 `TextDeltaEvent`
- 最终收到 `DoneEvent`（包含 `response_id`）

### REQ-0007-003 — Runtime query emits deltas

新增 E2E：`openagentic_sdk.query()` + `include_partial_messages=True`，验证：
- 事件中出现 `assistant.delta`
- 最终有 `result` 且 `final_text` 包含指定 token

### REQ-0007-004 — Session resume smoke

新增 E2E：同一 `FileSessionStore` 下 run 两次（第二次 `resume=session_id`），验证：
- 第二次返回的 `session_id` 与第一次一致
- 两次都拿到 `final_text`

### REQ-0007-005 — Slash command direct execution smoke (real model)

新增 E2E：在临时项目根写入 `.opencode/commands/<name>.md`，用户输入 `/name ...`，验证：
- 最终 `final_text` 包含模板内的随机 token（黑盒证明 runtime 确实做了直执行展开）

## Acceptance (DoD)

必须全部满足：

1) 配好环境变量后（至少 `RIGHTCODE_API_KEY`），运行：
   - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
   exit code=0
2) 新增用例覆盖 REQ-0007-001..005

