# PRD-0014 — Real-Network E2E (Compaction Auto + Summary Pivot)（真实网络 E2E：自动压缩与摘要枢轴）

## Vision

用真实网络 E2E 把 `runtime_core` 的 compaction 自动触发链路做硬回归，确保：
- 在 Responses 模式下，当 `supports_previous_response_id=False` 且使用量触发 overflow 时，会产生 `user.compaction(auto=True, reason="overflow")`；
- compaction 会写入 `assistant.message(is_summary=True)` 作为摘要枢轴；
- 最终 `result.provider_metadata.supports_previous_response_id` 与运行期一致、可回归。

## Background

当前 compaction 的自动触发与工具输出 pruning 都依赖：
- provider protocol（legacy vs responses）
- `supports_previous_response_id` 是否为 True

这导致“Responses 增量模式默认不触发 compaction”的分支容易被忽略；一旦 gateway/协议发生变化（例如 previous_response_id 不被支持触发 fallback），compaction 路径会突然成为关键路径。

## Non-Goals

- 不测试 MCP/Gateway。
- 不要求模型输出特定长摘要文本；只验证事件类型与枢轴语义。

## Requirements

### REQ-0014-001 — auto compaction emits marker + summary pivot（真实网络）

新增 E2E：
- 通过真实网络运行一次带 tool loop 的对话；
- 让运行期进入 `supports_previous_response_id=False`，并强制 overflow；
- 断言事件流包含：
  - `user.compaction`（`auto=True`, `reason="overflow"`）
  - `assistant.message`（`is_summary=True`）
  - 最终 `result.provider_metadata.supports_previous_response_id == False`

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0014-001

