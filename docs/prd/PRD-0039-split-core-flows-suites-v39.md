# PRD-0039 — Split core_flows into Themed Suites v39（拆分随机层 core_flows 为主题套件 v39）

## Vision

随着随机层 `core_flows` 用例数增长，单个 suite 逐渐变得：

- 运行时间过长（本地不愿跑、回归慢）
- 统计门禁难守（波动累加）
- 难以定位问题（失败归因不清晰）

本轮把随机层拆分为 3 个主题套件，每个套件单独 gate、单独出报告，同时保留原 `core_flows` 作为聚合入口（向后兼容）。

## Non-Goals

- 不改动任何核心 SDK 行为（只改测试组织方式）。
- 不触碰 PTY/ConPTY。
- 不扩大到 Gateway/MCP。

## Requirements

### REQ-0039-001 — New suites

新增 3 个 `unittest` suite 模块：

- `e2e_tests/core_flows_tools.py`
- `e2e_tests/core_flows_sessions.py`
- `e2e_tests/core_flows_hil.py`（human-in-the-loop：permissions/hooks/skills/ask_user）

### REQ-0039-002 — Keep `core_flows` as umbrella

更新 `e2e_tests/core_flows.py`，使其加载上述 3 个套件（不再直接枚举所有模块）。

### REQ-0039-003 — Evidence

输出可复现证据（DoD）：

1) `python -m unittest -v e2e_tests.core_flows_tools` exit code=0  
2) `python -m unittest -v e2e_tests.core_flows_sessions` exit code=0  
3) `python -m unittest -v e2e_tests.core_flows_hil` exit code=0  
4) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_tools --runs 3 --min-pass-rate 0.8 --rerun-failures 1` exit code=0  
5) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1` exit code=0  
6) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1` exit code=0  

## Acceptance (DoD)

必须全部满足：

- REQ-0039-001..003 全部达成
- 证据写入 `docs/plan/v39-split-core-flows-suites.md`

