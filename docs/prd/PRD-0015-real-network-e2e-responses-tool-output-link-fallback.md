# PRD-0015 — Real-Network E2E (Responses tool output link fallback)（真实网络 E2E：Responses 工具输出关联回退）

## Vision

用真实网络 E2E 把 `runtime_core` 在 Responses 协议下的“工具输出关联回退”路径做硬回归，确保当网关拒绝“仅 function_call_output”续写时：
- runtime 会识别错误并触发回退重试；
- 重试输入会补齐对应的 `function_call`（与 `function_call_output` 同 call_id 对齐）；
- 最终 `result.provider_metadata.supports_previous_response_id == False` 可回归。

## Background

在 Responses 增量模式中，runtime 会在工具执行后发送仅包含 `function_call_output` 的输入，并依赖 `previous_response_id` 线程化上下文。
部分 OpenAI-compatible 网关可能拒绝这种输入（报 “No tool call found for function call output”），此时 runtime 必须回退到“补齐 function_call + 取消 previous_response_id”模式才能继续。

## Non-Goals

- 不测试 MCP/Gateway 业务功能；这里只验证 runtime_core 的 fallback 行为。
- 不要求模型输出特定自然语言；断言以 provider 调用形态与 Result metadata 为准。

## Requirements

### REQ-0015-001 — fallback prepends function_call when outputs-only is rejected（真实网络）

新增 E2E：
- 第一次模型调用（真实网络）后注入一个 `Read` tool call；
- 工具执行后，第二次模型调用尝试 outputs-only + previous_response_id；
- 通过 provider wrapper 人为注入 “No tool call found for function call output … call_id …” 错误；
- 断言 runtime 回退重试时的输入包含 `function_call` + `function_call_output`（同 call_id）；
- 断言最终 `result.provider_metadata.supports_previous_response_id == False`。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0015-001

