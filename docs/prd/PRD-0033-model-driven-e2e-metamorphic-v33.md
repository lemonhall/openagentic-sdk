# PRD-0033 — Model-Driven E2E (Metamorphic / Relation Assertions v33)（模型驱动 E2E：变形测试/关系断言 v33）

## Vision

继续“别做太死”的路线：对随机层 `core_flows` 引入少量 **metamorphic / 关系断言** 用例，用“必要关系成立”替代“唯一文本输出一致”，降低脆弱性并提升回归信号质量。

同时，让 runner 报告显式输出：

- gate 的 **预算**（required passes / allowed failures）
- 可选的 **历史趋势**（最近 N 次 pass_rate 与失败聚合），便于观测漂移

## Non-Goals

- 不把 `core_flows` 改成 injected（保持随机层“活”）。
- 不把 metamorphic 用例变成“死步骤脚本”。
- 不改变 `smoke_core` 的硬门禁口径（仍建议 pass-rate=1.0）。

## Requirements

### REQ-0033-001 — Add a metamorphic core flow test

新增至少 1 条 metamorphic 用例（真网络），验证“同一意图的不同 prompt 变体”仍满足同一组硬证据：

- 磁盘落盘一致（文件内容包含 token）
- tool.use/tool.result 成功（Write/Read/AskUserQuestion 等）
- 尽量少依赖 `final_text`

并将其加入 `e2e_tests.core_flows`。

### REQ-0033-002 — Runner outputs gate budget and optional history trend

runner 报告输出：

- `required_passes`、`allowed_failures`（基于 min_pass_rate 与 runs 计算）
- 可选 history：从 `.openagentic_e2e_reports/` 扫描最近 N 次同 suite 报告，输出 pass_rate 序列与失败聚合

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.e2e_metamorphic_ask_user_write_read_variants_real_no_injection` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 1` exit code=0
3) runner 报告包含 budget 字段；开启 history 时包含 history 字段

