# PRD-0038 — Model-Driven E2E (Core Flows Expansion v38)（模型驱动 E2E：核心流程扩容 v38）

## Vision

把随机层 `core_flows` 做“更厚”，用更多真实用户任务型流程覆盖核心模块：

- Tools / Skill / Hooks / Permissions / Sessions(resume) / Compaction

本轮强调：

- 不注入 toolcalls（让模型自己在约束下完成流程）
- 断言以 `tool.use/tool.result` + 磁盘产物为主，减少对唯一 `final_text` 的依赖
- 允许抖动：用 model-driven runner 的统计门禁来吸收网络/模型波动

## Non-Goals

- 不扩大到 Gateway/MCP。
- 不触碰 PTY/ConPTY。
- 不把随机层改成 injected（hard-invariants 继续由 `core_matrix_v37` 守门）。

## Requirements

### REQ-0038-001 — Add core_flows tests (user-task style)

新增不少于 10 条 `e2e_tests/e2e_flow_*.py`（真实网络、no injection），覆盖：

- Glob+Grep+Edit+Read 链路
- List+Read 链路
- WebFetch 基础 fetch
- WebFetch SSRF/blocked host（localhost）负路径 + 继续可用
- Resume 跨两次 run 的流程
- Permissions(prompt) allow 流程
- AskUserQuestion + Permission(prompt) + Write/Read 组合
- TodoWrite 落盘并通过 Read 验证
- Read offset/limit 行号模式
- Skill missing → error → Skill existing 成功

### REQ-0038-002 — Expand `e2e_tests/core_flows.py`

把新增用例纳入 `e2e_tests/core_flows.py`，使随机层覆盖面“明显变厚”。

### REQ-0038-003 — Evidence via model-driven gate

输出可复现证据（DoD）：

1) `python -m unittest -v e2e_tests.core_flows` exit code=0  
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 2` exit code=0

## Acceptance (DoD)

必须全部满足：

- REQ-0038-001..003 全部落地
- 证据写入 `docs/plan/v38-model-driven-e2e-core-flows-expansion.md`

