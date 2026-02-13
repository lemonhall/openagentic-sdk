# PRD-0031 — Model-Driven E2E (Core Flows Stability v31)（模型驱动 E2E：核心流程稳定性收敛 v31）

## Vision

在不把用例写死的前提下，把 `core_flows` 的噪声继续压下去：

- 用例断言更“证据优先”：优先用 `tool.result`/落盘/事件，而不是 `final_text`
- runner 失败归因更可用：把常见“模型没按步骤/没触发 hook”的失败归类为 `model`，避免全都落在 `regression`

## Non-Goals

- 不将 `core_flows` 改成 injected（保持随机层“活”）。
- 不改变 smoke_core 的 hard-invariant 门禁（仍建议 1.0）。

## Requirements

### REQ-0031-001 — Hooks flow asserts tool evidence, not final text

对 `core_flows` 中的 hooks 用例（PreToolUse rewrite）：

- 断言 hook.event 出现
- 断言 Read 的 `tool.result.output` 实际包含被重写目标文件的内容（token_b）

### REQ-0031-002 — Runner triage recognizes common model-style flakes

runner 归因规则补充：对典型失败信息（如 “did not rewrite … after N attempts”）归为 `model`，便于 triage。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.e2e_hooks_pre_tool_use_rewrite_read_real_no_injection` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8` exit code=0
3) runner 报告中 `failure_kind` 分类更贴近实际（该类失败归入 `model` 而非泛化 `regression`）

