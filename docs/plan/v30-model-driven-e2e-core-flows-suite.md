# v30 Plan — Model-Driven E2E (Core Flows Suite)（模型驱动 E2E：核心用户流程套件）

## Goal

新增 `core_flows` 随机层套件，让测试保持“活”的用户流程覆盖，同时用 model-driven runner 的 pass-rate 门禁与归因来管理抖动。

## PRD Trace

- REQ-0030-001
- REQ-0030-002
- REQ-0030-003

## Scope

做：

- 新增 `e2e_tests/core_flows.py`（suite loader）
- runner 报告增强：聚合失败用例频次（便于定位最吵的那几条）
- 更新 `AGENTS.md`：补充 core_flows 的推荐门禁命令
- 更新 `skills/model-driven-e2e/SKILL.md`：补充“两车道”（smoke vs flows）的入口

不做：

- 不改 smoke_core 的 hard-invariant 门禁口径（仍建议 1.0）
- 不删除/改写现有用户流程 e2e（仅挑选集合进入 core_flows）
- 不动 CLI PTY/ConPTY
- 不动 MCP/Gateway

## Acceptance (DoD)

必须全部满足：

1) `python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- `python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0` → OK（Runs=3, Passes=3, pass_rate=1.000）
- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8` → OK（Runs=5, Passes=5, pass_rate=1.000）
- Report dirs:
  - `.openagentic_e2e_reports/20260212T034803Z-e2e_tests.smoke_core-pid33268/`
  - `.openagentic_e2e_reports/20260212T034803Z-e2e_tests.core_flows-pid36860/`

## Steps（Strict）

1) Red：写 PRD/Plan，明确两车道门禁口径
2) Green：新增 core_flows suite + runner 报告增强
3) Verify：实跑两车道 runner，并写回 Evidence
