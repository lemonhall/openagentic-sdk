# PRD-0034 — Model-Driven E2E (Metamorphic Templates v34)（模型驱动 E2E：关系断言模板 v34）

## Vision

把 `core_flows` 里“容易被 prompt/措辞影响”的用例继续往 **metamorphic/关系断言** 迁移：

- 同一意图的多个 prompt 变体 → 断言同一组硬证据成立
- 目标是减少对唯一 `final_text` 的依赖，让随机层更“活”但不更脆

## Non-Goals

- 不把 `core_flows` 的用例改 injected（保持随机层活性）。
- 不增加过多用例数量导致运行时间膨胀；尽量以“替换”为主。

## Requirements

### REQ-0034-001 — Metamorphic Edit flow template

新增/替换一个 metamorphic Edit 用例：

- 两个 prompt 变体都能完成 `Edit`（或 `Read→Edit`）并在磁盘上体现 token
- 断言以 `tool.use/tool.result` + 落盘为主，不以 `final_text` 为主

### REQ-0034-002 — Metamorphic permission default Edit flow template

新增/替换一个 metamorphic permission(default) Edit 用例：

- 两个 prompt 变体都触发 `user.question` 并允许 Edit
- 断言以 `user.question` + `tool.result` + 落盘为主

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.core_flows` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 1` exit code=0
3) core_flows 用例数不显著膨胀（以替换为主）

